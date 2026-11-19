"""Stage only the files required for diagnostic v4.6 Pycom LoPy deployment.

Does NOT flash hardware or activate alarms. Measure actual heap/CPU before
using this configuration outside a bench environment.
"""
from __future__ import annotations
import argparse,shutil
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,default=Path('algorithm/results/v4_6_wideband/tg_model_v46.py'))
    p.add_argument('--output',type=Path,default=Path('algorithm/results/v4_6_wideband/flash_stage'))
    args=p.parse_args()
    if not args.model.is_file():raise FileNotFoundError(args.model)
    if args.output.exists():raise FileExistsError('Output already exists: '+str(args.output))
    firmware=Path('firmware')
    args.output.mkdir(parents=True)
    shutil.copy2(firmware/'main.py',args.output/'main.py')
    # One source of truth, guaranteed diagnostic-only config.
    cfg_source=(firmware/'config.py').read_text(encoding='utf8')
    if "ALARM_OUTPUT_PIN = None" not in cfg_source or "ENABLE_PHYSICAL_ALARM = False" not in cfg_source:
        raise ValueError('Staging is restricted to diagnostic-only configuration')
    shutil.copy2(firmware/'config.py',args.output/'config.py')
    lib=args.output/'lib';lib.mkdir()
    names=('tg_v46_device.py','tg_temporal_v46.py','tg_cnn_v46.py',
           'tg_presence_v46.py','tg_sampling_v46.py','tg_hardware.py')
    for name in names:shutil.copy2(firmware/'lib'/name,lib/name)
    shutil.copy2(args.model,lib/'tg_model_v46.py')
    shutil.copy2(firmware/'lopy_v46_memory_probe.py',args.output/'lopy_v46_memory_probe.py')
    files=list(args.output.rglob('*'))
    size=sum(p.stat().st_size for p in files if p.is_file())
    print('DIAGNOSTIC STAGE:',args.output)
    print('Application files:',sum(p.is_file() for p in files),'size:',size,'bytes')
    print('Device NOT flashed. Alarm disabled. MicroPython heap/timing UNVERIFIED.')
if __name__=='__main__':main()
