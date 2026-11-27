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

    def __init__(self, H=16, l2=1e-3, iters=1500, lr=0.01, seed=0):
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


class GBTrees:
    """Gradient-boosted depth-2 trees on log-loss (Friedman 2001, Ann. Stat. 29(5)).
    Thresholds come from 32 per-feature quantiles; a fitted model is a few small arrays
    (feature, threshold, leaf values), cheap to evaluate on the LoPy."""

    def __init__(self, n_trees=200, lr=0.1, n_bins=32, min_leaf=20.0, l2=1.0):
        self.n_trees, self.lr, self.n_bins, self.min_leaf, self.l2 = n_trees, lr, n_bins, min_leaf, l2

    def _best_split(self, Xb, g, h, idx):
        best = (0.0, None)
        G, H = g[idx].sum(), h[idx].sum()
        base = G * G / (H + self.l2)
        for j in range(Xb.shape[1]):
            gs = np.bincount(Xb[idx, j], g[idx], self.n_bins)
            hs = np.bincount(Xb[idx, j], h[idx], self.n_bins)
            gl, hl = np.cumsum(gs)[:-1], np.cumsum(hs)[:-1]
            gr, hr = G - gl, H - hl
            ok = (hl >= self.min_leaf * h[idx].mean()) & (hr >= self.min_leaf * h[idx].mean())
            gain = np.where(ok, gl * gl / (hl + self.l2) + gr * gr / (hr + self.l2) - base, -1)
            b = int(np.argmax(gain))
            if gain[b] > best[0]:
                best = (gain[b], (j, b))
        return best[1]

    def fit(self, X, y, w=None):
        n, d = X.shape
        w = np.ones(n) if w is None else w / np.mean(w)
        qs = np.linspace(0, 1, self.n_bins + 1)[1:-1]
        self.edges = np.array([np.unique(np.quantile(X[:, j], qs)) for j in range(d)], dtype=object)
        Xb = np.zeros((n, d), dtype=np.int64)
        for j in range(d):
            Xb[:, j] = np.searchsorted(self.edges[j], X[:, j], side='right')
        p0 = np.clip(np.average(y, weights=w), 1e-3, 1 - 1e-3)
        self.base = float(np.log(p0 / (1 - p0)))
        F = np.full(n, self.base)
        self.trees = []
        allidx = np.arange(n)
        for t in range(self.n_trees):
            p = 1 / (1 + np.exp(-F))
            g = w * (p - y)
            h = w * p * (1 - p) + 1e-9
            s0 = self._best_split(Xb, g, h, allidx)
            if s0 is None:
                break
            j0, b0 = s0
            L = allidx[Xb[:, j0] <= b0]
            R = allidx[Xb[:, j0] > b0]
            node = [j0, self._thr(j0, b0)]
            leaves = []
            for part in (L, R):
                s1 = self._best_split(Xb, g, h, part)
                if s1 is None:
                    v = -g[part].sum() / (h[part].sum() + self.l2) * self.lr
                    node += [-1, 0.0]
                    leaves += [v, v]
                    F[part] += v
                    continue
                j1, b1 = s1
                node += [j1, self._thr(j1, b1)]
                for sub in (part[Xb[part, j1] <= b1], part[Xb[part, j1] > b1]):
                    v = -g[sub].sum() / (h[sub].sum() + self.l2) * self.lr
                    leaves.append(v)
                    F[sub] += v
            self.trees.append((node, leaves))
        return self

    def _thr(self, j, b):
        e = self.edges[j]
        return float(e[min(b, len(e) - 1)])

    def decision(self, X):
        F = np.full(len(X), self.base)
        for node, leaves in self.trees:
            j0, t0, jl, tl, jr, tr = node
            left = X[:, j0] <= t0
            for side, (jj, tt, off) in ((left, (jl, tl, 0)), (~left, (jr, tr, 2))):
                if jj < 0:
                    F[side] += leaves[off]
                else:
                    sub = X[:, jj] <= tt
                    F[side & sub] += leaves[off]
                    F[side & ~sub] += leaves[off + 1]
        return F


def class_weights(M, idx):
    """Positives: equal total weight per source (esc50, soc2, ice) and per clean/mix.
    Negatives: equal total weight per kind (forest, mech, other, ambig)."""
    y = M['label'][idx] == '1'
    k = M['kind'][idx]
    s = M['src'][idx]
    w = np.zeros(len(idx))
    pg = [(a, b) for a in set(s[y]) for b in set(k[y])]
    for a, b in pg:
        m = y & (s == a) & (k == b)
        if m.any():
            w[m] = 0.5 / (m.sum() * len(pg))
    ng = sorted(set(k[~y]))
    for kk in ng:
        m = (~y) & (k == kk)
        w[m] = 0.5 / (m.sum() * len(ng))
    # weather that sounds like rumble (priority 2): count rain / wind / storm three times
    wx = (~y) & np.isin(M['cls'][idx], ('rain', 'wind', 'thunderstorm'))
    w[wx] *= 3.0
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
    # storm/rain/wind mixtures at -3/+3 dB are evaluation-only: training on them hurt every
    # group in the ablation (AUC 0.953 -> 0.938), probably because the engine is masked
    trainable = ~((M['kind'] == 'engine_mix') & np.isin(M['snr'], ('-3.0', '3.0')))
    for k in range(1, 6):
        tr = np.where(((esc & (fold != k)) | ice) & trainable)[0]
        te = np.where(esc & (fold == k))[0]
        m = make_model().fit(X[tr], y[tr], class_weights(M, tr))
        dec[te] = m.decision(X[te])
    tr = np.where((esc | ice) & trainable)[0]
    m = make_model().fit(X[tr], y[tr], class_weights(M, tr))
    dec[ext] = m.decision(X[ext])
    dec[ice] = m.decision(X[ice])                      # in-sample, for reference only
    return dec, m


def threshold_at_fp(dec, M, fp_target=0.01):
    """Pick threshold on out-of-fold ESC negatives (forest+other+mech) at a target FP rate."""
    # forest-relevant negatives only: nature/weather/people + passing machines (no domestic)
    neg = (((M['src'] == 'esc50') | (M['src'] == 'soc2')) & (M['label'] == '0')
           & ((M['kind'] == 'forest') | (M['kind'] == 'mech')))
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
    models = {'logistic': lambda: Logistic(), 'mlp16': lambda: MLP(), 'gbt': lambda: GBTrees()}
    pick = sys.argv[2].split(',') if len(sys.argv) > 2 else list(models)
    for name, mk in [(k, models[k]) for k in pick]:
        dec, _ = cross_val(X, M, mk)
        for fp in (0.01, 0.03):
            thr = threshold_at_fp(dec, M, fp)
            summary(dec, M, thr, name + ' @%g forest+mech FP' % fp)
        sys.stdout.flush()
