"""Capture device TG JSON telemetry from COM port to JSONL (CPython host).

Usage: python tools/capture_serial.py COM5 --out captures/run.jsonl
pip install pyserial
"""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description='Record LoPy USB logs')
    parser.add_argument('port', help='Serial port, e.g. COM5')
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--out', type=Path, default=Path('captures/run.jsonl'))
    args = parser.parse_args()
    import serial
    args.out.parent.mkdir(parents=True, exist_ok=True)
    print('Recording from', args.port, 'to', args.out, '(Ctrl+C to stop)')
    with serial.Serial(args.port, args.baud, timeout=1) as device, args.out.open('a', encoding='utf-8') as out:
        try:
            while True:
                line = device.readline().decode('utf-8', 'replace').strip()
                if not line:
                    continue
                print(line)
                if not line.startswith('TG '):
                    continue
                try:
                    value = json.loads(line[3:])
                except ValueError:
                    continue
                out.write(json.dumps(value, ensure_ascii=False) + '\n')
                out.flush()
        except KeyboardInterrupt:
            print('Capture stopped')


if __name__ == '__main__':
    main()
