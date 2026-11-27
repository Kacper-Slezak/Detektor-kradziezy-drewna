# Timber Guard v2 engine detector: device-side feature extraction and scoring.
# Pure Python, MicroPython v1.11 compatible (Pycom 1.20.2.r6): no f-strings, no numpy,
# preallocated arrays, floats only where needed.  The numpy oracle is features.py; the
# test test_v2_device.py checks they agree.  build_main.py inlines this file into main.py.
#
# Usage on the device:
#   st = V2State()                 # allocate once per wake (about 9 KB)
#   for blk in nagraj_audio():     # 8000-byte LE blocks of 12-bit ADC codes
#       st.add_block(blk)
#   vec = st.session_vector()      # list of 58 floats, same order as features.NAMES
#   p = score(vec, MODEL)          # probability of "machine at the pile"

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
        # Hann autocorrelation, normalised, for lags V2_LAG0..V2_LAG1
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
        self.es = _zeros('f', 124)                 # sorted copy for the median
        self.nb = 0
        self.tb_lo = 0.0
        self.tb_hi = 0.0
        self.wsd = 0.0
        self.cosb = 0.0

    # ------------------------------------------------------------------ DSP helpers
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
        """dst[k] = log(src[k]+1e-3) - mean(log over max(1,k-WH)..min(256,k+WH)), k0<=k<k1.
        Uses self.L as scratch; computes logs for the needed span only."""
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
            # slide window to k+1
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

    # ------------------------------------------------------------------ per block
    def add_block(self, blk):
        """blk: bytes-like, 8000 bytes, little-endian 12-bit ADC codes."""
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
        # band shape
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
        # whitened block spectrum
        W = self.W
        self._whiten(P, W, V2_LO0, V2_HI1)
        # harmonicity: ACF of max(W,0) over bins 4..128 via the same FFT
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
        # flatness 4..128
        sl = 0.0
        sa = 0.0
        for k in range(4, 129):
            pk = P[k] + 1e-9
            sl += math.log(pk)
            sa += pk
        flat = math.exp(sl / 125.0) / (sa / 125.0)
        # sub-frame envelope variation (124 x 32 samples)
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
        # session-level running quantities
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

    def _whiten_frame(self, fi):
        nlo = V2_LO1 - V2_LO0
        W = self.W
        self._whiten(self.p1, W, V2_LO0, V2_LO1)
        o = fi * nlo
        for k in range(V2_LO0, V2_LO1):
            self.wf[o + k - V2_LO0] = W[k]

    # ------------------------------------------------------------------ session
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
        v.append(eh / (et + 0.1))
        return v


def score(vec, model):
    """model: dict with MU, SD (feature standardisation), W1 (bytes, int8, H*d row-major
    per hidden unit) with scale S1, B1 (H floats), W2 (bytes, int8, H) with scale S2, B2.
    Returns the logit."""
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
