"""Build minimal, self-contained LoPy 1.0 deployment packages.

Creates two independent packages under `detection/micropython/deploy/`:
1. `deploy/burst/`   - Primary low-memory candidate (Burst MLP).
2. `deploy/cnn_v46/` - Preferred CNN v4.6 with binary-streamed INT8 weights
                       (exact unmodified weights from `tg_model_v46.py`).
"""

import base64
import importlib.util
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_DIR = ROOT / 'deploy'
LIB_DIR = ROOT / 'firmware' / 'lib'
V46_MODEL_SRC = ROOT / 'algorithm' / 'results' / 'v4_6_wideband' / 'tg_model_v46.py'


def _export_v46_binary(src_path, dst_dir):
    """Export exact unmodified v4.6 INT8 weights into binary file + tiny metadata."""
    spec = importlib.util.spec_from_file_location('tg_model_v46_export', src_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    wc = base64.b64decode(mod.WEIGHT_B64[0])
    wd = base64.b64decode(mod.WEIGHT_B64[1])
    wo = base64.b64decode(mod.WEIGHT_B64[2])

    channels = int(mod.CONV_CHANNELS)
    hidden_n = int(mod.HIDDEN)
    pool_size = 12 * channels + 9
    assert len(wc) == 9 * channels
    assert len(wd) == pool_size * hidden_n
    assert len(wo) == hidden_n

    # Transpose wd from [pool_size, hidden_n] to [hidden_n, pool_size]
    # so LoPy streams one 201-byte row per hidden unit sequentially from flash.
    wd_t = bytearray(len(wd))
    for j in range(hidden_n):
        row_dst = j * pool_size
        for i in range(pool_size):
            wd_t[row_dst + i] = wd[i * hidden_n + j]

    bin_name = 'tg_v46_weights.bin'
    bin_path = dst_dir / bin_name
    bin_path.write_bytes(wc + bytes(wd_t) + wo)

    meta_lines = [
        '"""Compact binary-backed v4.6 CNN metadata (exact unmodified weights)."""',
        'MODEL_TYPE = %r' % (mod.MODEL_TYPE,),
        'RATE = %d' % int(mod.RATE),
        'CONV_CHANNELS = %d' % channels,
        'HIDDEN = %d' % hidden_n,
        'THRESHOLD = %r' % float(mod.THRESHOLD),
        'MEAN = %r' % (tuple(mod.MEAN),),
        'INV_STD = %r' % (tuple(mod.INV_STD),),
        'E_MEAN = %r' % (tuple(mod.E_MEAN),),
        'E_INV_STD = %r' % (tuple(mod.E_INV_STD),),
        'SCALES = %r' % (tuple(mod.SCALES),),
        'BIASES = %r' % (tuple(tuple(b) for b in mod.BIASES),),
        'WEIGHT_BIN = %r' % (bin_name,),
        '',
    ]
    (dst_dir / 'tg_model_v46_bin.py').write_text('\n'.join(meta_lines), encoding='utf-8')


def build():
    # 1. Burst MLP package
    burst_dir = DEPLOY_DIR / 'burst'
    if burst_dir.exists():
        shutil.rmtree(burst_dir)
    burst_dir.mkdir(parents=True)
    for name in ('tg_stream_detector.py', 'tg_burst.py', 'tg_model_burst.py'):
        shutil.copy2(LIB_DIR / name, burst_dir / name)
    shutil.copy2(DEPLOY_DIR / 'lopy_demo.py', burst_dir / 'lopy_demo.py')

    # 2. CNN v4.6 binary-streamed package (if trained v4.6 model exists locally)
    cnn_dir = DEPLOY_DIR / 'cnn_v46'
    if cnn_dir.exists():
        shutil.rmtree(cnn_dir)
    if V46_MODEL_SRC.is_file():
        cnn_dir.mkdir(parents=True)
        shutil.copy2(LIB_DIR / 'tg_stream_detector.py', cnn_dir / 'tg_stream_detector.py')
        shutil.copy2(DEPLOY_DIR / 'lopy_demo.py', cnn_dir / 'lopy_demo.py')
        _export_v46_binary(V46_MODEL_SRC, cnn_dir)

    for pkg_name, pkg_dir in (('burst', burst_dir), ('cnn_v46', cnn_dir)):
        if not pkg_dir.exists():
            print('%s: skipped (source model missing)' % pkg_name)
            continue
        files = sorted(p for p in pkg_dir.iterdir() if p.is_file())
        total = sum(p.stat().st_size for p in files)
        print('Package %s (%d bytes total):' % (pkg_name, total))
        for p in files:
            print('  - %s (%d B)' % (p.name, p.stat().st_size))


if __name__ == '__main__':
    build()
