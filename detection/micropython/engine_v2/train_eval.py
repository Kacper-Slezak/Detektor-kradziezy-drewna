"""Train and evaluate session-level engine classifiers on block features (numpy only).

Protocol (no leakage across recordings):
  * ESC-50 sessions: 5-fold CV using the official, source-disjoint folds;
  * ICE (Niš) sessions: training only (no vehicle IDs, cannot be split safely);
  * external sessions (soundsofchanges tractors/van/lorries, forest ambience, truck):
    never trained on; scored by the model trained on all ESC folds + ICE.
  * every recording appears at 3 gains; all gains of one recording stay together.
"""

import sys

import numpy as np

import cache
import feat_cache
import metrics

NB_F = 20            # block feature count (features.block_matrix)


def cos_sim_consecutive(B):
    b = B[:, :15]
    if len(b) < 2:
        return 1.0
    num = (b[1:] * b[:-1]).sum(1)
    den = np.linalg.norm(b[1:], axis=1) * np.linalg.norm(b[:-1], axis=1) + 1e-9
    return float(np.mean(num / den))


def session_vector(B):
    """(nb, 20) block features -> session feature vector."""
    mu = B.mean(0)
    sd = B.std(0)
    return np.concatenate([mu, sd, [cos_sim_consecutive(B)]])


class Logistic:
    def __init__(self, l2=1e-2, iters=3000, lr=0.1):
        self.l2, self.iters, self.lr = l2, iters, lr

    def fit(self, X, y, w=None):
        self.mu = X.mean(0)
        self.sd = X.std(0) + 1e-6
        Z = (X - self.mu) / self.sd
        n, d = Z.shape
        w = np.ones(n) if w is None else w
        w = w / w.sum()
        self.W = np.zeros(d)
        self.b = 0.0
        # Adam on weighted log-loss
        m = np.zeros(d + 1)
        v = np.zeros(d + 1)
        for t in range(1, self.iters + 1):
            p = 1 / (1 + np.exp(-(Z @ self.W + self.b)))
            g = p - y
            gw = Z.T @ (w * g) + self.l2 * self.W
            gb = np.sum(w * g)
            G = np.concatenate([gw, [gb]])
            m = 0.9 * m + 0.1 * G
            v = 0.999 * v + 0.001 * G * G
            step = self.lr * (m / (1 - 0.9 ** t)) / (np.sqrt(v / (1 - 0.999 ** t)) + 1e-8)
            self.W -= step[:-1]
            self.b -= step[-1]
        return self

    def decision(self, X):
        return ((X - self.mu) / self.sd) @ self.W + self.b


class MLP:
    """d -> H ReLU -> 1, Adam, weighted log-loss; small enough for the LoPy."""

    def __init__(self, H=16, l2=1e-3, iters=4000, lr=0.01, seed=0):
        self.H, self.l2, self.iters, self.lr, self.seed = H, l2, iters, lr, seed

    def fit(self, X, y, w=None):
        rng = np.random.default_rng(self.seed)
        self.mu = X.mean(0)
        self.sd = X.std(0) + 1e-6
        Z = np.clip((X - self.mu) / self.sd, -6, 6)
        n, d = Z.shape
        w = np.ones(n) if w is None else w
        w = w / w.sum()
        P = [rng.normal(0, 1 / np.sqrt(d), (d, self.H)), np.zeros(self.H),
             rng.normal(0, 1 / np.sqrt(self.H), self.H), np.zeros(1)]
        ms = [np.zeros_like(p) for p in P]
        vs = [np.zeros_like(p) for p in P]
        for t in range(1, self.iters + 1):
            h = np.maximum(0, Z @ P[0] + P[1])          # (n, H)
            o = h @ P[2] + P[3][0]                       # (n,)
            p = 1 / (1 + np.exp(-o))
            g = w * (p - y)                              # (n,)
            gW2 = h.T @ g + self.l2 * P[2]
            gb2 = np.array([g.sum()])
            gh = np.outer(g, P[2]) * (h > 0)
            gW1 = Z.T @ gh + self.l2 * P[0]
            gb1 = gh.sum(0)
            for i, G in enumerate([gW1, gb1, gW2, gb2]):
                ms[i] = 0.9 * ms[i] + 0.1 * G
                vs[i] = 0.999 * vs[i] + 0.001 * G * G
                P[i] -= self.lr * (ms[i] / (1 - 0.9 ** t)) / (np.sqrt(vs[i] / (1 - 0.999 ** t)) + 1e-8)
        self.P = P
        return self

    def decision(self, X):
        Z = np.clip((X - self.mu) / self.sd, -6, 6)
        h = np.maximum(0, Z @ self.P[0] + self.P[1])
        return h @ self.P[2] + self.P[3][0]


def class_weights(M, idx):
    """Balance positives vs negatives; inside negatives, balance kinds."""
    y = M['label'][idx] == '1'
    k = M['kind'][idx]
    w = np.ones(len(idx))
    w[y] = 1.0 / y.sum()
    for kk in set(k[~y]):
        m = (~y) & (k == kk)
        w[m] = 1.0 / (m.sum() * len(set(k[~y])))
    return w / w.mean()


def cross_val(X, M, make_model, verbose=True):
    """Returns out-of-fold decision for ESC-50, external decision from the all-data model."""
    src = M['src']
    fold = M['fold'].astype(int)
    y = (M['label'] == '1').astype(float)
    dec = np.full(len(y), np.nan)
    esc = (src == 'esc50') | (src == 'soc2')          # source-disjoint CV folds
    ice = src == 'ice'
    ext = ~(esc | ice)
    for k in range(1, 6):
        tr = np.where((esc & (fold != k)) | ice)[0]
        te = np.where(esc & (fold == k))[0]
        m = make_model().fit(X[tr], y[tr], class_weights(M, tr))
        dec[te] = m.decision(X[te])
    tr = np.where(esc | ice)[0]
    m = make_model().fit(X[tr], y[tr], class_weights(M, tr))
    dec[ext] = m.decision(X[ext])
    dec[ice] = m.decision(X[ice])                      # in-sample, for reference only
    return dec, m


def threshold_at_fp(dec, M, fp_target=0.01):
    """Pick threshold on out-of-fold ESC negatives (forest+other+mech) at a target FP rate."""
    neg = ((M['src'] == 'esc50') | (M['src'] == 'soc2')) & (M['label'] == '0') & (M['kind'] != 'ambig')
    return float(np.quantile(dec[neg], 1 - fp_target))


def summary(dec, M, thr, title):
    alarm = dec >= thr
    metrics.report(alarm, M, title)
    y = M['label'] == '1'
    esc = (M['src'] == 'esc50') | (M['src'] == 'soc2')
    print('CV (ESC-50 + soc2) out-of-fold session AUC: %.3f' % metrics.auc(dec[esc], y[esc]))


if __name__ == '__main__':
    tag = sys.argv[1] if len(sys.argv) > 1 else 'v2'
    S, M = cache.load(tag)
    X = feat_cache.load(tag)
    for name, mk in [('logistic', lambda: Logistic()), ('mlp16', lambda: MLP())]:
        dec, _ = cross_val(X, M, mk)
        thr = threshold_at_fp(dec, M, 0.01)
        summary(dec, M, thr, name + ' @1% CV-negative FP')
        sys.stdout.flush()
