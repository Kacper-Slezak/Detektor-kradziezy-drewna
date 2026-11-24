import machine
from machine import Pin
from network import WLAN
import usocket as socket
import time
import ubinascii
import struct
import pycom

pycom.heartbeat(False)

# ================= KONFIGURACJA =================
WIFI_SSID = "TWOJE_SSID"
WIFI_HASLO = "TWOJE_HASLO"
API_URL = "http://srv18.mikr.us:20376"
DEVICE_ID = "70B3D57ED00D0009"
INGEST_KEY = ""

PIN_MIKROFON_ID = "P19"
PIN_DRGANIA_ID  = "P20"
CZAS_SNU_SZTYWNEGO_MS = 600000
FIRMWARE_VER = 1

# Stałe domyślne dla backendu (poza analizą alarmową)
DOMYSLNY_CZAS_S = 1
DOMYSLNA_ENERGIA = 120

# ================= PROTOKÓŁ (V2) =================
PROTO_VERSION = 2
MSG_ALARM     = 1
MSG_HEARTBEAT = 2
MSG_BOOT      = 3

# ================= LOGIKA SIECIOWA (WI-FI / HTTP) =================
def rozbierz_url(url):
    if not url.startswith("http://"):
        raise ValueError("API_URL musi zaczynać się od http://")
    reszta = url[len("http://"):]
    i = reszta.find("/")
    adres, prefiks = (reszta, "") if i < 0 else (reszta[:i], reszta[i:].rstrip("/"))
    j = adres.find(":")
    if j < 0:
        return adres, 80, prefiks
    return adres[:j], int(adres[j + 1:]), prefiks

HOST, PORT, PREFIKS = rozbierz_url(API_URL)

def polacz_wifi():
    wlan = WLAN(mode=WLAN.STA)
    if wlan.isconnected():
        return
    wlan.connect(WIFI_SSID, auth=(WLAN.WPA2, WIFI_HASLO), timeout=10000)
    for _ in range(40):
        if wlan.isconnected():
            print("Wi-Fi OK, IP:", wlan.ifconfig()[0])
            return
        time.sleep(0.5)
    raise OSError("Brak połączenia z Wi-Fi")

def odchunkuj(tresc):
    wynik = b""
    while True:
        j = tresc.find(b"\r\n")
        if j < 0:
            return wynik
        n = int(tresc[:j].split(b";")[0], 16)
        if n == 0:
            return wynik
        wynik += tresc[j + 2:j + 2 + n]
        tresc = tresc[j + 2 + n + 2:]

def wyslij_payload(ramka):
    payload_hex = ubinascii.hexlify(ramka).decode()
    body = '{"device": "' + DEVICE_ID + '", "payload_hex": "' + payload_hex + '"}'
    host_naglowek = HOST if PORT == 80 else HOST + ":" + str(PORT)
    zapytanie = ("POST " + PREFIKS + "/api/v1/ingest HTTP/1.1\r\n"
                 + "Host: " + host_naglowek + "\r\n"
                 + "User-Agent: detektor-lopy\r\n"
                 + "Connection: close\r\n"
                 + "Content-Type: application/json\r\n"
                 + "X-Ingest-Key: " + INGEST_KEY + "\r\n"
                 + "Content-Length: " + str(len(body)) + "\r\n"
                 + "\r\n" + body)

    adres = socket.getaddrinfo(HOST, PORT)[0][-1]
    s = socket.socket()
    s.settimeout(15)
    try:
        s.connect(adres)
        dane = zapytanie.encode()
        while dane:
            dane = dane[s.send(dane):]
        odpowiedz = b""
        while True:
            kawalek = s.recv(512)
            if not kawalek:
                break
            odpowiedz += kawalek
    finally:
        s.close()

    i = odpowiedz.find(b"\r\n\r\n")
    if i >= 0:
        naglowki, tresc = odpowiedz[:i], odpowiedz[i + 4:]
        kod = int(naglowki.split(b" ")[1])
        if b"transfer-encoding: chunked" in naglowki.lower():
            tresc = odchunkuj(tresc)
        print("Wysłano:", payload_hex.upper(), "->", kod, tresc.decode())
        return True
    return False

# ================= CZUJNIKI I ANALIZA =================
def inicjalizuj_pin(pin_id):
    try:
        return Pin(pin_id, mode=Pin.IN, pull=Pin.PULL_DOWN)
    except ValueError:
        return Pin(pin_id, mode=Pin.IN, pull=None)

pin_mic = inicjalizuj_pin(PIN_MIKROFON_ID)
pin_vib = inicjalizuj_pin(PIN_DRGANIA_ID)

def analizuj_sygnaly(mic_aktywny, vib_aktywny):
    czy_alarm = mic_aktywny or vib_aktywny
    event_type = 1
    confidence = 90 if (mic_aktywny and vib_aktywny) else 60
    return czy_alarm, event_type, confidence

# ================= PAMIĘĆ NIEULOTNA (NVS) I RAMKI =================
def _pobierz_licznik():
    try:
        cnt = pycom.nvs_get("pkt_cnt")
        if cnt is None:
            cnt = 0
    except Exception as e:
        print("Błąd odczytu NVS (pkt_cnt):", e)
        cnt = 0
    cnt = (cnt + 1) & 0xFFFF
    try:
        pycom.nvs_set("pkt_cnt", cnt)
    except Exception as e:
        print("Błąd zapisu NVS (pkt_cnt):", e)
    return cnt

def _pobierz_boot_id():
    try:
        bid = pycom.nvs_get("boot_id")
        if bid is None:
            bid = 0
    except Exception as e:
        print("Błąd odczytu NVS (boot_id):", e)
        bid = 0

    bid = (bid + 1) & 0xFFFF
    if bid == 0:
        bid = 1

    try:
        pycom.nvs_set("boot_id", bid)
    except Exception as e:
        print("Błąd zapisu NVS (boot_id):", e)
    return bid

def _naglowek(msg_type):
    first_byte = ((PROTO_VERSION & 0x0F) << 4) | (msg_type & 0x0F)
    return struct.pack(">BH", first_byte, _pobierz_licznik())

def przygotuj_ramke_alarm(event_type=1, confidence=100, battery_pct=100,
                          source_bits=0, duration_s=DOMYSLNY_CZAS_S, energy=DOMYSLNA_ENERGIA):
    confidence  = max(0, min(100, int(confidence)))
    battery_pct = max(0, min(100, int(battery_pct)))
    duration_s  = max(0, min(65535, int(duration_s)))
    energy      = max(0, min(255, int(energy)))
    body = struct.pack(">BBBHBB", event_type, source_bits, confidence, duration_s, energy, battery_pct)
    return _naglowek(MSG_ALARM) + body

def przygotuj_ramke_heartbeat(battery_pct=100, rejected_events=0, flags=0):
    battery_pct     = max(0, min(100, int(battery_pct)))
    rejected_events = max(0, min(255, int(rejected_events)))
    body = struct.pack(">BBB", battery_pct, rejected_events, flags)
    return _naglowek(MSG_HEARTBEAT) + body

def przygotuj_ramke_boot(boot_id, firmware_version=FIRMWARE_VER, reset_reason=1, battery_pct=100):
    battery_pct = max(0, min(100, int(battery_pct)))
    body = struct.pack(">BBBH", firmware_version, reset_reason, battery_pct, boot_id)
    return _naglowek(MSG_BOOT) + body

# ================= TRYBY ZASILANIA =================
def idz_spac_na_czujniki():
    piny_bez_pull = ("P13", "P14", "P15", "P16", "P17", "P18")
    czy_pull = (PIN_MIKROFON_ID not in piny_bez_pull) and (PIN_DRGANIA_ID not in piny_bez_pull)

    machine.pin_deepsleep_wakeup(
        pins=[pin_mic, pin_vib],
        mode=machine.WAKEUP_ANY_HIGH,
        enable_pull=czy_pull
    )
    time.sleep(0.05)
    machine.deepsleep()

def idz_spac_na_sztywno(czas_ms):
    machine.pin_deepsleep_wakeup(pins=[])
    time.sleep(0.05)
    machine.deepsleep(czas_ms)

# ================= GŁÓWNA MASZYNA STANÓW =================
def main():
    wake_info = machine.wake_reason()
    powod = wake_info[0]

    # STAN 1: Wybudzenie z timera (RTC)
    if powod == machine.RTC_WAKE:
        ramka_hb = przygotuj_ramke_heartbeat(battery_pct=100, rejected_events=0, flags=0)
        try:
            polacz_wifi()
            wyslij_payload(ramka_hb)
        except Exception as e:
            print("Błąd wysyłania Heartbeata:", e)

        idz_spac_na_czujniki()

    # STAN 2: Wybudzenie z czujników (PIN)
    elif powod == machine.PIN_WAKE:
        piny_wybudzajace = wake_info[1] if len(wake_info) > 1 and wake_info[1] else []
        mic_aktywny = (pin_mic.value() == 1) or any(p.id() == PIN_MIKROFON_ID for p in piny_wybudzajace)
        vib_aktywny = (pin_vib.value() == 1) or any(p.id() == PIN_DRGANIA_ID for p in piny_wybudzajace)

        czy_alarm, event_type, confidence = analizuj_sygnaly(mic_aktywny, vib_aktywny)

        if czy_alarm:
            ramka = przygotuj_ramke_alarm(
                event_type=event_type,
                confidence=confidence,
                battery_pct=100
            )
            try:
                polacz_wifi()
                wyslij_payload(ramka)
            except Exception as e:
                print("Błąd wysyłania Alarmu:", e)

        idz_spac_na_sztywno(CZAS_SNU_SZTYWNEGO_MS)

    # STAN 3: Zimny start (Zasilanie / Reset)
    else:
        boot_id = _pobierz_boot_id()
        ramka_boot = przygotuj_ramke_boot(
            boot_id=boot_id,
            firmware_version=FIRMWARE_VER,
            reset_reason=1,
            battery_pct=100
        )
        try:
            polacz_wifi()
            wyslij_payload(ramka_boot)
        except Exception as e:
            print("Błąd wysyłania Boot:", e)

        idz_spac_na_czujniki()

if __name__ == "__main__":
    main()