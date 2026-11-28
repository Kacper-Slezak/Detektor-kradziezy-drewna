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
V2_LINE = 0.8
V2_MID0 = 20
V2_MID1 = 128
V2_HUM = bytearray(244)
for _k in range(1, 39):
    _b = int(50.0 * _k / 7.8125 + 0.5)
    if 4 <= _b < 244:
        V2_HUM[_b] = 1
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
        self.Wpp = _zeros('f', V2_LO1)             # block before previous (LO only)
        self.per = _zeros('B', V2_LO1 - V2_LO0)    # bin above V2_LINE in every block so far
        self.tb2 = 0.0
        self.tbm = 0.0
        self.wf = _zeros('f', 4 * (V2_LO1 - V2_LO0))  # whitened LO of 4 frames
        self.Wsum = _zeros('f', V2_HI1 - V2_LO0)   # sum over blocks of W[4..243]
        self.B = _zeros('f', 15 * V2_MAXB)         # band shape per block
        self.sc = _zeros('f', 5 * V2_MAXB)         # harm, flat, env, lowhi, tf_lo per block
        self.lv = _zeros('f', V2_MAXB)             # log block RMS
        self.imp = 0.0
        self.frr = 0.0
        self.e = _zeros('f', 124)
        self.fbp = _zeros('f', 15)                 # previous frame band logs
        self.fbc = _zeros('f', 15)                 # current frame band logs
        self.md1 = _zeros('f', 15)                 # sum of d, d^2 per band
        self.md2 = _zeros('f', 15)
        self.mr1 = _zeros('f', 15)                 # sum of rel, rel^2 per band
        self.mr2 = _zeros('f', 15)
        self.mrs = _zeros('f', 15)                 # shift (first frame) for stable variance
        self.mls = 0.0
        self.mda = 0.0
        self.ml1 = 0.0
        self.ml2 = 0.0
        self.nf = 0
        self.es = _zeros('f', 124)                 # sorted copy for the median
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
            self._frame_mod()
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
        es = self.es
        for j in range(124):
            es[j] = e[j]
        es = sorted(es)
        med = 0.5 * (es[61] + es[62])
        ni = 0
        for j in range(124):
            if e[j] > 4.0 * med:
                ni += 1
        self.imp += ni / 124.0
        self.lv[b] = 0.5 * math.log(em)
        qmx = 0.0
        qmn = 1e30
        for qq in range(4):
            s = 0.0
            for j in range(qq * 31, qq * 31 + 31):
                s += e[j]
            if s > qmx:
                qmx = s
            if s < qmn:
                qmn = s
        self.frr += math.log(qmx / qmn)
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
        for k in range(V2_LO0, V2_HI1):
            self.Wsum[k - V2_LO0] += W[k]
        for k in range(V2_LO0, V2_LO1):
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
        if b > 0:
            self.tbm += self._corr(W, V2_MID0, self.Wp, V2_MID0, V2_MID1 - V2_MID0)
        if b > 1:
            self.tb2 += self._corr(W, V2_LO0, self.Wpp, V2_LO0, nlo)
        per = self.per
        for k in range(V2_LO0, V2_LO1):
            if b == 0:
                per[k - V2_LO0] = 1 if W[k] > V2_LINE else 0
            elif W[k] <= V2_LINE:
                per[k - V2_LO0] = 0
            self.Wpp[k] = self.Wp[k]
        for k in range(V2_HALF + 1):
            self.Wp[k] = W[k]
        self.nb = b + 1
    def _frame_mod(self):
        p1 = self.p1
        fbc = self.fbc
        fbp = self.fbp
        m = 0.0
        for q in range(15):
            a0 = V2_BINS[q]
            a1 = V2_BINS[q + 1]
            s = 0.0
            for k in range(a0, a1):
                s += p1[k]
            vl = math.log(s / (a1 - a0) + 1e-6)
            fbc[q] = vl
            m += vl
        m /= 15.0
        if self.nf == 0:
            self.mls = m
            for q in range(15):
                self.mrs[q] = fbc[q] - m
        x = m - self.mls
        self.ml1 += x
        self.ml2 += x * x
        for q in range(15):
            r = fbc[q] - m - self.mrs[q]
            self.mr1[q] += r
            self.mr2[q] += r * r
            if self.nf > 0:
                dd = fbc[q] - fbp[q]
                self.md1[q] += dd
                self.md2[q] += dd * dd
                self.mda += dd if dd > 0.0 else -dd
            fbp[q] = fbc[q]
        self.nf += 1
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
        n_l = 0
        prom = 0.0
        n_p = 0
        for i in range(nlo):
            wm = self.Wsum[i] / nb
            if wm > V2_LINE:
                n_l += 1
                prom += wm - V2_LINE
            n_p += self.per[i]
        v.append(float(n_l))
        v.append(prom)
        v.append(float(n_p))
        v.append(self.tb2 / (nb - 2) if nb > 2 else 0.0)
        v.append(self.tbm / (nb - 1))
        v.append(self.imp / nb)
        s = 0.0
        for b in range(nb):
            s += self.lv[b]
        m = s / nb
        s = 0.0
        da = 0.0
        for b in range(nb):
            d = self.lv[b] - m
            s += d * d
            if b > 0:
                d = self.lv[b] - self.lv[b - 1]
                da += d if d > 0.0 else -d
        v.append(math.sqrt(s / nb))
        v.append(da / (nb - 1))
        v.append(self.frr / nb)
        n_h = 0
        p_h = 0.0
        best = -1e30
        kb = 0
        for i in range(V2_HI1 - V2_LO0):
            wm = self.Wsum[i] / nb
            if wm > best:
                best = wm
                kb = i
            if i >= V2_LO1 - V2_LO0 and wm > V2_LINE:
                n_h += 1
                p_h += wm - V2_LINE
        v.append(float(n_h))
        v.append(p_h)
        v.append(math.log((prom + 0.1) / (p_h + 0.1)))
        v.append((kb + V2_LO0) * 7.8125)
        eh = 0.0
        et = 0.0
        for i in range(V2_HI1 - V2_LO0):
            x = self.Wsum[i] / nb - V2_LINE
            if x > 0.0:
                et += x
                if V2_HUM[i + V2_LO0]:
                    eh += x
        v.append((eh + 0.016) / (et + 0.1))
        nf = self.nf
        nd = nf - 1
        for q in range(15):
            mm = self.md1[q] / nd
            x = self.md2[q] / nd - mm * mm
            v.append(math.sqrt(x if x > 0.0 else 0.0))
        for q in range(15):
            mm = self.mr1[q] / nf
            x = self.mr2[q] / nf - mm * mm
            v.append(math.sqrt(x if x > 0.0 else 0.0))
        v.append(self.mda / (nd * 15))
        mm = self.ml1 / nf
        x = self.ml2 / nf - mm * mm
        v.append(math.sqrt(x if x > 0.0 else 0.0))
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


V2_T_HIGH = 5.2177
V2_T_SUSP = 2.6165
V2_TRYB_POKAZ = False          # True for the corridor demo: short confirm and lock-out
V2_CONFIRM_SLEEP_MS = 15000 if V2_TRYB_POKAZ else 120000   # 2nd look: machine still there?
V2_PO_ALARMIE_MS = 60000 if V2_TRYB_POKAZ else CZAS_SNU_SZTYWNEGO_MS
V2_NVS_KEY = "v2_conf"
V2_MODELS = (
    dict(MU=(0.433906, 0.642708, 0.819817, 0.765554, 0.599136, 0.380742, 0.227888, 0.0890671, -0.076091, -0.277996, -0.447619, -0.588484, -0.742791, -0.854323, -0.971513, 0.636639, 0.618909, 0.560176, 0.525299, 0.499702, 0.453634, 0.441323, 0.428251, 0.43634, 0.446372, 0.458147, 0.46486, 0.480853, 0.49825, 0.505536, 0.376483, 0.0643617, 0.468866, 0.10035, -0.149305, 0.355242, -0.528035, 0.66729, 0.223198, 0.0986805, 0.377223, 0.131881, 0.653132, 0.714098, 5.87002, 5.48935, 2.02852, 0.342934, 0.229916, 0.0790471, 0.486856, 0.428082, 1.47604, 4.08833, 2.60826, 1.23163, 364.923, 0.217009, 1.32253, 1.41968, 1.33609, 1.33543, 1.35158, 1.35193, 1.38284, 1.40475, 1.42707, 1.43634, 1.43888, 1.43193, 1.43449, 1.41282, 1.39401, 0.911233, 0.901522, 0.806705, 0.754351, 0.716898, 0.64635, 0.626489, 0.606235, 0.603444, 0.615341, 0.62353, 0.627617, 0.646318, 0.660293, 0.670542, 1.0363, 1.20402,), SD=(1.80131, 1.56094, 1.43139, 1.28961, 1.11351, 0.921041, 0.859492, 0.812266, 0.821239, 0.907195, 1.03774, 1.13959, 1.20658, 1.27683, 1.35188, 0.441181, 0.407199, 0.384405, 0.356138, 0.347257, 0.320074, 0.325178, 0.327564, 0.352061, 0.362427, 0.37169, 0.374201, 0.388166, 0.407738, 0.413681, 0.122784, 0.0391116, 0.226132, 0.0760277, 0.654555, 0.275915, 1.81835, 0.567482, 0.219697, 0.0509363, 0.275019, 0.18447, 0.169222, 0.284332, 5.9514, 12.1394, 4.76219, 0.27904, 0.236757, 0.0873024, 0.550067, 0.48694, 1.46645, 7.32608, 8.29495, 1.78265, 451.755, 0.184811, 0.854861, 0.884807, 0.905153, 0.919651, 0.928788, 0.965785, 1.02405, 1.05954, 1.078, 1.08142, 1.11422, 1.1252, 1.12564, 1.11978, 1.12619, 0.426733, 0.389886, 0.365118, 0.332598, 0.321769, 0.300411, 0.31417, 0.324271, 0.338953, 0.343234, 0.361695, 0.373117, 0.38187, 0.399279, 0.410387, 0.703529, 1.00794,), W1=ubinascii.a2b_base64('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'), S1=0.00571061, B1=(-0.519386, 0.571396, -0.0754916, -0.0195732, -0.426257, -0.376342, -0.227792, -0.00284539, -0.518146, -0.154068, -0.163539, -0.26537, -0.205398, -0.0129075, 0.1238, -0.217547, 0.0854661, -0.222173, -0.209336, -0.680645, 0.326808, -0.39308, 0.593549, -0.0761917, -0.389451, 0.0709565, -0.0950338, -0.348748, -0.249475, 0.336714, -0.252025, -0.116908, -0.300584, -0.2035, -0.16754, -0.156858, -0.273029, -0.444668, 0.0189509, -0.200635, 0.128067, -0.116787, 0.10407, -0.111556, -0.712687, -0.233995, -0.0936994, -0.15676, -0.478417, 0.0293338, -0.294517, 0.448457, -0.0495657, 0.0748874, -0.887712, 0.136411, 0.152463, -0.228059, 0.108468, -0.128858, -0.400685, 0.454477, 0.0641312, -0.25493,), W2=ubinascii.a2b_base64('G4ZHrp8oMjnLSdvtjnKkK5zTl26YcFSVsVmEupBUtdemx16O48g6QjFlz2eva4+RnxmRoGMvgVRCk3mci09eMQ=='), S2=0.0112837, B2=0.0459014),
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


def v2_bench(n_blokow=10):
    """REPL: import main; main.v2_bench()  -> ms per 1 s block and free heap, no Wi-Fi."""
    gc.collect()
    print("V2_HEAP_START", gc.mem_free() if hasattr(gc, "mem_free") else -1)
    st = V2State()
    blk = bytearray(8000)
    x = 12345
    for i in range(4000):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        v = 2048 + int(300.0 * math.sin(2.0 * math.pi * 45.0 * i / 4000.0)) + (x % 61) - 30
        blk[2 * i] = v & 0xFF
        blk[2 * i + 1] = (v >> 8) & 0xFF
    gc.collect()
    print("V2_HEAP_STATE", gc.mem_free() if hasattr(gc, "mem_free") else -1)
    for b in range(n_blokow):
        t0 = time.ticks_ms()
        st.add_block(blk)
        print("V2_BLOCK_MS", b, time.ticks_diff(time.ticks_ms(), t0))
    t0 = time.ticks_ms()
    vec = st.session_vector()
    lg = 0.0
    for m in V2_MODELS:
        lg += score(vec, m)
    print("V2_SCORE_MS", time.ticks_diff(time.ticks_ms(), t0), "logit", lg / len(V2_MODELS))
    gc.collect()
    print("V2_HEAP_END", gc.mem_free() if hasattr(gc, "mem_free") else -1)


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
                idz_spac_na_sztywno(V2_PO_ALARMIE_MS)
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
            idz_spac_na_sztywno(V2_PO_ALARMIE_MS)
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
