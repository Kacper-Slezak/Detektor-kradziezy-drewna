"""Compute session feature vectors for all cached sessions -> $TG_DATA/cache/sfeat_<tag>.npy"""

import multiprocessing as mp
import sys

import numpy as np

import cache
import features


def build(tag='v2'):
    S, M = cache.load(tag)
    with mp.Pool(mp.cpu_count()) as p:
        X = np.array(p.map(features.session_features, S, chunksize=8), dtype=np.float64)
    np.save(cache.devsim.DATA / 'cache' / ('sfeat_%s.npy' % tag), X)
    return X


def load(tag='v2'):
    return np.load(cache.devsim.DATA / 'cache' / ('sfeat_%s.npy' % tag))


if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else 'v2')
