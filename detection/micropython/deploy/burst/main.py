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
        j = t.find(b"\r\n")
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
        "POST " + PREFIKS + "/api/v1/ingest HTTP/1.1\r\nHost: " + h
        + "\r\nUser-Agent: detektor-lopy\r\nConnection: close"
        + "\r\nContent-Type: application/json\r\nX-Ingest-Key: " + INGEST_KEY
        + "\r\nContent-Length: " + str(len(body)) + "\r\n\r\n" + body
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
    i = resp.find(b"\r\n\r\n")
    if i < 0:
        return False
    hdr, tr = resp[:i], resp[i + 4:]
    parts = hdr.split(b"\r\n", 1)[0].split(b" ")
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
    from array import array
    import math
    N = 512
    B = 15
    INP = 32
    HID = 16
    TH = 0.84
    REQ = 2
    MN = (2.33041, 1.862249, 1.277732, 0.766236, 0.438646, 0.334615, 0.140322, -0.05325, -0.258494, -0.564463, -0.827131, -1.092074, -1.283409, -1.473083, -1.60918, 0.725765, 0.739235, 0.664465, 0.615682, 0.584126, 0.53152, 0.521938, 0.500388, 0.475254, 0.493085, 0.49285, 0.500509, 0.528777, 0.550158, 0.685384, 0.385582, -3.631901)
    IS = (0.396642, 0.532302, 0.735562, 0.840386, 0.918611, 0.863016, 1.050359, 1.131938, 1.10536, 1.039661, 0.994162, 0.850733, 0.758836, 0.73803, 0.64903, 2.08871, 2.303122, 2.54984, 2.79974, 2.97125, 3.110344, 2.815549, 2.944725, 2.927174, 2.562597, 2.350902, 2.139562, 1.988035, 1.940156, 1.713624, 1.359401, 0.529465)
    SC = (0.0103115, 0.0105673)
    BI = (-0.845143, -0.296848, 0.468891, 0.313998, 0.1661, 0.601917, 0.089784, 0.547218, 0.101929, 0.684029, 0.508327, -0.314188, 0.77284, 0.498411, 0.03797, 0.998465, 0.607969)
    WT = (
        b'\xdd,\x03%\x07\xfe\xe9\xeb\xfa\xa7\xf0#4\x01\xe4\xf4\xf1\x14\xfd\x10\xf5\xfb\x07\x01\x13\x06\x0f\xf9\xff\xed\xdcOU\xff\xea\x03\x06\xef\xfc\xee\xdd\x13\x1d\x11\xe7\xda\xe6\t\xfc\x00\xe9\x04\xf0\xf3\xe7\xe5\xe4\xd3\xf6\x02%+\x02\x8a\xf2\x07\x05\x0f\xda\x04\xcd\x11\xfe\x13\x14\xf6\x07\xfd\xfe)'
        b'\x18\xef\xf2\xf6\x06\xee\n\xdb\xf1\x12\xe5\x08\xf8\x02\x04\x19\xd9\xf9\x07*\x02\x0e\x0f\x14\xfa?\x1f=\x14\x05\x91\xff\xff\xee\xf5\xfd\x02\x03\x07\xf4\xec\x08\xf7\xf4\xcf\xe9\xf88\xea\xda\xe4\xea\xef\x13\xf2\xfb\x18\x1e \x1f\x14\x1c\x0b\x10\xfa\xfa\xff\xee\xf8\xf9\xff\xfd\n\x0e\xff\x02\xdd\xf3\x14\x1a'
        b'\xe9\r\xe3\xfe\xe0\xee\xfb\x02 \x02\x03\x12\x1e\x1d\t\xde\xdf\xf7\xf1\xf2\xfc\xff\xf7\x01\xef\xf6\x05\xf7\xeb\xe2\xd9\x1e\x04\x15\x14\x0e\xbc\xf6 \x00\xfe\x13\xeb\xf9\xf0\xfb\x05\xe4\xf1\x16\x18\x00\xf7\x10\x03\xf7\x1c\x06\x08\xee\xf4\xe8\x05\x00\x84\xe2\x08\x17\x08)\x00\x009\x05\xf8#:6:\x02'
        b'\x05\t\xfe\x04\xfd\xf5\xf6\xf5\xf2\t\xfa\xed\xdf\xfa"\xf9\xf8\x14\xf3\xf9\xfe\xf7\r\xff\x12\xf7\xfc\x07\x0e\t\x05\xf2\xee\xf5\x03\t\xf1\xf3\x12\x02\xe2\xf9\x0f\x11\x00\xfa\xed\x03\xa3\x13\x18\t\xf6\xf8\x0e\xfb\x1e\xfa\xff\x15,(\x18\x14\x02\x0e"\xf2\xfc\xfe\x0e\x17\x04\xfd\xfd\x18\x0f\x06\x00\xe6'
        b'\x00\n\xdc\xed\x13\xff\xee\xfc\x1a\x0b\x01\x1a\x11\x08\x06\t\xe4\xe7\x08\x06\x00\x02\xe2\xf3\xfa\xf6\xfd\x0c\xf8\x12\xec0\x7f\xd5\xd7\xc8\xe4\xdf\xfa\x14\x03\xef\t\x1f\xc2\xd6\x03(\x06\x01\x07\xfc\xf7\xfc\x04\xf2\xdf\xf6\xfb\xe4\x07\x02-\xcf\xee\xeb\xfd$\t\xec\xf3\x0c\x15\xf7\x12\xe0\x17\xfa\x01\xed'
        b'\x15\x1a\x01\x07\x1b\xd6\xe6\x01\x02*\x02\xed\xfe\xfd\xff\x12\xec\xf7\x06\x18\xeb\xd1%\x07\x08\xf9\x1f\x02\x16\x07\x0b\x04\r\x14\xe5\xf1\xd4\xfe\xf8\x05\xdf\xef \x00\xed\xed\xf7\x1c\x1a\xcb+\xec"\x1a\x10#\x11%\x02\xed\xb5\xce\x08\x05\xf4\xf8\xf9\x02\xff\xf9\x0e\xf5\xff\xf7\x05\x11\x1b$\xfc\x88'
        b'\xfc\x1d\xf2\xe4\xf0&\xfd\x12\x16\x14\xe9\xe0\n\xf5\x10\xfd\x1a\xf0\x08\xf6\r\x16\x00\xed\xf1\xef\xf0\xcc\xba\xf7\xdf \x97\xab>\xa1\xc0@A\x93&\xb7>\x88:<\x81F'
    )

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
    return czy_alarm, event_type, confidence

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
    print("Sleep: timer ms", czas_ms)
    time.sleep(0.05)
    machine.deepsleep(czas_ms)


def idz_spac_na_czujniki():
    for _ in range(20):
        if not ((pin_mic and pin_mic.value() == 1) or (pin_vib and pin_vib.value() == 1)):
            break
        time.sleep(0.1)
    if (pin_mic and pin_mic.value() == 1) or (pin_vib and pin_vib.value() == 1):
        print("Sensor stuck HIGH")
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
    print("Sleep: GPIO P19/P20")
    time.sleep(0.05)
    machine.deepsleep()


def main():
    wi = machine.wake_reason()
    pw = wi[0] if wi else -1
    if pw == machine.RTC_WAKE:
        print("Wake: RTC")
        gc.collect()
        try:
            polacz_wifi()
            wyslij_payload(przygotuj_ramke_heartbeat(100, 0, 0))
        except Exception as e:
            print("HB err:", e)
        idz_spac_na_czujniki()
    elif pw == machine.PIN_WAKE:
        print("Wake: GPIO", wi)
        pl = wi[1] if len(wi) > 1 and wi[1] else ()
        ids = [(p.id() if hasattr(p, "id") else str(p)) for p in pl]
        mic = (pin_mic is not None and pin_mic.value() == 1) or (PIN_MIKROFON_ID in ids)
        vib = (pin_vib is not None and pin_vib.value() == 1) or (PIN_DRGANIA_ID in ids)
        czy_alarm = False
        event_type = 0
        confidence = 0
        try:
            print("Detection start: mic/vib", mic, vib)
            czy_alarm, event_type, confidence = analizuj_sygnaly(mic, vib)
            print("Detection result: alarm/type/conf", czy_alarm, event_type, confidence)
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
        print("Boot: wake reason", pw)
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
