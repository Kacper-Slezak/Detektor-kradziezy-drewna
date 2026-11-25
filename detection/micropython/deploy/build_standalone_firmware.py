"""Generate stabilized, single-file Pycom LoPy 1.0 `main.py` firmware builds.

Produces two complete, independently deployable standalone firmware files:
- `detection/micropython/deploy/burst/main.py`   (Burst MLP, primary low-RAM target)
- `detection/micropython/deploy/cnn_v46/main.py` (CNN v4.6, fused inference)

Target hardware & exact firmware:
- Pycom LoPy 1.0 (ESP32 @ 160 MHz, no PSRAM)
- Pycom 1.20.2.r6, MicroPython v1.11, commit c5a0a97 (2021-10-28)

Key fixes applied over read-only reference `firmware/main4.py`:
1. Replaces unsupported `machine.pin_deepsleep_wakeup` with Pycom 1.20.2.r6
   `machine.pin_sleep_wakeup(pins, mode, enable_pull)` + stuck-pin loop guard.
2. Eliminates duplicate 10-second audio recording (records once per session).
3. Replaces unsupported `array * int` and generator-in-`array()` with v1.11-safe
   `array(tc, range(n))` zeroing.
4. Handles missing NVS keys (`ValueError`/`OSError`) cleanly on first boot.
5. Hardens Wi-Fi/HTTP error handling, HTTP 2xx status validation, and socket
   cleanup; frees detection buffers + `gc.collect()` before networking.
6. Adds `tryb_diagnostyczny()` for synthetic ADC testing without microphone,
   Wi-Fi, backend, or Deep Sleep.
7. Fails closed on ADC/inference errors instead of reporting clean background.
"""

import ast
import base64
import importlib.util
from pathlib import Path

MICROPYTHON_ROOT = Path(__file__).resolve().parents[1]
BURST_MODEL_SRC = MICROPYTHON_ROOT / 'firmware' / 'lib' / 'tg_model_burst.py'
V46_MODEL_SRC = (
    MICROPYTHON_ROOT / 'algorithm' / 'results' / 'v4_6_wideband' / 'tg_model_v46.py'
)
DEPLOY_DIR = MICROPYTHON_ROOT / 'deploy'


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _format_bytes_literal(data, indent='    ', chunk=48):
    lines = ['(']
    for i in range(0, len(data), chunk):
        lines.append(indent + '    ' + repr(data[i:i + chunk]))
    lines.append(indent + ')')
    return '\n'.join(lines)


def _format_float_tuple(values, digits=9):
    parts = [repr(round(float(v), digits)) for v in values]
    return '(' + ', '.join(parts) + ')'


COMPACT_BURST_HEADER = '''import machine
from machine import Pin, ADC
from network import WLAN
import usocket as socket
import time
import ubinascii
import struct
import pycom
import gc

try:
    pycom.heartbeat(False)
except Exception:
    pass

WIFI_SSID = "TWOJE_SSID"
WIFI_HASLO = "TWOJE_HASLO"
API_URL = "http://srv18.mikr.us:20376"
DEVICE_ID = "70B3D57ED00D0009"
INGEST_KEY = ""

PIN_MIKROFON_ID = "P19"
PIN_MIKROFON_ADC_ID = "P16"
PIN_DRGANIA_ID = "P20"
CZAS_SNU_SZTYWNEGO_MS = 600000
FIRMWARE_VER = 1

CZAS_NAGRANIA_S = 10
CZESTOTLIWOSC_HZ = 4000
ROZMIAR_BLOKU_PROBEK = 4000
DOMYSLNY_CZAS_S = 1
DOMYSLNA_ENERGIA = 120

PROTO_VERSION = 2
MSG_ALARM = 1
MSG_HEARTBEAT = 2
MSG_BOOT = 3


def rozbierz_url(url):
    if not url.startswith("http://"):
        raise ValueError("API_URL")
    r = url[7:]
    i = r.find("/")
    a, p = (r, "") if i < 0 else (r[:i], r[i:].rstrip("/"))
    j = a.find(":")
    return (a, 80, p) if j < 0 else (a[:j], int(a[j + 1:]), p)


HOST, PORT, PREFIKS = rozbierz_url(API_URL)


def polacz_wifi():
    wlan = WLAN(mode=WLAN.STA)
    if wlan.isconnected():
        return
    wlan.connect(WIFI_SSID, auth=(WLAN.WPA2, WIFI_HASLO), timeout=10000)
    for _ in range(20):
        if wlan.isconnected():
            return
        time.sleep(0.5)
    raise OSError("WiFi timeout")


def odchunkuj(t):
    w = b""
    while True:
        j = t.find(b"\\r\\n")
        if j < 0:
            return w
        try:
            n = int(t[:j].split(b";")[0], 16)
        except ValueError:
            return w
        if n == 0:
            return w
        w += t[j + 2:j + 2 + n]
        t = t[j + 2 + n + 2:]


def wyslij_payload(ramka):
    hx = ubinascii.hexlify(ramka).decode()
    body = '{"device": "' + DEVICE_ID + '", "payload_hex": "' + hx + '"}'
    h = HOST if PORT == 80 else HOST + ":" + str(PORT)
    req = (
        "POST " + PREFIKS + "/api/v1/ingest HTTP/1.1\\r\\nHost: " + h
        + "\\r\\nUser-Agent: detektor-lopy\\r\\nConnection: close"
        + "\\r\\nContent-Type: application/json\\r\\nX-Ingest-Key: " + INGEST_KEY
        + "\\r\\nContent-Length: " + str(len(body)) + "\\r\\n\\r\\n" + body
    )
    addr = socket.getaddrinfo(HOST, PORT)[0][-1]
    s = socket.socket()
    s.settimeout(15)
    try:
        s.connect(addr)
        d = req.encode()
        while d:
            n = s.send(d)
            if not n:
                raise OSError("send")
            d = d[n:]
        resp = b""
        while True:
            c = s.recv(512)
            if not c:
                break
            resp += c
    finally:
        try:
            s.close()
        except Exception:
            pass
    i = resp.find(b"\\r\\n\\r\\n")
    if i < 0:
        return False
    hdr, tr = resp[:i], resp[i + 4:]
    parts = hdr.split(b"\\r\\n", 1)[0].split(b" ")
    if len(parts) < 2:
        return False
    try:
        kod = int(parts[1])
    except ValueError:
        return False
    if b"transfer-encoding: chunked" in hdr.lower():
        tr = odchunkuj(tr)
    print("TX:", kod)
    return 200 <= kod < 300


def inicjalizuj_pin(pid):
    try:
        return Pin(pid, mode=Pin.IN, pull=Pin.PULL_DOWN)
    except ValueError:
        return Pin(pid, mode=Pin.IN, pull=None)


try:
    pin_mic = inicjalizuj_pin(PIN_MIKROFON_ID)
    pin_vib = inicjalizuj_pin(PIN_DRGANIA_ID)
except Exception as e:
    print("Pin err:", e)
    pin_mic = None
    pin_vib = None


def nagraj_audio(pin_id=PIN_MIKROFON_ADC_ID, czas_s=CZAS_NAGRANIA_S,
                 fs_hz=CZESTOTLIWOSC_HZ, blok_probek=ROZMIAR_BLOKU_PROBEK):
    gc.collect()
    nb = (czas_s * fs_hz) // blok_probek
    okres = 1000000 // fs_hz
    try:
        adc = ADC(bits=12)
    except TypeError:
        adc = ADC(0)
    apin = adc.channel(pin=pin_id, attn=ADC.ATTN_11DB)
    buf = bytearray(blok_probek * 2)
    for _ in range(nb):
        tn = time.ticks_us()
        idx = 0
        for _ in range(blok_probek):
            v = apin()
            buf[idx] = v & 0xFF
            buf[idx + 1] = (v >> 8) & 0xFF
            idx += 2
            tn = time.ticks_add(tn, okres)
            while time.ticks_diff(tn, time.ticks_us()) > 0:
                pass
        yield buf


def analizuj_sygnaly(mic_aktywny, vib_aktywny):
'''

COMPACT_BURST_FOOTER = '''

def _nvs_inc(k, skip_zero=False):
    try:
        v = pycom.nvs_get(k)
        v = 0 if v is None else v
    except (ValueError, OSError):
        v = 0
    v = (v + 1) & 0xFFFF
    if skip_zero and v == 0:
        v = 1
    try:
        pycom.nvs_set(k, v)
    except Exception:
        pass
    return v


def _naglowek(mt):
    return struct.pack(">BH", ((PROTO_VERSION & 0x0F) << 4) | (mt & 0x0F), _nvs_inc("pkt_cnt"))


def przygotuj_ramke_alarm(event_type=1, confidence=100, battery_pct=100,
                          source_bits=0, duration_s=DOMYSLNY_CZAS_S, energy=DOMYSLNA_ENERGIA):
    return _naglowek(MSG_ALARM) + struct.pack(
        ">BBBHBB",
        max(0, min(255, int(event_type))),
        max(0, min(255, int(source_bits))),
        max(0, min(100, int(confidence))),
        max(0, min(65535, int(duration_s))),
        max(0, min(255, int(energy))),
        max(0, min(100, int(battery_pct))),
    )


def przygotuj_ramke_heartbeat(battery_pct=100, rejected_events=0, flags=0):
    return _naglowek(MSG_HEARTBEAT) + struct.pack(
        ">BBB",
        max(0, min(100, int(battery_pct))),
        max(0, min(255, int(rejected_events))),
        max(0, min(255, int(flags))),
    )


def przygotuj_ramke_boot(boot_id, firmware_version=FIRMWARE_VER, reset_reason=1, battery_pct=100):
    return _naglowek(MSG_BOOT) + struct.pack(
        ">BBBH", firmware_version, reset_reason, max(0, min(100, int(battery_pct))), boot_id
    )


def idz_spac_na_sztywno(czas_ms):
    try:
        machine.pin_sleep_wakeup(None, machine.WAKEUP_ANY_HIGH, False)
    except Exception:
        try:
            machine.pin_sleep_wakeup([], machine.WAKEUP_ANY_HIGH, False)
        except Exception:
            pass
    time.sleep(0.05)
    machine.deepsleep(czas_ms)


def idz_spac_na_czujniki():
    for _ in range(20):
        if not ((pin_mic and pin_mic.value() == 1) or (pin_vib and pin_vib.value() == 1)):
            break
        time.sleep(0.1)
    if (pin_mic and pin_mic.value() == 1) or (pin_vib and pin_vib.value() == 1):
        idz_spac_na_sztywno(CZAS_SNU_SZTYWNEGO_MS)
        return
    bez = ("P13", "P14", "P15", "P16", "P17", "P18")
    pull = (PIN_MIKROFON_ID not in bez) and (PIN_DRGANIA_ID not in bez)
    try:
        machine.pin_sleep_wakeup([PIN_MIKROFON_ID, PIN_DRGANIA_ID], mode=machine.WAKEUP_ANY_HIGH, enable_pull=pull)
    except Exception as e:
        print("Wake cfg err:", e)
        idz_spac_na_sztywno(CZAS_SNU_SZTYWNEGO_MS)
        return
    time.sleep(0.05)
    machine.deepsleep()


def main():
    wi = machine.wake_reason()
    pw = wi[0] if wi else -1
    if pw == machine.RTC_WAKE:
        gc.collect()
        try:
            polacz_wifi()
            wyslij_payload(przygotuj_ramke_heartbeat(100, 0, 0))
        except Exception as e:
            print("HB err:", e)
        idz_spac_na_czujniki()
    elif pw == machine.PIN_WAKE:
        pl = wi[1] if len(wi) > 1 and wi[1] else ()
        ids = [(p.id() if hasattr(p, "id") else str(p)) for p in pl]
        mic = (pin_mic is not None and pin_mic.value() == 1) or (PIN_MIKROFON_ID in ids)
        vib = (pin_vib is not None and pin_vib.value() == 1) or (PIN_DRGANIA_ID in ids)
        czy_alarm = False
        event_type = 0
        confidence = 0
        try:
            czy_alarm, event_type, confidence = analizuj_sygnaly(mic, vib)
        except Exception as e:
            print("Det err:", e)
        gc.collect()
        if czy_alarm:
            sb = (1 if czy_alarm else 0) | (2 if vib else 0)
            try:
                polacz_wifi()
                wyslij_payload(przygotuj_ramke_alarm(event_type, confidence, 100, sb))
            except Exception as e:
                print("Alarm err:", e)
        idz_spac_na_sztywno(CZAS_SNU_SZTYWNEGO_MS)
    else:
        ramka = przygotuj_ramke_boot(_nvs_inc("boot_id", True), FIRMWARE_VER, 1, 100)
        gc.collect()
        try:
            polacz_wifi()
            wyslij_payload(ramka)
        except Exception as e:
            print("Boot err:", e)
        idz_spac_na_czujniki()


if __name__ == "__main__":
    main()
'''


FIRMWARE_HEADER = '''"""Standalone Pycom LoPy 1.0 wood-theft detection firmware ({variant_label}).

Target: Pycom LoPy 1.0 (ESP32 @ 160 MHz), Pycom 1.20.2.r6, MicroPython v1.11 (c5a0a97).
Hardware note: `nagraj_audio()` requires an ANALOG microphone (AO -> P16, DO -> P19).
Pycom 1.20.2.r6 does NOT expose `machine.I2S`; digital I2S microphones are unsupported
by ADC capture. Use `tryb_diagnostyczny()` via REPL to run synthetic ADC self-tests.
"""
import machine
from machine import Pin, ADC
from network import WLAN
import usocket as socket
import time
import ubinascii
import struct
import pycom
import gc

try:
    pycom.heartbeat(False)
except Exception:
    pass

# ================= KONFIGURACJA =================
WIFI_SSID = "TWOJE_SSID"
WIFI_HASLO = "TWOJE_HASLO"
API_URL = "http://srv18.mikr.us:20376"
DEVICE_ID = "70B3D57ED00D0009"
INGEST_KEY = ""

PIN_MIKROFON_ID = "P19"      # Wyjscie cyfrowe (DO) mikrofonu analogowego (wybudzanie)
PIN_MIKROFON_ADC_ID = "P16"  # Wyjscie analogowe (AO) mikrofonu (ADC1: P13-P20)
PIN_DRGANIA_ID = "P20"       # Czujnik drgan (binarna metadana wybudzania)
CZAS_SNU_SZTYWNEGO_MS = 600000
FIRMWARE_VER = 1
TRYB_DIAGNOSTYCZNY = False   # Ustaw True tylko do testow bez sieci i Deep Sleep

# Parametry nagrywania audio (kontrakt zgodny z firmware/main4.py)
CZAS_NAGRANIA_S = 10
CZESTOTLIWOSC_HZ = 4000
ROZMIAR_BLOKU_PROBEK = 4000  # 1 s = 4000 probek = 8000 bajtow (8 KB RAM)
MAX_GAP_MS = 1500            # Przerwa miedzy blokami resetujaca okno 2 s

# Stale domyslne dla backendu (V2)
DOMYSLNY_CZAS_S = 1
DOMYSLNA_ENERGIA = 120
SOURCE_BIT_MIC = 0x01
SOURCE_BIT_VIB = 0x02

# ================= PROTOKOL (V2) =================
PROTO_VERSION = 2
MSG_ALARM = 1
MSG_HEARTBEAT = 2
MSG_BOOT = 3

# Ostatnie metadane sesji V2 (aktualizowane przez analizuj_sygnaly)
_OSTATNI_WYNIK = {{
    "source_bits": 0,
    "duration_s": DOMYSLNY_CZAS_S,
    "energy": DOMYSLNA_ENERGIA,
    "inference_ok": False,
    "blocks": 0,
}}
_ZRODLO_AUDIO_OVERRIDE = None


# ================= LOGIKA SIECIOWA (WI-FI / HTTP) =================
def rozbierz_url(url):
    if not url.startswith("http://"):
        raise ValueError("API_URL musi zaczynac sie od http://")
    reszta = url[len("http://"):]
    i = reszta.find("/")
    adres, prefiks = (reszta, "") if i < 0 else (reszta[:i], reszta[i:].rstrip("/"))
    j = adres.find(":")
    if j < 0:
        return adres, 80, prefiks
    return adres[:j], int(adres[j + 1:]), prefiks


HOST, PORT, PREFIKS = rozbierz_url(API_URL)


def polacz_wifi(timeout_ms=10000):
    wlan = WLAN(mode=WLAN.STA)
    if wlan.isconnected():
        return True
    try:
        wlan.connect(WIFI_SSID, auth=(WLAN.WPA2, WIFI_HASLO), timeout=timeout_ms)
    except Exception as e:
        raise OSError("Blad inicjalizacji Wi-Fi: " + str(e))
    kroki = max(1, (timeout_ms + 499) // 500)
    for _ in range(kroki):
        if wlan.isconnected():
            print("Wi-Fi OK, IP:", wlan.ifconfig()[0])
            return True
        time.sleep(0.5)
    raise OSError("Brak polaczenia z Wi-Fi (timeout)")


def odchunkuj(tresc):
    wynik = b""
    while True:
        j = tresc.find(b"\\r\\n")
        if j < 0:
            return wynik
        try:
            n = int(tresc[:j].split(b";")[0], 16)
        except ValueError:
            return wynik
        if n == 0:
            return wynik
        wynik += tresc[j + 2:j + 2 + n]
        tresc = tresc[j + 2 + n + 2:]


def wyslij_payload(ramka):
    payload_hex = ubinascii.hexlify(ramka).decode()
    body = '{{"device": "' + DEVICE_ID + '", "payload_hex": "' + payload_hex + '"}}'
    host_naglowek = HOST if PORT == 80 else HOST + ":" + str(PORT)
    zapytanie = (
        "POST " + PREFIKS + "/api/v1/ingest HTTP/1.1\\r\\n"
        + "Host: " + host_naglowek + "\\r\\n"
        + "User-Agent: detektor-lopy\\r\\n"
        + "Connection: close\\r\\n"
        + "Content-Type: application/json\\r\\n"
        + "X-Ingest-Key: " + INGEST_KEY + "\\r\\n"
        + "Content-Length: " + str(len(body)) + "\\r\\n"
        + "\\r\\n" + body
    )

    adres = socket.getaddrinfo(HOST, PORT)[0][-1]
    s = socket.socket()
    s.settimeout(15)
    try:
        s.connect(adres)
        dane = zapytanie.encode()
        while dane:
            wyslano = s.send(dane)
            if not wyslano:
                raise OSError("Przerwane wysylanie HTTP")
            dane = dane[wyslano:]
        odpowiedz = b""
        while True:
            kawalek = s.recv(512)
            if not kawalek:
                break
            odpowiedz += kawalek
    finally:
        try:
            s.close()
        except Exception:
            pass

    i = odpowiedz.find(b"\\r\\n\\r\\n")
    if i < 0:
        print("Niepoprawna odpowiedz HTTP (brak naglowkow)")
        return False
    naglowki, tresc = odpowiedz[:i], odpowiedz[i + 4:]
    linia_statusu = naglowki.split(b"\\r\\n", 1)[0].split(b" ")
    if len(linia_statusu) < 2:
        print("Niepoprawna linia statusu HTTP:", linia_statusu)
        return False
    try:
        kod = int(linia_statusu[1])
    except ValueError:
        print("Niepoprawny kod HTTP:", linia_statusu[1])
        return False
    if b"transfer-encoding: chunked" in naglowki.lower():
        tresc = odchunkuj(tresc)
    try:
        tresc_txt = tresc.decode()
    except Exception:
        tresc_txt = repr(tresc)
    print("Wyslano:", payload_hex.upper(), "->", kod, tresc_txt)
    return 200 <= kod < 300


# ================= CZUJNIKI, AUDIO I ANALIZA =================
def inicjalizuj_pin(pin_id):
    try:
        return Pin(pin_id, mode=Pin.IN, pull=Pin.PULL_DOWN)
    except ValueError:
        return Pin(pin_id, mode=Pin.IN, pull=None)


try:
    pin_mic = inicjalizuj_pin(PIN_MIKROFON_ID)
    pin_vib = inicjalizuj_pin(PIN_DRGANIA_ID)
except Exception as _pin_err:
    print("Blad inicjalizacji pinow wybudzania:", _pin_err)
    pin_mic = None
    pin_vib = None


def nagraj_audio(pin_id=PIN_MIKROFON_ADC_ID, czas_s=CZAS_NAGRANIA_S,
                 fs_hz=CZESTOTLIWOSC_HZ, blok_probek=ROZMIAR_BLOKU_PROBEK):
    gc.collect()
    liczba_blokow = (czas_s * fs_hz) // blok_probek
    okres_us = 1000000 // fs_hz

    try:
        adc = ADC(bits=12)
    except TypeError:
        adc = ADC(0)
    apin = adc.channel(pin=pin_id, attn=ADC.ATTN_11DB)

    # Jeden bufor 8 KB uzywany wielokrotnie (bez ponownych alokacji)
    bufor = bytearray(blok_probek * 2)

    print("Start nagrywania (%d blokow po %d probek)..." % (liczba_blokow, blok_probek))
    for _ in range(liczba_blokow):
        t_nastepna = time.ticks_us()
        idx = 0
        for _ in range(blok_probek):
            val = apin()
            bufor[idx] = val & 0xFF
            bufor[idx + 1] = (val >> 8) & 0xFF
            idx += 2

            t_nastepna = time.ticks_add(t_nastepna, okres_us)
            while time.ticks_diff(t_nastepna, time.ticks_us()) > 0:
                pass

        yield bufor


def analizuj_sygnaly(mic_aktywny, vib_aktywny):
'''

FIRMWARE_FOOTER = '''

# ================= PAMIEC NIEULOTNA (NVS) I RAMKI =================
def _nvs_odczytaj(klucz, domyslna=0):
    try:
        val = pycom.nvs_get(klucz)
        if val is None:
            return domyslna
        return val
    except (ValueError, OSError):
        # Normalny stan przy pierwszym uruchomieniu przed zapisem klucza
        return domyslna
    except Exception as e:
        print("Blad odczytu NVS (%s):" % klucz, e)
        return domyslna


def _nvs_zapisz(klucz, wartosc):
    try:
        pycom.nvs_set(klucz, wartosc)
        return True
    except Exception as e:
        print("Blad zapisu NVS (%s):" % klucz, e)
        return False


def _pobierz_licznik():
    cnt = (_nvs_odczytaj("pkt_cnt", 0) + 1) & 0xFFFF
    _nvs_zapisz("pkt_cnt", cnt)
    return cnt


def _pobierz_boot_id():
    bid = (_nvs_odczytaj("boot_id", 0) + 1) & 0xFFFF
    if bid == 0:
        bid = 1
    _nvs_zapisz("boot_id", bid)
    return bid


def _naglowek(msg_type):
    first_byte = ((PROTO_VERSION & 0x0F) << 4) | (msg_type & 0x0F)
    return struct.pack(">BH", first_byte, _pobierz_licznik())


def przygotuj_ramke_alarm(event_type=1, confidence=100, battery_pct=100,
                          source_bits=0, duration_s=DOMYSLNY_CZAS_S, energy=DOMYSLNA_ENERGIA):
    event_type = max(0, min(255, int(event_type)))
    source_bits = max(0, min(255, int(source_bits)))
    confidence = max(0, min(100, int(confidence)))
    battery_pct = max(0, min(100, int(battery_pct)))
    duration_s = max(0, min(65535, int(duration_s)))
    energy = max(0, min(255, int(energy)))
    body = struct.pack(">BBBHBB", event_type, source_bits, confidence, duration_s, energy, battery_pct)
    return _naglowek(MSG_ALARM) + body


def przygotuj_ramke_heartbeat(battery_pct=100, rejected_events=0, flags=0):
    battery_pct = max(0, min(100, int(battery_pct)))
    rejected_events = max(0, min(255, int(rejected_events)))
    flags = max(0, min(255, int(flags)))
    body = struct.pack(">BBB", battery_pct, rejected_events, flags)
    return _naglowek(MSG_HEARTBEAT) + body


def przygotuj_ramke_boot(boot_id, firmware_version=FIRMWARE_VER, reset_reason=1, battery_pct=100):
    battery_pct = max(0, min(100, int(battery_pct)))
    body = struct.pack(">BBBH", firmware_version, reset_reason, battery_pct, boot_id)
    return _naglowek(MSG_BOOT) + body


# ================= TRYBY ZASILANIA (Pycom 1.20.2.r6) =================
def _wylacz_wybudzanie_pinami():
    try:
        machine.pin_sleep_wakeup(None, machine.WAKEUP_ANY_HIGH, False)
    except Exception:
        try:
            machine.pin_sleep_wakeup([], machine.WAKEUP_ANY_HIGH, False)
        except Exception as e:
            print("Ostrzezenie pin_sleep_wakeup(clear):", e)


def _piny_aktywne_wysoko():
    mic_hi = pin_mic is not None and pin_mic.value() == 1
    vib_hi = pin_vib is not None and pin_vib.value() == 1
    return mic_hi or vib_hi


def idz_spac_na_czujniki():
    # Ochrona przed nieskonczona petla wybudzen przy stale wysokim stanie pinu
    for _ in range(20):
        if not _piny_aktywne_wysoko():
            break
        time.sleep(0.1)
    if _piny_aktywne_wysoko():
        print("Uwaga: pin wybudzania stale HIGH — przejscie w sen czasowy")
        idz_spac_na_sztywno(CZAS_SNU_SZTYWNEGO_MS)
        return

    piny_bez_pull = ("P13", "P14", "P15", "P16", "P17", "P18")
    czy_pull = (PIN_MIKROFON_ID not in piny_bez_pull) and (PIN_DRGANIA_ID not in piny_bez_pull)
    piny_budzenia = [PIN_MIKROFON_ID, PIN_DRGANIA_ID]

    try:
        machine.pin_sleep_wakeup(
            piny_budzenia,
            mode=machine.WAKEUP_ANY_HIGH,
            enable_pull=czy_pull,
        )
    except Exception as e:
        print("Blad konfiguracji pin_sleep_wakeup:", e)
        idz_spac_na_sztywno(CZAS_SNU_SZTYWNEGO_MS)
        return

    time.sleep(0.05)
    machine.deepsleep()


def idz_spac_na_sztywno(czas_ms):
    _wylacz_wybudzanie_pinami()
    time.sleep(0.05)
    machine.deepsleep(czas_ms)


def _wyslij_bezpiecznie(ramka, etykieta):
    gc.collect()
    try:
        polacz_wifi()
        ok = wyslij_payload(ramka)
        if not ok:
            print("Ostrzezenie: backend odrzucil ramke (%s)" % etykieta)
        return ok
    except Exception as e:
        print("Blad wysylania %s:" % etykieta, e)
        return False


def _czy_pin_na_liscie(piny, pin_id):
    if not piny:
        return False
    for p in piny:
        pid = p.id() if hasattr(p, "id") else str(p)
        if pid == pin_id:
            return True
    return False


# ================= TRYB DIAGNOSTYCZNY (SYNTHETIC ADC) =================
def _syntetyczne_audio(liczba_blokow=CZAS_NAGRANIA_S):
    import math
    bufor = bytearray(ROZMIAR_BLOKU_PROBEK * 2)
    lut = [int(900.0 * math.sin(2.0 * math.pi * k / 64.0)) for k in range(64)]
    for blk in range(liczba_blokow):
        idx = 0
        phase = (blk * ROZMIAR_BLOKU_PROBEK) & 63
        for _ in range(ROZMIAR_BLOKU_PROBEK):
            s1 = lut[phase]
            s2 = lut[(phase * 2) & 63]
            raw = 2048 + ((s1 * 3 + s2) >> 2)
            if raw < 0:
                raw = 0
            elif raw > 4095:
                raw = 4095
            bufor[idx] = raw & 0xFF
            bufor[idx + 1] = (raw >> 8) & 0xFF
            idx += 2
            phase = (phase + 1) & 63
        yield bufor


def tryb_diagnostyczny(liczba_blokow=CZAS_NAGRANIA_S, vib_aktywny=False):
    """Samodzielny test detekcji bez mikrofonu, Wi-Fi, backendu i Deep Sleep."""
    global _ZRODLO_AUDIO_OVERRIDE
    gc.collect()
    heap_start = gc.mem_free() if hasattr(gc, "mem_free") else -1
    print("=== TRYB DIAGNOSTYCZNY (bloki=%d, heap_start=%d) ===" % (liczba_blokow, heap_start))
    t0 = time.ticks_ms() if hasattr(time, "ticks_ms") else 0
    _ZRODLO_AUDIO_OVERRIDE = lambda: _syntetyczne_audio(liczba_blokow)
    try:
        czy_alarm, event_type, confidence = analizuj_sygnaly(True, vib_aktywny)
    finally:
        _ZRODLO_AUDIO_OVERRIDE = None
    dt = time.ticks_diff(time.ticks_ms(), t0) if hasattr(time, "ticks_diff") else 0
    gc.collect()
    heap_end = gc.mem_free() if hasattr(gc, "mem_free") else -1
    print("DIAG_TIME_MS:", dt)
    print("DIAG_HEAP_END:", heap_end)
    print("DIAG_RESULT:", (czy_alarm, event_type, confidence))
    print("DIAG_META:", _OSTATNI_WYNIK)
    print("=== KONIEC TRYBU DIAGNOSTYCZNEGO (brak Wi-Fi, brak Deep Sleep) ===")
    return czy_alarm, event_type, confidence


# ================= GLOWNA MASZYNA STANOW =================
def main():
    if TRYB_DIAGNOSTYCZNY:
        tryb_diagnostyczny()
        return

    wake_info = machine.wake_reason()
    powod = wake_info[0] if wake_info else -1

    # STAN 1: Wybudzenie z timera (RTC)
    if powod == machine.RTC_WAKE:
        ramka_hb = przygotuj_ramke_heartbeat(battery_pct=100, rejected_events=0, flags=0)
        _wyslij_bezpiecznie(ramka_hb, "Heartbeat")
        idz_spac_na_czujniki()

    # STAN 2: Wybudzenie z czujnikow (PIN)
    elif powod == machine.PIN_WAKE:
        piny_wybudzajace = wake_info[1] if len(wake_info) > 1 and wake_info[1] else []
        mic_aktywny = (pin_mic is not None and pin_mic.value() == 1) or _czy_pin_na_liscie(
            piny_wybudzajace, PIN_MIKROFON_ID
        )
        vib_aktywny = (pin_vib is not None and pin_vib.value() == 1) or _czy_pin_na_liscie(
            piny_wybudzajace, PIN_DRGANIA_ID
        )

        # Pojedyncza sesja akwizycji i analizy audio (bez podwojnego nagrywania)
        czy_alarm = False
        event_type = 0
        confidence = 0
        try:
            czy_alarm, event_type, confidence = analizuj_sygnaly(mic_aktywny, vib_aktywny)
        except Exception as e:
            print("Blad analizy audio (fail-closed, brak alarmu):", e)
            czy_alarm = False
        finally:
            gc.collect()

        if czy_alarm and _OSTATNI_WYNIK.get("inference_ok"):
            ramka = przygotuj_ramke_alarm(
                event_type=event_type,
                confidence=confidence,
                battery_pct=100,
                source_bits=_OSTATNI_WYNIK.get("source_bits", 0),
                duration_s=_OSTATNI_WYNIK.get("duration_s", DOMYSLNY_CZAS_S),
                energy=_OSTATNI_WYNIK.get("energy", DOMYSLNA_ENERGIA),
            )
            _wyslij_bezpiecznie(ramka, "Alarm")

        idz_spac_na_sztywno(CZAS_SNU_SZTYWNEGO_MS)

    # STAN 3: Zimny start (Zasilanie / Reset)
    else:
        boot_id = _pobierz_boot_id()
        ramka_boot = przygotuj_ramke_boot(
            boot_id=boot_id,
            firmware_version=FIRMWARE_VER,
            reset_reason=1,
            battery_pct=100,
        )
        _wyslij_bezpiecznie(ramka_boot, "Boot")
        idz_spac_na_czujniki()


if __name__ == "__main__":
    main()
'''


def _build_burst_body(model):
    weights_lit = _format_bytes_literal(bytes(model.WEIGHTS), indent='    ', chunk=80)
    mean_lit = _format_float_tuple(model.MEAN, digits=6)
    inv_std_lit = _format_float_tuple(model.INVERSE_STD, digits=6)
    scales_lit = _format_float_tuple(model.SCALES, digits=7)
    biases_lit = _format_float_tuple(model.BIASES, digits=6)

    return """    from array import array
    import math
    N = {burst_samples}
    B = 15
    INP = {inputs}
    HID = {hidden}
    TH = {threshold}
    REQ = {required}
    MN = {mean_lit}
    IS = {inv_std_lit}
    SC = {scales_lit}
    BI = {biases_lit}
    WT = {weights_lit}

    def _z(tc, sz):
        a = array(tc, range(sz))
        z = 0.0 if tc == 'f' else 0
        for i in range(sz):
            a[i] = z
        return a

    pcm = _z('h', N)
    re = _z('f', N)
    im = _z('f', N)
    hn = N // 2
    ct = _z('f', hn)
    st = _z('f', hn)
    hw = _z('f', N)
    rv = _z('H', N)
    for k in range(hn):
        ag = 2.0 * math.pi * k / N
        ct[k] = math.cos(ag)
        st[k] = -math.sin(ag)
    for i in range(N):
        hw[i] = 0.5 - 0.5 * math.cos(2.0 * math.pi * i / (N - 1))
    for i in range(1, N):
        rv[i] = (rv[i >> 1] >> 1) | ((i & 1) * hn)
    bins = (4, 9, 13, 19, 26, 34, 45, 57, 71, 88, 106, 127, 152, 178, 209, 244)
    fr = _z('f', 128)
    ft = _z('f', 32)
    xv = _z('f', INP)

    cur = 0
    vf = 0
    blks = 0
    pos = 0
    nsc = 0
    stk = 0
    mstk = 0
    msc = 0.0
    mcsc = 0.0
    imp = 0
    prms = None
    lend = None
    htk = hasattr(time, "ticks_ms") and hasattr(time, "ticks_diff")

    for blk in nagraj_audio():
        if len(blk) != 8000:
            raise ValueError("blk")
        if htk:
            ts = time.ticks_ms()
            if lend is not None and time.ticks_diff(ts, lend) - 1000 > 1500:
                cur = 0
                vf = 0
                stk = 0
        rsq = 0.0
        mxr = 0.0
        mnr = 1.0
        mxc = 0.0
        for f in range(4):
            bi = f * 2000
            sm = 0.0
            for i in range(N):
                raw = blk[bi] | (blk[bi + 1] << 8)
                bi += 2
                if raw > 4095:
                    raw = 4095
                sp = (raw << 4) - 32768
                pcm[i] = sp
                sm += sp
            mn = sm / float(N)
            msq = 0.0
            pk = 0.0
            for i in range(N):
                v = float(pcm[i]) - mn
                av = -v if v < 0.0 else v
                if av > pk:
                    pk = av
                msq += v * v
                j = rv[i]
                re[j] = v * hw[i]
                im[j] = 0.0
            rp = math.sqrt(msq / float(N))
            nr = rp / 32768.0
            cr = pk / (rp + 1e-6)
            rsq += nr * nr
            if nr > mxr:
                mxr = nr
            if nr < mnr:
                mnr = nr
            if cr > mxc:
                mxc = cr
            w = 2
            while w <= N:
                h = w // 2
                sd = N // w
                for s0 in range(0, N, w):
                    for k in range(h):
                        i = s0 + k
                        j = i + h
                        tw = k * sd
                        c = ct[tw]
                        s = st[tw]
                        u = re[j]
                        v = im[j]
                        r = c * u - s * v
                        q = s * u + c * v
                        re[j] = re[i] - r
                        im[j] = im[i] - q
                        re[i] += r
                        im[i] += q
                w *= 2
            off = cur * 16
            ctr = 0.0
            for b in range(B):
                a0 = bins[b]
                a1 = bins[b + 1]
                pw = 0.0
                for k in range(a0, a1):
                    pw += re[k] * re[k] + im[k] * im[k]
                vl = math.log(pw / (a1 - a0) + 1e-6)
                ctr += vl
                fr[off + b] = vl
            ctr /= 15.0
            for b in range(B):
                ix = off + b
                v = fr[ix] - ctr
                fr[ix] = -10.0 if v < -10.0 else (10.0 if v > 10.0 else v)
            fr[off + B] = math.log(nr + 1e-7)
            cur = (cur + 1) & 7
            if vf < 8:
                vf += 1

        blks += 1
        brms = math.sqrt(rsq * 0.25)
        if mxr >= 0.035:
            br = mnr if mnr > 1e-5 else 1e-5
            if prms is not None and prms < br:
                br = prms if prms > 1e-5 else 1e-5
            if mxc >= 5.5 or (mxr / br) >= 3.0:
                imp += 1
        prms = brms

        if vf == 8:
            for ch in range(16):
                tot = 0.0
                sq = 0.0
                for k in range(8):
                    fv = fr[k * 16 + ch]
                    tot += fv
                    sq += fv * fv
                mv = tot * 0.125
                sv = math.sqrt(max(0.0, sq * 0.125 - mv * mv))
                if ch < B:
                    ft[ch] = mv
                    ft[B + ch] = sv
                else:
                    ft[30] = sv
                    ft[31] = mv
            for i in range(INP):
                z = (ft[i] - MN[i]) * IS[i]
                xv[i] = -6.0 if z < -6.0 else (6.0 if z > 6.0 else z)
            lg = 0.0
            sc0 = SC[0]
            for u in range(HID or 1):
                wo = u * INP
                ac = 0.0
                for i in range(INP):
                    wb = WT[wo + i]
                    ac += xv[i] * (wb if wb < 128 else wb - 256)
                vl = ac * sc0 + BI[u]
                if HID:
                    if vl > 0.0:
                        wb2 = WT[HID * INP + u]
                        lg += vl * (wb2 if wb2 < 128 else wb2 - 256)
                else:
                    lg = vl
            if HID:
                lg = lg * SC[1] + BI[-1]
            lg = -30.0 if lg < -30.0 else (30.0 if lg > 30.0 else lg)
            sc = 1.0 / (1.0 + math.exp(-lg))
            nsc += 1
            if sc > msc:
                msc = sc
            if sc >= TH:
                pos += 1
                stk += 1
                if stk > mstk:
                    mstk = stk
                if stk >= REQ and sc > mcsc:
                    mcsc = sc
            else:
                stk = 0
        if htk:
            lend = time.ticks_ms()

    if blks == 0:
        raise RuntimeError("No audio")
    eng = mstk >= REQ
    czy_alarm = bool(eng)
    event_type = 1 if czy_alarm else 0
    if nsc == 0:
        confidence = 0
    elif not eng:
        r = msc / TH
        confidence = int(round((1.0 if r > 1.0 else r) * 40.0))
    else:
        rf = mcsc if mcsc > 0.0 else msc
        mg = (rf - TH) / max(1e-6, 1.0 - TH)
        mg = 0.0 if mg < 0.0 else (1.0 if mg > 1.0 else mg)
        cf = 55.0 + 25.0 * mg + 10.0 * (float(pos) / float(nsc))
        if imp > 0:
            cf += 5.0
        if vib_aktywny:
            cf += 5.0
        confidence = max(0, min(100, int(round(cf))))
    return czy_alarm, event_type, confidence""".format(
        burst_samples=int(model.BURST_SAMPLES),
        inputs=int(model.INPUTS),
        hidden=int(model.HIDDEN),
        threshold=repr(float(model.THRESHOLD)),
        required=int(model.REQUIRED),
        mean_lit=mean_lit,
        inv_std_lit=inv_std_lit,
        scales_lit=scales_lit,
        biases_lit=biases_lit,
        weights_lit=weights_lit,
    )


def _build_v46_body(model):
    wc = base64.b64decode(model.WEIGHT_B64[0])
    wd = base64.b64decode(model.WEIGHT_B64[1])
    wo = base64.b64decode(model.WEIGHT_B64[2])

    channels = int(model.CONV_CHANNELS)
    hidden_n = int(model.HIDDEN)
    pool_size = 12 * channels + 9
    assert len(wc) == 9 * channels
    assert len(wd) == pool_size * hidden_n
    assert len(wo) == hidden_n

    wc_lit = _format_bytes_literal(wc, indent='    ')
    wd_lit = _format_bytes_literal(wd, indent='    ')
    wo_lit = _format_bytes_literal(wo, indent='    ')

    mean_lit = _format_float_tuple(model.MEAN)
    inv_std_lit = _format_float_tuple(model.INV_STD)
    e_mean_lit = _format_float_tuple(model.E_MEAN)
    e_inv_std_lit = _format_float_tuple(model.E_INV_STD)
    scales_lit = _format_float_tuple(model.SCALES)
    b0_lit = _format_float_tuple(model.BIASES[0])
    b1_lit = _format_float_tuple(model.BIASES[1])
    b2_lit = repr(round(float(model.BIASES[2][0]), 9))

    return """    from array import array
    import math

    _OSTATNI_WYNIK["inference_ok"] = False
    _OSTATNI_WYNIK["blocks"] = 0

    # Embedded CNN v4.6 parameters (unmodified INT8 weights as raw bytes literals)
    SAMPLE_RATE = 4000
    BLOCK_BYTES = 8000
    FFT_N = 1024
    FRAME_N = 1000
    N_BANDS = 24
    N_FRAMES = 8
    FPS = 4
    CHANNELS = {channels}
    HIDDEN = {hidden_n}
    POOL_SIZE = {pool_size}
    THRESHOLD = {threshold}
    MIN_CONFIRM = 2
    MEAN = {mean_lit}
    INV_STD = {inv_std_lit}
    E_MEAN = {e_mean_lit}
    E_INV_STD = {e_inv_std_lit}
    S0, S1, S2 = {scales_lit}
    B0 = {b0_lit}
    B1 = {b1_lit}
    B2 = {b2_lit}
    WC = {wc_lit}
    WD = {wd_lit}
    WO = {wo_lit}

    # Pycom MicroPython v1.11 safe array allocator (no array * int, no reallocs)
    def _zeros(tc, size):
        arr = array(tc, range(size))
        z = 0.0 if tc == 'f' else 0
        for idx in range(size):
            arr[idx] = z
        return arr

    # Build 24 triangular mel filterbanks (35..1900 Hz)
    low_mel = 1127.0 * math.log(1.0 + 35.0 / 700.0)
    high_mel = 1127.0 * math.log(1.0 + 1900.0 / 700.0)
    hz_pts = [
        700.0 * (math.exp((low_mel + (high_mel - low_mel) * i / 25.0) / 1127.0) - 1.0)
        for i in range(26)
    ]
    bands_list = []
    for b_i in range(N_BANDS):
        left = hz_pts[b_i]
        center = hz_pts[b_i + 1]
        right = hz_pts[b_i + 2]
        ids = []
        wts = []
        for k in range(1, FFT_N // 2 + 1):
            freq = SAMPLE_RATE * k / float(FFT_N)
            if left < freq < right:
                w = (freq - left) / (center - left) if freq <= center else (right - freq) / (right - center)
                if w > 0.0:
                    ids.append(k)
                    wts.append(w)
        s_w = sum(wts)
        w_arr = _zeros('f', len(wts))
        for m_i in range(len(wts)):
            w_arr[m_i] = wts[m_i] / s_w
        bands_list.append((array('H', ids), w_arr))
    bands = tuple(bands_list)
    del hz_pts, bands_list

    # Pre-allocate reusable FFT, feature, and fused-CNN buffers (no 12 KB conv tensor)
    half_fft = FFT_N // 2
    cos_t = _zeros('f', half_fft)
    sin_t = _zeros('f', half_fft)
    for k in range(half_fft):
        ang = 2.0 * math.pi * k / FFT_N
        cos_t[k] = math.cos(ang)
        sin_t[k] = -math.sin(ang)
    half_frame = FRAME_N // 2
    hann_half = _zeros('f', half_frame)
    for i in range(half_frame):
        hann_half[i] = 0.5 - 0.5 * math.cos(2.0 * math.pi * i / (FRAME_N - 1))
    rev = _zeros('H', FFT_N)
    for i in range(FFT_N):
        n_v = i
        j_v = 0
        for _ in range(10):
            j_v = (j_v << 1) | (n_v & 1)
            n_v >>= 1
        rev[i] = j_v

    re = _zeros('f', FFT_N)
    im = _zeros('f', FFT_N)
    frame_pcm = _zeros('h', FRAME_N)
    prev_mel = _zeros('f', FPS * N_BANDS)
    prev_rms = _zeros('f', FPS)
    curr_mel = _zeros('f', FPS * N_BANDS)
    curr_rms = _zeros('f', FPS)
    x_norm = _zeros('f', N_FRAMES * N_BANDS)
    env_norm = _zeros('f', 9)
    pooled = _zeros('f', POOL_SIZE)
    hidden = _zeros('f', HIDDEN)

    has_prev = False
    blocks_processed = 0
    positive_windows = 0
    n_scores = 0
    current_streak = 0
    max_streak = 0
    max_score = 0.0
    max_confirmed_score = 0.0
    max_audio_rms = 0.0
    impact_count = 0
    prev_block_rms = None
    last_idx = FRAME_N - 1
    half_mel = FPS * N_BANDS
    last_proc_end_ms = None
    has_ticks = hasattr(time, "ticks_ms") and hasattr(time, "ticks_diff")

    zrodlo = _ZRODLO_AUDIO_OVERRIDE if _ZRODLO_AUDIO_OVERRIDE is not None else nagraj_audio

    for blok_audio in zrodlo():
        if len(blok_audio) != BLOCK_BYTES:
            raise ValueError("Niepoprawny rozmiar bloku audio: %d" % len(blok_audio))

        if has_ticks:
            t_start_ms = time.ticks_ms()
            if last_proc_end_ms is not None:
                gap_ms = time.ticks_diff(t_start_ms, last_proc_end_ms) - 1000
                if gap_ms > MAX_GAP_MS:
                    has_prev = False
                    current_streak = 0

        rms_sq_sum = 0.0
        max_frame_rms = 0.0
        min_frame_rms = 1.0
        max_crest = 0.0

        for f in range(FPS):
            byte_idx = f * FRAME_N * 2
            s_sum = 0.0
            for i in range(FRAME_N):
                raw = blok_audio[byte_idx] | (blok_audio[byte_idx + 1] << 8)
                byte_idx += 2
                if raw < 0:
                    raw = 0
                elif raw > 4095:
                    raw = 4095
                sample = (raw << 4) - 32768
                frame_pcm[i] = sample
                s_sum += sample

            mean = s_sum / float(FRAME_N)
            for i in range(FFT_N):
                re[i] = 0.0
                im[i] = 0.0

            msq = 0.0
            peak = 0.0
            for i in range(FRAME_N):
                v = float(frame_pcm[i]) - mean
                av = -v if v < 0.0 else v
                if av > peak:
                    peak = av
                msq += v * v
                w = hann_half[i] if i < half_frame else hann_half[last_idx - i]
                re[rev[i]] = v * w

            # In-place radix-2 1024-pt FFT
            n_w = 2
            while n_w <= FFT_N:
                half = n_w // 2
                stride = FFT_N // n_w
                for start in range(0, FFT_N, n_w):
                    for k in range(half):
                        i = start + k
                        j = i + half
                        tw = stride * k
                        c = cos_t[tw]
                        s = sin_t[tw]
                        rj = re[j]
                        ij = im[j]
                        r = c * rj - s * ij
                        q = c * ij + s * rj
                        u = re[i]
                        v = im[i]
                        re[i] = u + r
                        im[i] = v + q
                        re[j] = u - r
                        im[j] = v - q
                n_w *= 2

            for k in range(half_fft + 1):
                rk = re[k]
                ik = im[k]
                re[k] = rk * rk + ik * ik

            mel_off = f * N_BANDS
            for b_idx in range(N_BANDS):
                b_ids, b_wts = bands[b_idx]
                energy_b = 0.0
                for m_i in range(len(b_ids)):
                    energy_b += re[b_ids[m_i]] * b_wts[m_i]
                curr_mel[mel_off + b_idx] = math.log(energy_b + 1e-6)

            rms_pcm = math.sqrt(msq / float(FRAME_N))
            norm_rms = rms_pcm / 32768.0
            crest = peak / (rms_pcm + 1e-6)
            curr_rms[f] = math.log(norm_rms + 1e-7)
            rms_sq_sum += norm_rms * norm_rms
            if norm_rms > max_frame_rms:
                max_frame_rms = norm_rms
            if norm_rms < min_frame_rms:
                min_frame_rms = norm_rms
            if crest > max_crest:
                max_crest = crest

        blocks_processed += 1
        block_rms = math.sqrt(rms_sq_sum / float(FPS))
        if block_rms > max_audio_rms:
            max_audio_rms = block_rms
        if max_frame_rms >= 0.035:
            base_rms = min_frame_rms if min_frame_rms > 1e-5 else 1e-5
            if prev_block_rms is not None and prev_block_rms < base_rms:
                base_rms = prev_block_rms if prev_block_rms > 1e-5 else 1e-5
            if max_crest >= 5.5 or (max_frame_rms / base_rms) >= 3.0:
                impact_count += 1
        prev_block_rms = block_rms

        if has_prev:
            mel_sum = 0.0
            for i in range(half_mel):
                mel_sum += prev_mel[i] + curr_mel[i]
            mel_center = mel_sum / float(N_FRAMES * N_BANDS)

            for t in range(FPS):
                base = t * N_BANDS
                for f_i in range(N_BANDS):
                    v = prev_mel[base + f_i] - mel_center
                    if v < -10.0:
                        v = -10.0
                    elif v > 10.0:
                        v = 10.0
                    z = (v - MEAN[f_i]) * INV_STD[f_i]
                    x_norm[base + f_i] = -6.0 if z < -6.0 else (6.0 if z > 6.0 else z)

            for t in range(FPS):
                src_base = t * N_BANDS
                dst_base = (t + FPS) * N_BANDS
                for f_i in range(N_BANDS):
                    v = curr_mel[src_base + f_i] - mel_center
                    if v < -10.0:
                        v = -10.0
                    elif v > 10.0:
                        v = 10.0
                    z = (v - MEAN[f_i]) * INV_STD[f_i]
                    x_norm[dst_base + f_i] = -6.0 if z < -6.0 else (6.0 if z > 6.0 else z)

            rms_sum = 0.0
            for i in range(FPS):
                rms_sum += prev_rms[i] + curr_rms[i]
            rms_mean = rms_sum / float(N_FRAMES)

            for i in range(FPS):
                v = prev_rms[i] - rms_mean
                v = -4.0 if v < -4.0 else (4.0 if v > 4.0 else v)
                z = (v - E_MEAN[i]) * E_INV_STD[i]
                env_norm[i] = -6.0 if z < -6.0 else (6.0 if z > 6.0 else z)
            for i in range(FPS):
                v = curr_rms[i] - rms_mean
                v = -4.0 if v < -4.0 else (4.0 if v > 4.0 else v)
                idx = i + FPS
                z = (v - E_MEAN[idx]) * E_INV_STD[idx]
                env_norm[idx] = -6.0 if z < -6.0 else (6.0 if z > 6.0 else z)
            z_abs = (rms_mean - E_MEAN[8]) * E_INV_STD[8]
            env_norm[8] = -6.0 if z_abs < -6.0 else (6.0 if z_abs > 6.0 else z_abs)

            # Fused 3x3 Conv2D + ReLU + 6 frequency-group mean/max pooling
            for grp in range(6):
                f_start = grp * 4
                f_end = f_start + 4
                for c in range(CHANNELS):
                    total = 0.0
                    maximum = 0.0
                    bc = B0[c]
                    for t in range(N_FRAMES):
                        for f_i in range(f_start, f_end):
                            z = bc
                            for dt in (-1, 0, 1):
                                tt = t + dt
                                if tt < 0 or tt >= N_FRAMES:
                                    continue
                                row_base = tt * N_BANDS
                                k_row = (dt + 1) * 3
                                for df in (-1, 0, 1):
                                    ff = f_i + df
                                    if ff < 0 or ff >= N_BANDS:
                                        continue
                                    k = (k_row + (df + 1)) * CHANNELS + c
                                    wb = WC[k]
                                    z += x_norm[row_base + ff] * ((wb if wb < 128 else wb - 256) * S0)
                            if z > 0.0:
                                total += z
                                if z > maximum:
                                    maximum = z
                    pooled[grp * CHANNELS + c] = total / 32.0
                    pooled[(6 + grp) * CHANNELS + c] = maximum

            base_env = 12 * CHANNELS
            for i in range(9):
                pooled[base_env + i] = env_norm[i]

            for j in range(HIDDEN):
                z = B1[j]
                for i in range(POOL_SIZE):
                    wb = WD[i * HIDDEN + j]
                    z += pooled[i] * ((wb if wb < 128 else wb - 256) * S1)
                hidden[j] = z if z > 0.0 else 0.0

            z = B2
            for i in range(HIDDEN):
                wb = WO[i]
                z += hidden[i] * ((wb if wb < 128 else wb - 256) * S2)
            if z < -40.0:
                z = -40.0
            elif z > 40.0:
                z = 40.0
            score = 1.0 / (1.0 + math.exp(-z))

            n_scores += 1
            if score > max_score:
                max_score = score
            if score >= THRESHOLD:
                positive_windows += 1
                current_streak += 1
                if current_streak > max_streak:
                    max_streak = current_streak
                if current_streak >= MIN_CONFIRM and score > max_confirmed_score:
                    max_confirmed_score = score
            else:
                current_streak = 0

        prev_mel, curr_mel = curr_mel, prev_mel
        prev_rms, curr_rms = curr_rms, prev_rms
        has_prev = True
        if has_ticks:
            last_proc_end_ms = time.ticks_ms()

    if blocks_processed == 0:
        raise RuntimeError("Brak poprawnych blokow audio z nagraj_audio()")

    engine_detected = max_streak >= MIN_CONFIRM
    impact_detected = impact_count > 0
    vib_flag = bool(vib_aktywny)

    # Binarna metadana drgan sama w sobie nigdy nie potwierdza alarmu
    czy_alarm = bool(engine_detected)
    event_type = 1 if czy_alarm else 0

    if n_scores == 0:
        confidence = 0
    elif not engine_detected:
        ratio = max_score / THRESHOLD
        if ratio > 1.0:
            ratio = 1.0
        confidence = int(round(ratio * 40.0))
    else:
        ref = max_confirmed_score if max_confirmed_score > 0.0 else max_score
        margin = (ref - THRESHOLD) / max(1e-6, 1.0 - THRESHOLD)
        if margin < 0.0:
            margin = 0.0
        elif margin > 1.0:
            margin = 1.0
        persistence = float(positive_windows) / float(n_scores)
        conf = 55.0 + 25.0 * margin + 10.0 * persistence
        if impact_detected:
            conf += 5.0
        if vib_flag:
            conf += 5.0
        confidence = max(0, min(100, int(round(conf))))

    src_bits = 0
    if engine_detected or impact_detected or (bool(mic_aktywny) and czy_alarm):
        src_bits |= SOURCE_BIT_MIC
    if vib_flag:
        src_bits |= SOURCE_BIT_VIB
    dur_s = min(blocks_processed, positive_windows + 1) if engine_detected else (
        min(blocks_processed, impact_count) if impact_detected else 0
    )
    if max_audio_rms > 0.0:
        db = 20.0 * math.log(max(max_audio_rms, 1e-6)) / 2.302585092994046
        en_u8 = max(0, min(255, int(round((db + 60.0) * (255.0 / 60.0)))))
    else:
        en_u8 = 0

    _OSTATNI_WYNIK["source_bits"] = src_bits
    _OSTATNI_WYNIK["duration_s"] = dur_s
    _OSTATNI_WYNIK["energy"] = en_u8
    _OSTATNI_WYNIK["inference_ok"] = True
    _OSTATNI_WYNIK["blocks"] = blocks_processed

    return czy_alarm, event_type, confidence""".format(
        channels=channels,
        hidden_n=hidden_n,
        pool_size=pool_size,
        threshold=repr(float(model.THRESHOLD)),
        mean_lit=mean_lit,
        inv_std_lit=inv_std_lit,
        e_mean_lit=e_mean_lit,
        e_inv_std_lit=e_inv_std_lit,
        scales_lit=scales_lit,
        b0_lit=b0_lit,
        b1_lit=b1_lit,
        b2_lit=b2_lit,
        wc_lit=wc_lit,
        wd_lit=wd_lit,
        wo_lit=wo_lit,
    )


def _write_and_verify(full_src, out_path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(full_src, encoding='utf-8', newline='\n')

    # Automated verification checks
    tree = ast.parse(full_src, filename=str(out_path))
    assert 'pin_deepsleep_wakeup' not in full_src, 'Unsupported API found!'

    allowed_mods = {
        'machine', 'network', 'usocket', 'time', 'ubinascii',
        'struct', 'pycom', 'gc', 'array', 'math',
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in allowed_mods, 'Forbidden import: %s' % alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.module in allowed_mods, 'Forbidden from-import: %s' % node.module
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            for side in (node.left, node.right):
                if (isinstance(side, ast.Call) and isinstance(side.func, ast.Name)
                        and side.func.id == 'array'):
                    raise AssertionError('Forbidden array * int in %s' % out_path)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == 'array'):
            for arg in node.args:
                if isinstance(arg, ast.GeneratorExp):
                    raise AssertionError('Forbidden generator in array() in %s' % out_path)

    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'analizuj_sygnaly']
    assert len(funcs) == 1
    fn = funcs[0]
    assert [a.arg for a in fn.args.args] == ['mic_aktywny', 'vib_aktywny']
    last_stmt = fn.body[-1]
    assert isinstance(last_stmt, ast.Return) and isinstance(last_stmt.value, ast.Tuple)
    assert [e.id for e in last_stmt.value.elts] == ['czy_alarm', 'event_type', 'confidence']

    return out_path.stat().st_size


def build_burst():
    burst_model = _load_module('tg_model_burst_src', BURST_MODEL_SRC)
    burst_out = DEPLOY_DIR / 'burst' / 'main.py'
    src = COMPACT_BURST_HEADER + _build_burst_body(burst_model) + COMPACT_BURST_FOOTER
    burst_size = _write_and_verify(src, burst_out)
    print('Generated %s (%d bytes) — compact Pycom 1.20.2.r6 checks OK' % (burst_out, burst_size))


def build_all(burst_only=False):
    build_burst()
    if not burst_only:
        v46_model = _load_module('tg_model_v46_src', V46_MODEL_SRC)
        v46_out = DEPLOY_DIR / 'cnn_v46' / 'main.py'
        v46_src = FIRMWARE_HEADER.format(variant_label='CNN v4.6') + _build_v46_body(v46_model) + FIRMWARE_FOOTER
        v46_size = _write_and_verify(v46_src, v46_out)
        print('Generated %s (%d bytes) — Pycom 1.20.2.r6 checks OK' % (v46_out, v46_size))


if __name__ == '__main__':
    import sys
    build_all(burst_only='--burst-only' in sys.argv)
