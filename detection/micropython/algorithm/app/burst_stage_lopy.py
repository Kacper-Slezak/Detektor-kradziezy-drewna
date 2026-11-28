"""Stage the diagnostic burst monitor for the original Pycom LoPy."""

import argparse
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import shutil

from firmware.lib.tg_burst import Classifier

FIRMWARE = Path(__file__).resolve().parents[2] / 'firmware'
DEFAULT_MODEL = FIRMWARE / 'lib' / 'tg_model_burst.py'


def read_export(path):
    if not path.is_file():
        raise FileNotFoundError(path)
    spec = spec_from_file_location('burst_export', path)
    model = module_from_spec(spec)
    spec.loader.exec_module(model)
    Classifier(model)
    return model


def stage(output, model_path, accel=False, bench=False):
    read_export(model_path)
    config = (FIRMWARE / 'config.py').read_text(encoding='utf8')
    config = config.replace("MODEL_FLAVOR = 'v4_6'", "MODEL_FLAVOR = 'burst'")
    if accel:
        config = config.replace('ACCEL_ENABLED = False', 'ACCEL_ENABLED = True')
    lib = output / 'lib'
    output.mkdir(parents=True, exist_ok=False)
    lib.mkdir()
    (output / 'config.py').write_text(config, encoding='utf8')
    for name in ('main.py', 'lopy_burst_probe.py'):
        shutil.copy2(FIRMWARE / name, output / name)
    for name in ('tg_burst.py', 'tg_burst_device.py', 'tg_hardware.py'):
        shutil.copy2(FIRMWARE / 'lib' / name, lib / name)
    shutil.copy2(model_path, lib / 'tg_model_burst.py')
    if bench:
        shutil.copy2(FIRMWARE / 'lopy_bench.py', output / 'lopy_bench.py')
        shutil.copy2(FIRMWARE / 'lib' / 'tg_burst_capture.py', lib / 'tg_burst_capture.py')
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        (output / 'lopy_bench_build.py').write_text(f'MODEL_SHA256 = {digest!r}\n', encoding='ascii')
    size = sum(p.stat().st_size for p in output.rglob('*.py'))
    print(f'Staged {size} bytes of Python source in {output}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    parser.add_argument('--accel', action='store_true', help='Report optional ADXL345 XYZ readings')
    parser.add_argument('--bench', action='store_true', help='Include the optional REPL bench and SD recorder')
    args = parser.parse_args()
    stage(args.output, args.model, args.accel, args.bench)


if __name__ == '__main__':
    main()
