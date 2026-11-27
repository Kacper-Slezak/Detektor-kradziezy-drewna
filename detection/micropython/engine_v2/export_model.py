"""Train the deployed v2 model (MLP 49-8-1, int8 weights on the device) and pick thresholds.

Thresholds come from out-of-fold decisions of the same recipe on the forest-relevant CV
negatives (ESC-50 nature/weather/people + passing helicopter/plane/train, soc2 forest):
  T_HIGH : single-session false-alarm rate 0.5 %  -> alarm at once
  T_SUSP : single-session false-alarm rate 3 %    -> suspicious, confirm with a 2nd session
Output: $TG_DATA/cache/model_v2.json (+ copy next to this file for the build).
"""

import json
from pathlib import Path

import numpy as np

import cache
import feat_cache
import features
import train_eval as te

SEEDS = (11,)
H = 8


class Ens:
    def __init__(self):
        self.ms = [te.MLP(H=H, seed=s) for s in SEEDS]

    def fit(self, X, y, w=None):
        for m in self.ms:
            m.fit(X, y, w)
        return self

    def decision(self, X):
        return np.mean([m.decision(X) for m in self.ms], axis=0)


def main():
    S, M = cache.load('v2')
    X = feat_cache.load('v2')
    dec, _ = te.cross_val(X, M, Ens)
    np.save(cache.devsim.DATA / 'cache' / 'dec_ens8_v2.npy', dec)
    t_high = te.threshold_at_fp(dec, M, 0.005)
    t_susp = te.threshold_at_fp(dec, M, 0.03)
    for name, t in (('T_HIGH', t_high), ('T_SUSP', t_susp)):
        te.summary(dec, M, t, 'ens8 %s=%.3f' % (name, t))
    y = (M['label'] == '1').astype(float)
    tr = np.where((M['src'] == 'esc50') | (M['src'] == 'soc2') | (M['src'] == 'ice'))[0]
    ens = Ens().fit(X[tr], y[tr], te.class_weights(M, tr))
    models = []
    for m in ens.ms:
        W1, B1, W2, B2 = m.P
        s1 = float(np.abs(W1).max() / 127.0)
        s2 = float(np.abs(W2).max() / 127.0)
        q1 = np.round(W1.T / s1).astype(int).reshape(-1)        # (H*d,) row-major per unit
        q2 = np.round(W2 / s2).astype(int)
        models.append(dict(MU=m.mu.tolist(), SD=m.sd.tolist(),
                           W1=q1.tolist(), S1=s1, B1=B1.tolist(), W2=q2.tolist(), S2=s2,
                           B2=float(B2[0])))
    # out-of-fold decisions are float; check the int8 model against the float one in-sample
    xs = X[tr[:2000]]
    f = ens.ms[0].decision(xs)
    z = np.clip((xs - ens.ms[0].mu) / ens.ms[0].sd, -6, 6)
    mm = models[0]
    h = np.maximum(0, z @ (np.array(mm['W1']).reshape(H, -1).T * mm['S1']) + np.array(mm['B1']))
    q = h @ (np.array(mm['W2']) * mm['S2']) + mm['B2']
    print('int8 vs float logit: max abs diff %.3f, median |logit| %.2f' % (np.abs(q - f).max(), np.median(np.abs(f))))
    out = dict(names=list(features.NAMES), models=models, T_HIGH=t_high, T_SUSP=t_susp,
               note='MLP 49-8-1 int8 weights; thresholds from out-of-fold CV (float model)')
    js = json.dumps(out)
    (cache.devsim.DATA / 'cache' / 'model_v2.json').write_text(js)
    Path(__file__).with_name('model_v2.json').write_text(js)
    print('saved model_v2.json  T_HIGH=%.3f T_SUSP=%.3f' % (t_high, t_susp))


if __name__ == '__main__':
    main()
