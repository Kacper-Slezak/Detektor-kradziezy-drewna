"""Evaluate a standalone main.py (default: Kiryl's deploy/burst/main.py) on cached sessions.

    python eval_firmware.py [path/to/main.py] [cache_tag]
"""

import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np

import cache
import firmware_runner
import metrics

DEFAULT = Path(__file__).resolve().parents[1] / 'deploy' / 'burst' / 'main.py'
_MOD = None


def _init(path):
    global _MOD
    _MOD = firmware_runner.load_main(path)


def _one(codes):
    try:
        a, et, conf = firmware_runner.run_session(_MOD, codes)
        lg = float(_MOD.V2_OSTATNI[0]) if hasattr(_MOD, 'V2_OSTATNI') else float('nan')
        return int(bool(a)), int(conf), lg
    except Exception:
        return -1, -1, float('nan')


def evaluate(path, tag='v1', procs=None):
    S, M = cache.load(tag)
    with mp.Pool(procs or mp.cpu_count(), initializer=_init, initargs=(str(path),)) as p:
        res = p.map(_one, S, chunksize=16)
    res = np.array(res)
    return res, M


if __name__ == '__main__':
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    tag = sys.argv[2] if len(sys.argv) > 2 else 'v1'
    res, M = evaluate(path, tag)
    print('errors:', int((res[:, 0] < 0).sum()))
    alarm = res[:, 0] == 1
    metrics.report(alarm, M, str(path))
    y = M['label'] == '1'
    print('session AUC (confidence) all levels: %.3f' % metrics.auc(res[:, 1], y))
    np.save(Path(cache.devsim.DATA) / 'cache' / ('res_%s_%s.npy' % (path.parent.name, tag)), res)
