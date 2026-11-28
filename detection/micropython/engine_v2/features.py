"""Reference (numpy) features for the v2 engine detector, computed per 10 s device session.

Intuition (review "Przegląd detekcji issue-31", section 5, plus measurements in this dir):
  * an engine is a set of *stable tonal lines* (firing frequency f_z = rpm/60*cyl/2 and its
    harmonics) that persist second after second; wind/rain/insects/birds do not have stable
    low-frequency lines; all features are ratios or correlations, so they do not depend on
    the microphone gain.

Per 1 s block (4000 raw ADC codes) the device takes 4 Hann frames of 512 samples at offsets
0/1000/2000/3000 (as burst) and averages their power spectra (Welch 1967). From the block
spectrum P[0..256] (bin = 7.8125 Hz):
  bands[15]  log band power minus its mean over bands (spectral shape, as burst)
  W          whitened log spectrum: log P[k] minus its local mean over k +- 12 bins
             (removes the spectral envelope, keeps narrow lines)
  harm       peak of the normalised ACF of max(W, 0) over bins 4..128, lags 36..171
             (111..23 Hz), Hann-ACF corrected (Tolonen & Karjalainen 2000; Boersma 1993)
  flat       spectral flatness 31..1000 Hz (Johnston 1988)
  env        log coefficient of variation of 32-sample sub-frame energies
  lowhi      log(P 31-350 Hz / P 350-1900 Hz)
  tf_lo      mean correlation of W (31-500 Hz) between the 4 frames of the block
Session (blocks b = 0..nb-1):
  tb_lo/hi   mean correlation of W between consecutive blocks, 31-500 / 500-1900 Hz
             (the strongest single feature: AUC 0.85-0.91 engine vs forest sounds)
  stab_lo    std of session-mean W over 31-500 Hz / mean per-block std (lines survive averaging)
  cos_bands  mean cosine similarity of consecutive band-shape vectors
  lines_*    session-mean W over 31-500 Hz: number of bins above LINE, summed excess
             above LINE, bins above LINE in *every* block
  tb2_lo     like tb_lo, blocks two seconds apart;  tb_mid: like tb_lo over 156-1000 Hz
  imp_rate   mean fraction of 8 ms sub-frames with energy > 4x the block median (rain clicks)
  lvl_sd     std over blocks of log block RMS; lvl_dabs: mean |change| between blocks (gusts)
  frame_range  mean log(max/min) of the energy of the four 248 ms quarters of a block
  lines_*_hi like lines_* over 500-1906 Hz; lines_lo_hi = log((prom_lo+0.1)/(prom_hi+0.1));
             peak_hz: frequency of the strongest bin of the session-mean W (31-1906 Hz)
  mod_d[15]  per band: std of the frame-to-frame change of log band energy (frames 250 ms
             apart, across the whole session); mod_r[15]: std of the band level relative to
             the frame mean; mod_dabs: mean |change|; mod_lvl: std of the frame mean level
  hum50      share of line prominence (session-mean W above LINE) that sits on the bins of
             exact multiples of 50 Hz: mains hum is there, an engine's drifting comb is not
  + mean and std over blocks of bands, harm, flat, env, lowhi, tf_lo.
"""

import numpy as np

N = 512
FS = 4000
OFFS = (0, 1000, 2000, 3000)
BINS = (4, 9, 13, 19, 26, 34, 45, 57, 71, 88, 106, 127, 152, 178, 209, 244)  # as burst
HANN = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N) / (N - 1))
WH = 12                                          # whitening half-width [bins]
LO = slice(4, 64)                                # 31-500 Hz
HI = slice(64, 244)                              # 500-1906 Hz
LAG_LO, LAG_HI = 36, 171
_w_acf = np.correlate(HANN, HANN, 'full')[N - 1:]
WAC = _w_acf / _w_acf[0]

NAMES = (['band_mu%d' % i for i in range(15)] + ['band_sd%d' % i for i in range(15)]
         + ['harm_mu', 'harm_sd', 'flat_mu', 'flat_sd', 'env_mu', 'env_sd',
            'lowhi_mu', 'lowhi_sd', 'tf_lo_mu', 'tf_lo_sd',
            'tb_lo', 'tb_hi', 'stab_lo', 'cos_bands',
            'lines_n', 'lines_prom', 'lines_persist', 'tb2_lo', 'tb_mid',
            'imp_rate', 'lvl_sd', 'lvl_dabs', 'frame_range',
            'lines_n_hi', 'lines_prom_hi', 'lines_lo_hi', 'peak_hz', 'hum50']
         + ['mod_d%d' % i for i in range(15)] + ['mod_r%d' % i for i in range(15)]
         + ['mod_dabs', 'mod_lvl'])
HUM_BINS = sorted({int(round(50.0 * k / 7.8125)) for k in range(1, 39)} & set(range(4, 244)))
LINE = 0.8                                       # whitened log level of a 'strong line'
MID = slice(20, 128)                             # 156-1000 Hz


def whiten(P):
    """log power minus local mean over +-WH bins (edges use the available bins)."""
    L = np.log(P + 1e-3)
    cs = np.concatenate([[0.0], np.cumsum(L)])
    k = np.arange(len(L))
    a = np.maximum(1, k - WH)
    b = np.minimum(len(L) - 1, k + WH) + 1
    return L - (cs[b] - cs[a]) / (b - a)


def corr(a, b):
    a = a - a.mean()
    b = b - b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-9))


def block_features(block):
    """block: (4000,) ADC codes -> (dict of scalars, bands (15,), W (257,))."""
    x = block.astype(np.float64)
    assert x.shape == (4000,)
    P = np.zeros(N // 2 + 1)                                   # (257,)
    Wf = []
    Fb = []                                                    # (4, 15) frame band logs
    for o in OFFS:
        f = x[o:o + N]
        f = (f - f.mean()) * HANN
        X = np.fft.rfft(f)
        p = X.real ** 2 + X.imag ** 2
        Wf.append(whiten(p)[LO])
        Fb.append([np.log(p[BINS[q]:BINS[q + 1]].mean() + 1e-6) for q in range(15)])
        P += p
    P /= len(OFFS)
    bp = np.array([P[BINS[b]:BINS[b + 1]].mean() for b in range(15)]) + 1e-6
    lb = np.log(bp)
    bands = np.clip(lb - lb.mean(), -10, 10)
    W = whiten(P)
    hw = np.zeros(N // 2 + 1)
    hw[4:129] = np.maximum(W[4:129], 0.0)
    acf = np.fft.irfft(hw, n=N)
    r = acf[LAG_LO:LAG_HI + 1] / (acf[0] * WAC[LAG_LO:LAG_HI + 1] + 1e-12)
    harm = float(r.max())
    seg = P[4:129] + 1e-9
    flat = float(np.exp(np.mean(np.log(seg))) / np.mean(seg))
    xs = x - x.mean()
    e = (xs[:3968].reshape(-1, 32) ** 2).mean(axis=1) + 1e-9     # (124,)
    env = float(np.log(e.std() / e.mean() + 1e-3))
    imp = float((e > 4 * np.median(e)).mean())
    lvl = float(0.5 * np.log(e.mean()))
    q = e.reshape(4, 31).mean(axis=1)
    frr = float(np.log(q.max() / q.min()))
    lowhi = float(np.log((P[4:45].sum() + 1e-9) / (P[45:244].sum() + 1e-9)))
    tf_lo = float(np.mean([corr(Wf[j], Wf[j + 1]) for j in range(len(Wf) - 1)]))
    return dict(harm=harm, flat=flat, env=env, lowhi=lowhi, tf_lo=tf_lo, imp=imp, lvl=lvl,
                frr=frr, fb=np.array(Fb)), bands, W


def session_features(codes):
    """codes: (nb*4000,) ADC codes -> (len(NAMES),) session vector."""
    nb = len(codes) // 4000
    assert nb >= 2
    D, B, W = [], [], []
    for i in range(nb):
        d, b, w = block_features(codes[i * 4000:(i + 1) * 4000])
        D.append(d)
        B.append(b)
        W.append(w)
    B = np.array(B)                                            # (nb, 15)
    W = np.array(W)                                            # (nb, 257)
    sc = {k: np.array([d[k] for d in D]) for k in D[0] if k != 'fb'}
    E = np.concatenate([d['fb'] for d in D])                    # (4*nb, 15)
    tb_lo = np.mean([corr(W[i, LO], W[i + 1, LO]) for i in range(nb - 1)])
    tb_hi = np.mean([corr(W[i, HI], W[i + 1, HI]) for i in range(nb - 1)])
    stab_lo = W[:, LO].mean(0).std() / (np.mean(W[:, LO].std(1)) + 1e-9)
    num = (B[1:] * B[:-1]).sum(1)
    den = np.linalg.norm(B[1:], axis=1) * np.linalg.norm(B[:-1], axis=1) + 1e-9
    cosb = float(np.mean(num / den))
    v = list(B.mean(0)) + list(B.std(0))
    for k in ('harm', 'flat', 'env', 'lowhi', 'tf_lo'):
        v += [sc[k].mean(), sc[k].std()]
    v += [tb_lo, tb_hi, stab_lo, cosb]
    wm = W[:, LO].mean(0)
    v += [float((wm > LINE).sum()), float(np.clip(wm - LINE, 0, None).sum()),
          float((W[:, LO] > LINE).all(0).sum()),
          np.mean([corr(W[i, LO], W[i + 2, LO]) for i in range(nb - 2)]) if nb > 2 else 0.0,
          np.mean([corr(W[i, MID], W[i + 1, MID]) for i in range(nb - 1)])]
    v += [sc['imp'].mean(), sc['lvl'].std(), float(np.mean(np.abs(np.diff(sc['lvl'])))),
          sc['frr'].mean()]
    wh = W[:, HI].mean(0)
    p_lo = float(np.clip(wm - LINE, 0, None).sum())
    p_hi = float(np.clip(wh - LINE, 0, None).sum())
    v += [float((wh > LINE).sum()), p_hi, float(np.log((p_lo + 0.1) / (p_hi + 0.1))),
          float(np.argmax(W[:, 4:244].mean(0)) + 4) * 7.8125]
    ex = np.clip(W[:, 4:244].mean(0) - LINE, 0, None)
    v += [float((ex[[k - 4 for k in HUM_BINS]].sum() + 0.016) / (ex.sum() + 0.1))]  # no lines -> 0.16 (chance)
    dE = np.diff(E, axis=0)
    rel = E - E.mean(1, keepdims=True)
    v += list(np.std(dE, 0)) + list(np.std(rel, 0)) + [float(np.mean(np.abs(dE))), float(np.std(E.mean(1)))]
    return np.array(v)
