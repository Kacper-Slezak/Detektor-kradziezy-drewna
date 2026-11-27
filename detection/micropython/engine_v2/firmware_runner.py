"""Run a standalone LoPy main.py's `analizuj_sygnaly` on PC with mocked Pycom modules.

The firmware code itself is executed unchanged; only `nagraj_audio` is replaced by a
generator that yields 8000-byte little-endian blocks built from simulated ADC codes.
"""

import importlib.util
import sys
import types

import numpy as np


def _stub_modules():
    class Pin:
        IN = 0
        PULL_DOWN = 1
        IRQ_RISING = 1

        def __init__(self, *a, **k):
            pass

        def value(self):
            return 0

    class ADC:
        ATTN_11DB = 3

        def __init__(self, *a, **k):
            pass

    machine = types.ModuleType('machine')
    machine.Pin = Pin
    machine.ADC = ADC
    machine.RTC_WAKE = 2
    machine.PIN_WAKE = 1
    machine.WAKEUP_ANY_HIGH = 1
    machine.wake_reason = lambda: (0, None)
    machine.deepsleep = lambda *a: None
    machine.pin_sleep_wakeup = lambda *a, **k: None
    network = types.ModuleType('network')
    network.WLAN = object
    pycom = types.ModuleType('pycom')
    pycom.heartbeat = lambda *a: None
    pycom.nvs_get = lambda k: None
    pycom.nvs_set = lambda k, v: None
    import binascii
    import socket
    sys.modules.update(machine=machine, network=network, pycom=pycom,
                       usocket=socket, ubinascii=binascii)


def load_main(path, name='fw_main'):
    _stub_modules()
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def adc_blocks(codes):
    """codes: (n,) int ADC 0..4095 -> list of 8000-byte blocks (whole seconds only)."""
    n = len(codes) // 4000
    out = []
    for b in range(n):
        c = np.asarray(codes[b * 4000:(b + 1) * 4000], dtype='<u2')
        out.append(bytearray(c.tobytes()))
    return out


def run_session(mod, codes, mic=True, vib=False):
    blocks = adc_blocks(codes)

    def fake_rec(*a, **k):
        for b in blocks:
            yield b

    mod.nagraj_audio = fake_rec
    return mod.analizuj_sygnaly(mic, vib)
