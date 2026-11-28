"""Multi-wake confirmation: alarm when 2 consecutive 10 s sessions both score >= thr.

A machine loading timber works for minutes, so after a suspicious session the device
records a second one (after a short sleep) and alarms only if that one is suspicious too.
Transient look-alikes (bird, thunder, a passing helicopter/plane/truck) rarely persist.

Pairs are formed from consecutive sessions of the same recording group, at the same gain:
  * long recordings: consecutive 10 s sessions (soc, soc2, forest ambience, valla forest)
  * ESC-50: different takes (A, B, C, ...) cut from the same source file.
"""

import sys

import numpy as np

import cache
import metrics


def pairs(M):
    """Return list of (i, j) session index pairs, consecutive within group+level."""
    out = []
    key = {}
    for i in range(len(M['group'])):
        k = (M['group'][i], M['level'][i], M['kind'][i])
        key.setdefault(k, []).append(i)
    for k, idx in key.items():
        idx = sorted(idx, key=lambda i: (float(M['start'][i]), M['path'][i]))
        for a, b in zip(idx[:-1], idx[1:]):
            out.append((a, b))
    return np.array(out)


def report_pairs(dec, M, thr, title):
    P = pairs(M)
    alarm = (dec[P[:, 0]] >= thr) & (dec[P[:, 1]] >= thr)
    sub = {k: v[P[:, 0]] for k, v in M.items()}
    metrics.report(alarm, sub, title + ' (2 consecutive sessions)')


def threshold_pairs(dec, M, fp):
    P = pairs(M)
    cvneg = (((M['src'] == 'esc50') | (M['src'] == 'soc2')) & (M['label'] == '0')
             & ((M['kind'] == 'forest') | (M['kind'] == 'mech')))[P[:, 0]]
    m = np.minimum(dec[P[:, 0]], dec[P[:, 1]])[cvneg]
    return float(np.quantile(m, 1 - fp)), int(cvneg.sum())


if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else 'mlp16s0'
    S, M = cache.load('v2')
    dec = np.load(cache.devsim.DATA / 'cache' / ('dec_%s_v2.npy' % name))
    for fp in (0.01, 0.03):
        thr, n = threshold_pairs(dec, M, fp)
        print('pair threshold %.3f for %g FP on %d negative pairs' % (thr, fp, n))
        report_pairs(dec, M, thr, '%s pair-FP %g' % (name, fp))
