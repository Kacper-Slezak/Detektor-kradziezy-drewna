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
FIRMWARE_VER = 2

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


import math
from array import array
V2_N = 512
V2_HALF = 256
V2_OFFS = (0, 1000, 2000, 3000)
V2_BINS = (4, 9, 13, 19, 26, 34, 45, 57, 71, 88, 106, 127, 152, 178, 209, 244)
V2_WH = 12
V2_LO0 = 4
V2_LO1 = 64
V2_HI1 = 244
V2_LAG0 = 36
V2_LAG1 = 171
V2_MAXB = 12
def _zeros(tc, n):
    a = array(tc, range(n))
    z = 0.0 if tc == 'f' else 0
    for i in range(n):
        a[i] = z
    return a
class V2State:
    def __init__(self):
        N = V2_N
        hn = N // 2
        self.re = _zeros('f', N)
        self.im = _zeros('f', N)
        self.ct = _zeros('f', hn)
        self.st = _zeros('f', hn)
        self.hw = _zeros('f', N)
        self.rv = _zeros('H', N)
        for k in range(hn):
            ag = 2.0 * math.pi * k / N
            self.ct[k] = math.cos(ag)
            self.st[k] = -math.sin(ag)
        for i in range(N):
            self.hw[i] = 0.5 - 0.5 * math.cos(2.0 * math.pi * i / (N - 1))
        for i in range(1, N):
            self.rv[i] = (self.rv[i >> 1] >> 1) | ((i & 1) * hn)
        nl = V2_LAG1 - V2_LAG0 + 1
        self.wac = _zeros('f', nl)
        w0 = 0.0
        for i in range(N):
            w0 += self.hw[i] * self.hw[i]
        for t in range(nl):
            lag = V2_LAG0 + t
            s = 0.0
            for i in range(N - lag):
                s += self.hw[i] * self.hw[i + lag]
            self.wac[t] = s / w0
        self.P = _zeros('f', V2_HALF + 1)          # Welch power of the current block
        self.p1 = _zeros('f', V2_HALF + 1)         # power of one frame
        self.L = _zeros('f', V2_HALF + 1)          # log power scratch
        self.W = _zeros('f', V2_HALF + 1)          # whitened log spectrum, current block
        self.Wp = _zeros('f', V2_HALF + 1)         # previous block
        self.wf = _zeros('f', 4 * (V2_LO1 - V2_LO0))  # whitened LO of 4 frames
        self.Wsum = _zeros('f', V2_LO1 - V2_LO0)   # sum over blocks of W[LO]
        self.B = _zeros('f', 15 * V2_MAXB)         # band shape per block
        self.sc = _zeros('f', 5 * V2_MAXB)         # harm, flat, env, lowhi, tf_lo per block
        self.e = _zeros('f', 124)
        self.nb = 0
        self.tb_lo = 0.0
        self.tb_hi = 0.0
        self.wsd = 0.0
        self.cosb = 0.0
    def _fft(self):
        re = self.re
        im = self.im
        ct = self.ct
        st = self.st
        N = V2_N
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
    def _whiten(self, src, dst, k0, k1):
        L = self.L
        a0 = k0 - V2_WH
        if a0 < 1:
            a0 = 1
        a1 = k1 - 1 + V2_WH
        if a1 > V2_HALF:
            a1 = V2_HALF
        for k in range(a0, a1 + 1):
            L[k] = math.log(src[k] + 1e-3)
        lo = k0 - V2_WH
        if lo < 1:
            lo = 1
        hi = k0 + V2_WH
        if hi > V2_HALF:
            hi = V2_HALF
        s = 0.0
        for k in range(lo, hi + 1):
            s += L[k]
        for k in range(k0, k1):
            dst[k] = L[k] - s / (hi - lo + 1)
            nlo = k + 1 - V2_WH
            if nlo < 1:
                nlo = 1
            nhi = k + 1 + V2_WH
            if nhi > V2_HALF:
                nhi = V2_HALF
            while lo < nlo:
                s -= L[lo]
                lo += 1
            while hi < nhi:
                hi += 1
                s += L[hi]
    @staticmethod
    def _corr(a, ao, b, bo, n):
        sa = 0.0
        sb = 0.0
        for i in range(n):
            sa += a[ao + i]
            sb += b[bo + i]
        ma = sa / n
        mb = sb / n
        sab = 0.0
        saa = 0.0
        sbb = 0.0
        for i in range(n):
            x = a[ao + i] - ma
            y = b[bo + i] - mb
            sab += x * y
            saa += x * x
            sbb += y * y
        return sab / (math.sqrt(saa * sbb) + 1e-9)
    def add_block(self, blk):
        if self.nb >= V2_MAXB:
            return
        N = V2_N
        re = self.re
        im = self.im
        hw = self.hw
        rv = self.rv
        P = self.P
        p1 = self.p1
        nlo = V2_LO1 - V2_LO0
        for k in range(V2_HALF + 1):
            P[k] = 0.0
        for fi in range(4):
            bi = V2_OFFS[fi] * 2
            sm = 0
            for i in range(N):
                sm += blk[bi + 2 * i] | (blk[bi + 2 * i + 1] << 8)
            mn = sm / N
            for i in range(N):
                v = (blk[bi + 2 * i] | (blk[bi + 2 * i + 1] << 8)) - mn
                j = rv[i]
                re[j] = v * hw[i]
                im[j] = 0.0
            self._fft()
            for k in range(V2_HALF + 1):
                pw = re[k] * re[k] + im[k] * im[k]
                p1[k] = pw
                P[k] += pw
            self._whiten_frame(fi)
        for k in range(V2_HALF + 1):
            P[k] *= 0.25
        b = self.nb
        ob = b * 15
        ctr = 0.0
        for q in range(15):
            a0 = V2_BINS[q]
            a1 = V2_BINS[q + 1]
            s = 0.0
            for k in range(a0, a1):
                s += P[k]
            vl = math.log(s / (a1 - a0) + 1e-6)
            self.B[ob + q] = vl
            ctr += vl
        ctr /= 15.0
        for q in range(15):
            v = self.B[ob + q] - ctr
            self.B[ob + q] = -10.0 if v < -10.0 else (10.0 if v > 10.0 else v)
        W = self.W
        self._whiten(P, W, V2_LO0, V2_HI1)
        for i in range(N):
            re[i] = 0.0
            im[i] = 0.0
        for k in range(4, 129):
            v = W[k]
            if v > 0.0:
                re[rv[k]] = v
                re[rv[N - k]] = v
        self._fft()
        r0 = re[0]
        best = 0.0
        for t in range(V2_LAG1 - V2_LAG0 + 1):
            v = re[V2_LAG0 + t] / (r0 * self.wac[t] + 1e-12)
            if v > best:
                best = v
        harm = best
        sl = 0.0
        sa = 0.0
        for k in range(4, 129):
            pk = P[k] + 1e-9
            sl += math.log(pk)
            sa += pk
        flat = math.exp(sl / 125.0) / (sa / 125.0)
        sm = 0
        for i in range(4000):
            sm += blk[2 * i] | (blk[2 * i + 1] << 8)
        mn = sm / 4000.0
        e = self.e
        es = 0.0
        for j in range(124):
            acc = 0.0
            o = j * 64
            for i in range(32):
                v = (blk[o + 2 * i] | (blk[o + 2 * i + 1] << 8)) - mn
                acc += v * v
            e[j] = acc / 32.0 + 1e-9
            es += e[j]
        em = es / 124.0
        ev = 0.0
        for j in range(124):
            d = e[j] - em
            ev += d * d
        env = math.log(math.sqrt(ev / 124.0) / em + 1e-3)
        lo = 0.0
        for k in range(4, 45):
            lo += P[k]
        hi = 0.0
        for k in range(45, 244):
            hi += P[k]
        lowhi = math.log((lo + 1e-9) / (hi + 1e-9))
        wf = self.wf
        tf = 0.0
        for j in range(3):
            tf += self._corr(wf, j * nlo, wf, (j + 1) * nlo, nlo)
        tf /= 3.0
        osc = b * 5
        self.sc[osc] = harm
        self.sc[osc + 1] = flat
        self.sc[osc + 2] = env
        self.sc[osc + 3] = lowhi
        self.sc[osc + 4] = tf
        sw = 0.0
        for k in range(V2_LO0, V2_LO1):
            self.Wsum[k - V2_LO0] += W[k]
            sw += W[k]
        mw = sw / nlo
        vv = 0.0
        for k in range(V2_LO0, V2_LO1):
            d = W[k] - mw
            vv += d * d
        self.wsd += math.sqrt(vv / nlo)
        if b > 0:
            Wp = self.Wp
            self.tb_lo += self._corr(W, V2_LO0, Wp, V2_LO0, nlo)
            self.tb_hi += self._corr(W, V2_LO1, Wp, V2_LO1, V2_HI1 - V2_LO1)
            num = 0.0
            na = 0.0
            nb2 = 0.0
            op = (b - 1) * 15
            for q in range(15):
                x = self.B[ob + q]
                y = self.B[op + q]
                num += x * y
                na += x * x
                nb2 += y * y
            self.cosb += num / (math.sqrt(na) * math.sqrt(nb2) + 1e-9)
        for k in range(V2_HALF + 1):
            self.Wp[k] = W[k]
        self.nb = b + 1
    def _whiten_frame(self, fi):
        nlo = V2_LO1 - V2_LO0
        W = self.W
        self._whiten(self.p1, W, V2_LO0, V2_LO1)
        o = fi * nlo
        for k in range(V2_LO0, V2_LO1):
            self.wf[o + k - V2_LO0] = W[k]
    def session_vector(self):
        nb = self.nb
        if nb < 2:
            return None
        v = []
        for q in range(15):
            s = 0.0
            for b in range(nb):
                s += self.B[b * 15 + q]
            v.append(s / nb)
        for q in range(15):
            m = v[q]
            s = 0.0
            for b in range(nb):
                d = self.B[b * 15 + q] - m
                s += d * d
            v.append(math.sqrt(s / nb))
        for c in range(5):
            s = 0.0
            for b in range(nb):
                s += self.sc[b * 5 + c]
            m = s / nb
            s = 0.0
            for b in range(nb):
                d = self.sc[b * 5 + c] - m
                s += d * d
            v.append(m)
            v.append(math.sqrt(s / nb))
        v.append(self.tb_lo / (nb - 1))
        v.append(self.tb_hi / (nb - 1))
        nlo = V2_LO1 - V2_LO0
        s = 0.0
        for i in range(nlo):
            s += self.Wsum[i] / nb
        m = s / nlo
        s = 0.0
        for i in range(nlo):
            d = self.Wsum[i] / nb - m
            s += d * d
        v.append(math.sqrt(s / nlo) / (self.wsd / nb + 1e-9))
        v.append(self.cosb / (nb - 1))
        return v
def score(vec, model):
    mu = model['MU']
    sd = model['SD']
    d = len(mu)
    W1 = model['W1']
    B1 = model['B1']
    W2 = model['W2']
    H = len(B1)
    z = [0.0] * d
    for i in range(d):
        x = (vec[i] - mu[i]) / sd[i]
        z[i] = -6.0 if x < -6.0 else (6.0 if x > 6.0 else x)
    out = 0.0
    s1 = model['S1']
    for u in range(H):
        acc = 0.0
        o = u * d
        for i in range(d):
            w = W1[o + i]
            acc += (w - 256 if w > 127 else w) * z[i]
        acc = acc * s1 + B1[u]
        if acc > 0.0:
            w = W2[u]
            out += acc * (w - 256 if w > 127 else w)
    return out * model['S2'] + model['B2']


V2_T_HIGH = 6.4072
V2_T_SUSP = 2.9465
V2_CONFIRM_SLEEP_MS = 120000   # 2nd look after 2 min: a machine loading timber is still there
V2_NVS_KEY = "v2_conf"
V2_MODELS = (
    dict(MU=(0.0880461, 0.42087, 0.496324, 0.460552, 0.316046, 0.214543, 0.155262, 0.10269, 0.0447391, -0.112629, -0.231345, -0.335315, -0.456507, -0.536507, -0.626769, 0.595431, 0.591408, 0.532305, 0.498216, 0.489508, 0.446723, 0.436337, 0.424858, 0.433852, 0.434667, 0.434906, 0.443751, 0.455662, 0.469543, 0.474842, 0.35041, 0.058815, 0.502088, 0.10449, -0.141429, 0.358866, -0.94354, 0.624218, 0.175775, 0.0932506, 0.332428, 0.118162, 0.650766, 0.685244,), SD=(1.55133, 1.49032, 1.28752, 1.12503, 0.967007, 0.861415, 0.850706, 0.81138, 0.819967, 0.850554, 0.891001, 0.962994, 1.00675, 1.09804, 1.17973, 0.406161, 0.388492, 0.361346, 0.337627, 0.344757, 0.329632, 0.337774, 0.336348, 0.3722, 0.374558, 0.369321, 0.377127, 0.385256, 0.406625, 0.412123, 0.0728226, 0.0305651, 0.205783, 0.0840003, 0.652755, 0.311246, 1.68658, 0.543441, 0.162225, 0.0439007, 0.260918, 0.149346, 0.145432, 0.304779,), W1=b'\xddE\xc6\xf0\xc85\xff4\xf8\xd2\xd4\x08\x036\x16\x08\xdd\x0b\xf5\xd4\n\xfb\x1f\xee\x01\xf3\x06\'\xd2\xfd$\xfe1\x1d-\xe8\x1b;\xf2\x150\xfa\xdc\x1c\xdb\xf5\x11\xda\xda\xdf#\x02\xe3\x18\xb9D\x05)I\x18\xed\x0c\xd1\xe3\xb8\xf1\xf1 \x1f\xba\xfd\xf3\xd6\t\xe0\xfc\xb3%88\xb1\xff\t6\xc4\xd1\xfe\xf2\r\xd3\x0e\x03\x1e\x05\x19Z\xce\xd9O4\xa9\xe8\xe11\xa4L&\x1e\xf9<\x0b\x00 \xf6\xef\xf4\x01\xff\xe3\xf7\xff\xd9%\xe2\x19\xdd\x01\xda\xca\xec?\xf5\xdb\xcd\x18(\xf3\n,\x1b\x16\xf2\xe5\x02\x02\r\x01\xf6\xfb"\x114\x14"\x03\xf4\x14\xf2\xff\xe38(\xe2\x10\xf0\xd1[\xf8\xe6\xf9\xe8\xf9|\x06\xb6#%\x19\xf5\xf3\xeb\xe3\xe9\x1b\xe5\xf3I\xef\r\xd1\x02\xf6\x08\xfe\xe5\x1f\x1b\x03\xd7\xf2\x1a\x01\x1b\xe2\x04\xd2"\x04;7\xfa\x13$\xef\xf5\xe5\xe3\x0b62\xed\x1a\xec\x1a\x1d\xed\xfb\x04\xeb\x01\xc7*\n\xeb\r\x08\x14\x13\xc6\x0c\xf3\x06\x01\xfd\xf7\xfb\xf6\x10\x1c\x08\x03\x11\xfd\xd8\xf4:\x12\xd9\r&-\xf1\x1f\xec\x1c\x1d\x04\x03\xca\xc5\x17\xd0#\x1e\xca\xda\x0f\x08\x1b\x10\x05\x1a\xf1\xfd\xb2\x0e\x0c\xdb\t\xd0\xcb\xe3\xe5\x15\x08\x00\x0f\xf8\xfc,\xdc\x18>&\xc2\x00\xf5\x1b\xa59\xbb\x0c\xd4\x10\x15\xf0)5\xf3\xc99\x0f8\xdb"\x0f\xe5\x13!\t\x0c\xc7\xfd\xe6\x12\x05.#B\x11\x81\xf2C\x1a,\x15\xbc\n\xcb\x06Q&', S1=0.0100811, B1=(0.257389, -0.0942158, 0.0835717, 1.53038, -0.12933, -0.618427, 0.26929, 1.52833,), W2=b'_\x8d\x8efTF]\x81', S2=0.0237762, B2=-2.52199),
)
V2_OSTATNI = [0.0, False]       # last session: mean logit, suspicious


def _v2_sig(x):
    x = -30.0 if x < -30.0 else (30.0 if x > 30.0 else x)
    return 1.0 / (1.0 + math.exp(-x))


def analizuj_sygnaly(mic_aktywny, vib_aktywny, prog=None):
    """Record one session (nagraj_audio) and score it.
    Returns (czy_alarm, event_type, confidence); V2_OSTATNI holds the logit and whether
    the session is suspicious enough to be confirmed by a second one."""
    st = V2State()
    n = 0
    for blk in nagraj_audio():
        if len(blk) != 8000:
            raise ValueError("blk")
        st.add_block(blk)
        n += 1
    if n < 2:
        raise RuntimeError("No audio")
    vec = st.session_vector()
    st = None
    gc.collect()
    lg = 0.0
    for m in V2_MODELS:
        lg += score(vec, m)
    lg /= len(V2_MODELS)
    susp = lg >= V2_T_SUSP
    V2_OSTATNI[0] = lg
    V2_OSTATNI[1] = susp
    hi = V2_T_HIGH if prog is None else prog
    czy = lg >= hi or (vib_aktywny and susp)
    conf = int(round(100.0 * _v2_sig(lg)))
    if vib_aktywny and czy:
        conf += 10
    conf = max(0, min(100, conf))
    return czy, (1 if czy else 0), conf


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


def _v2_nvs_get(k):
    try:
        v = pycom.nvs_get(k)
        return 0 if v is None else v
    except (ValueError, OSError):
        return 0


def _v2_nvs_set(k, v):
    try:
        pycom.nvs_set(k, v)
    except Exception:
        pass


def _v2_alarm(conf, vib):
    sb = 1 | (2 if vib else 0)
    gc.collect()
    try:
        polacz_wifi()
        wyslij_payload(przygotuj_ramke_alarm(1, conf, 100, sb))
    except Exception as e:
        print("Alarm err:", e)


def main():
    wi = machine.wake_reason()
    pw = wi[0] if wi else -1
    if pw == machine.RTC_WAKE and _v2_nvs_get(V2_NVS_KEY):
        # second look at a suspicious session
        prev = _v2_nvs_get(V2_NVS_KEY)
        _v2_nvs_set(V2_NVS_KEY, 0)
        vib = (prev & 2) != 0 or (pin_vib is not None and pin_vib.value() == 1)
        print("Wake: RTC confirm")
        try:
            czy, et, conf = analizuj_sygnaly(True, vib, prog=V2_T_SUSP)
            print("Confirm result: alarm/conf/logit", czy, conf, V2_OSTATNI[0])
            if czy:
                _v2_alarm(conf, vib)
                idz_spac_na_sztywno(CZAS_SNU_SZTYWNEGO_MS)
                return
        except Exception as e:
            print("Det err:", e)
        idz_spac_na_czujniki()
    elif pw == machine.RTC_WAKE:
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
        czy = False
        conf = 0
        try:
            print("Detection start: mic/vib", mic, vib)
            czy, et, conf = analizuj_sygnaly(mic, vib)
            print("Detection result: alarm/conf/logit/susp", czy, conf, V2_OSTATNI[0], V2_OSTATNI[1])
        except Exception as e:
            print("Det err:", e)
        gc.collect()
        if czy:
            _v2_alarm(conf, vib)
            idz_spac_na_sztywno(CZAS_SNU_SZTYWNEGO_MS)
        elif V2_OSTATNI[1]:
            _v2_nvs_set(V2_NVS_KEY, 1 | (2 if vib else 0))
            idz_spac_na_sztywno(V2_CONFIRM_SLEEP_MS)
        else:
            idz_spac_na_czujniki()
    else:
        print("Boot: wake reason", pw)
        _v2_nvs_set(V2_NVS_KEY, 0)
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
