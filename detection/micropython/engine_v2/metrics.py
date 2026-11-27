"""Session-level metrics with Wilson intervals, grouped by kind / class / level."""

import math

import numpy as np


def wilson(k, n, z=1.96):
    if n == 0:
        return (float('nan'), float('nan'))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def rate(mask_alarm, mask_sel):
    k = int(np.sum(mask_alarm & mask_sel))
    n = int(np.sum(mask_sel))
    lo, hi = wilson(k, n)
    return k, n, lo, hi


def fmt(k, n, lo, hi):
    if n == 0:
        return '   -'
    return '%3d/%-4d %5.1f%% [%4.1f-%4.1f]' % (k, n, 100.0 * k / n, 100 * lo, 100 * hi)


def report(alarm, meta, title, sets=None):
    """alarm: (n,) bool per session. sets: list of (name, mask)."""
    kind, src, lev = meta['kind'], meta['src'], meta['level']
    if sets is None:
        sets = [
            ('engine ESC-50 (CV)', (kind == 'engine') & (src == 'esc50')),
            ('engine soc2 machines (CV)', (kind == 'engine') & (src == 'soc2')),
            ('engine+weather SNR 0dB (CV)', (kind == 'engine_mix') & ((src == 'esc50') | (src == 'soc2')) & (meta['snr'] == '0.0')),
            ('engine+weather SNR 6dB (CV)', (kind == 'engine_mix') & ((src == 'esc50') | (src == 'soc2')) & (meta['snr'] == '6.0')),
            ('engine+storm/rain/wind -3dB (CV)', (kind == 'engine_mix') & ((src == 'esc50') | (src == 'soc2')) & (meta['snr'] == '-3.0')),
            ('engine+storm/rain/wind +3dB (CV)', (kind == 'engine_mix') & ((src == 'esc50') | (src == 'soc2')) & (meta['snr'] == '3.0')),
            ('engine external soc+truck', (kind == 'engine') & ((src == 'soc') | (src == 'sample'))),
            ('engine ICE (train src)', (kind == 'engine') & (src == 'ice')),
            ('FP forest rec soc2 (CV)', (kind == 'forest') & (src == 'soc2')),
            ('FP forest/nature ESC', (kind == 'forest') & (src == 'esc50')),
            ('FP forest ambience rec', (kind == 'forest') & (src == 'sample')),
            ('FP passing mech (heli/plane/train)', (kind == 'mech') & (src == 'esc50')),
            ('FSD50K engine', (kind == 'engine') & (src == 'fsd')),
            ('FSD50K engine+weather', (kind == 'engine_mix') & (src == 'fsd')),
            ('FSD50K FP nature/weather', (kind == 'forest') & (src == 'fsd')),
            ('FSD50K FP passing mech', (kind == 'mech') & (src == 'fsd')),
            ('FP other ESC (domestic etc.)', kind == 'other'),
            ('FP mains hum / ventilation (synth)', src == 'synth'),
            ('alarm on chainsaw/hand_saw', kind == 'ambig'),
        ]
    print('==', title)
    levels = sorted(set(lev), key=float)
    print('%-36s' % '' + ''.join('%-28s' % ('rms=' + l) for l in levels))
    for name, m in sets:
        if not m.any():
            continue
        row = '%-36s' % name
        for l in levels:
            row += '%-28s' % fmt(*rate(alarm, m & (lev == l)))
        print(row)


def auc(scores, labels):
    s = np.asarray(scores, float)
    y = np.asarray(labels).astype(bool)
    order = np.argsort(s)
    ranks = np.empty(len(s))
    ranks[order] = np.arange(1, len(s) + 1)
    # average ties
    for v in np.unique(s):
        m = s == v
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    npos, nneg = y.sum(), (~y).sum()
    return (ranks[y].sum() - npos * (npos + 1) / 2) / (npos * nneg)
