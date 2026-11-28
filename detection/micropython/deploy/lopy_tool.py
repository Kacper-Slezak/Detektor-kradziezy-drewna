"""Lightweight Pycom LoPy serial uploader and runner using pyserial.

Designed for Pycom MicroPython 1.20.2.r6 (MicroPython v1.11) over COMx.
Protects `main.py` and `boot.py` from accidental modification or deletion.
"""

import argparse
import binascii
import os
import sys
import time
import serial

PROTECTED_PATHS = ('/flash/main.py', '/flash/boot.py', 'main.py', 'boot.py')


class LoPySerial:
    def __init__(self, port='COM4', baud=115200, timeout=1.0):
        self.ser = serial.Serial(port, baud, timeout=timeout)
        time.sleep(0.2)

    def close(self):
        try:
            self.ser.write(b'\x02')  # exit raw REPL
            time.sleep(0.1)
        except Exception:
            pass
        self.ser.close()

    def enter_raw_repl(self):
        self.ser.write(b'\r\x03\x03')
        time.sleep(0.3)
        self.ser.read_all()
        self.ser.write(b'\r\x01')
        deadline = time.time() + 3.0
        buf = b''
        while time.time() < deadline:
            chunk = self.ser.read_all()
            if chunk:
                buf += chunk
                if b'raw REPL; CTRL-B to exit' in buf or buf.endswith(b'>'):
                    return
            time.sleep(0.05)
        raise RuntimeError('Failed to enter raw REPL. Received: %r' % (buf,))

    def soft_reset_raw(self):
        """Soft reset inside raw REPL to get a clean heap without running main.py."""
        self.enter_raw_repl()
        self.ser.write(b'\x04')
        deadline = time.time() + 4.0
        buf = b''
        while time.time() < deadline:
            chunk = self.ser.read_all()
            if chunk:
                buf += chunk
                if b'raw REPL; CTRL-B to exit' in buf or buf.endswith(b'>'):
                    return
            time.sleep(0.05)

    def exec_raw(self, code, timeout=30.0, stream_stdout=False):
        if isinstance(code, str):
            code = code.encode('utf-8')
        # Send in small chunks to avoid UART RX FIFO overflow on ESP32
        for i in range(0, len(code), 128):
            self.ser.write(code[i:i + 128])
            time.sleep(0.01)
        self.ser.write(b'\x04')

        # Wait for OK
        buf = b''
        deadline = time.time() + timeout
        ok_seen = False
        while time.time() < deadline:
            chunk = self.ser.read_all()
            if chunk:
                buf += chunk
                if not ok_seen and b'OK' in buf:
                    ok_seen = True
                    buf = buf.split(b'OK', 1)[1]
                if ok_seen:
                    # Raw REPL ends output with \x04<stderr>\x04>
                    if buf.count(b'\x04') >= 2 and buf.endswith(b'>'):
                        break
            time.sleep(0.02)

        if not ok_seen:
            raise RuntimeError('No OK from raw REPL: %r' % (buf,))
        parts = buf.split(b'\x04')
        out = parts[0].decode('utf-8', 'replace')
        err = parts[1].decode('utf-8', 'replace') if len(parts) > 1 else ''
        if stream_stdout and out:
            sys.stdout.write(out)
            sys.stdout.flush()
        return out, err

    def ensure_dir(self, remote_dir):
        remote_dir = remote_dir.rstrip('/')
        if not remote_dir or remote_dir == '/flash':
            return
        code = (
            "import os\n"
            "try:\n"
            "    os.mkdir(%r)\n"
            "except OSError:\n"
            "    pass\n"
        ) % (remote_dir,)
        _, err = self.exec_raw(code, timeout=5.0)
        if err:
            raise RuntimeError('mkdir %s failed: %s' % (remote_dir, err))

    def upload_file(self, local_path, remote_path):
        norm = remote_path.replace('\\', '/')
        if norm in PROTECTED_PATHS:
            raise ValueError('Refusing to overwrite protected file: %s' % norm)
        parent = norm.rsplit('/', 1)[0]
        if parent and parent != '/flash':
            self.ensure_dir(parent)

        with open(local_path, 'rb') as f:
            data = f.read()

        # Open file on device
        _, err = self.exec_raw("f = open(%r, 'wb')\n" % (norm,), timeout=5.0)
        if err:
            raise RuntimeError('open %s failed: %s' % (norm, err))

        chunk_size = 256
        for i in range(0, len(data), chunk_size):
            b64 = binascii.b2a_base64(data[i:i + chunk_size]).decode('ascii').strip()
            cmd = "import ubinascii; f.write(ubinascii.a2b_base64(%r))\n" % (b64,)
            _, err = self.exec_raw(cmd, timeout=5.0)
            if err:
                self.exec_raw("f.close()\n", timeout=5.0)
                raise RuntimeError('write %s failed at %d: %s' % (norm, i, err))

        _, err = self.exec_raw("f.close()\nimport os; print(os.stat(%r)[6])\n" % (norm,), timeout=5.0)
        if err:
            raise RuntimeError('close/stat %s failed: %s' % (norm, err))
        return len(data)


def cmd_info(dev):
    dev.enter_raw_repl()
    code = (
        "import os, sys, gc, machine\n"
        "gc.collect()\n"
        "print('UNAME:', os.uname())\n"
        "print('IMPL:', sys.implementation)\n"
        "print('FREQ_MHZ:', machine.freq() // 1000000)\n"
        "print('HEAP_FREE:', gc.mem_free())\n"
        "print('HEAP_ALLOC:', gc.mem_alloc())\n"
        "st = os.statvfs('/flash')\n"
        "print('FLASH_FREE_B:', st[0] * st[3])\n"
        "print('FLASH_FILES:', os.listdir('/flash'))\n"
        "if 'lib' in os.listdir('/flash'):\n"
        "    print('LIB_FILES:', os.listdir('/flash/lib'))\n"
        "if 'tg_demo' in os.listdir('/flash'):\n"
        "    print('TG_DEMO_FILES:', os.listdir('/flash/tg_demo'))\n"
    )
    out, err = dev.exec_raw(code, timeout=10.0)
    print(out, end='')
    if err:
        sys.stderr.write(err)
        sys.exit(1)


def cmd_upload(dev, local_path, remote_path):
    dev.enter_raw_repl()
    n = dev.upload_file(local_path, remote_path)
    print('Uploaded %s -> %s (%d bytes)' % (local_path, remote_path, n))


def cmd_upload_dir(dev, local_dir, remote_dir):
    dev.enter_raw_repl()
    dev.ensure_dir(remote_dir)
    total = 0
    for root, _, files in os.walk(local_dir):
        for name in sorted(files):
            if name.endswith('.pyc') or '__pycache__' in root:
                continue
            src = os.path.join(root, name)
            rel = os.path.relpath(src, local_dir).replace('\\', '/')
            dst = remote_dir.rstrip('/') + '/' + rel
            n = dev.upload_file(src, dst)
            total += n
            print('Uploaded %s -> %s (%d bytes)' % (src, dst, n))
    print('Total uploaded: %d bytes' % total)


def cmd_run(dev, code, timeout, reset):
    if reset:
        dev.soft_reset_raw()
    else:
        dev.enter_raw_repl()
    out, err = dev.exec_raw(code, timeout=timeout, stream_stdout=True)
    if err:
        sys.stderr.write('DEVICE STDERR:\n' + err)
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description='Pycom LoPy serial deployment tool')
    p.add_argument('--port', default='COM4')
    p.add_argument('--baud', type=int, default=115200)
    sub = p.add_subparsers(dest='cmd', required=True)

    sub.add_parser('info')

    up = sub.add_parser('upload')
    up.add_argument('local_path')
    up.add_argument('remote_path')

    upd = sub.add_parser('upload-dir')
    upd.add_argument('local_dir')
    upd.add_argument('remote_dir')

    rn = sub.add_parser('run')
    rn.add_argument('code')
    rn.add_argument('--timeout', type=float, default=60.0)
    rn.add_argument('--reset', action='store_true')

    args = p.parse_args()
    dev = LoPySerial(port=args.port, baud=args.baud)
    try:
        if args.cmd == 'info':
            cmd_info(dev)
        elif args.cmd == 'upload':
            cmd_upload(dev, args.local_path, args.remote_path)
        elif args.cmd == 'upload-dir':
            cmd_upload_dir(dev, args.local_dir, args.remote_dir)
        elif args.cmd == 'run':
            cmd_run(dev, args.code, args.timeout, args.reset)
    finally:
        dev.close()


if __name__ == '__main__':
    main()
