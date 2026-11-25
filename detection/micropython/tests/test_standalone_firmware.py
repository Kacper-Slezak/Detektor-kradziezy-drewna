"""Verification tests for stabilized single-file Pycom LoPy 1.0 `main.py` builds.

Covers:
- Python syntax, self-contained built-in imports, and Pycom 1.20.2.r6 / v1.11 rules.
- Embedded INT8 weight integrity and exact numerical parity with `tg_stream_detector`.
- Full firmware state machine (RTC, PIN wake with single audio capture, cold boot).
- First-boot missing NVS key handling, Wi-Fi/HTTP failure recovery, HTTP 2xx check.
- `machine.pin_sleep_wakeup` API usage and stuck-HIGH infinite-loop protection.
- Fail-closed behavior on ADC/inference errors and standalone diagnostic mode.
"""

import ast
import base64
import binascii
import importlib.util
from pathlib import Path
import struct
import sys
import types
import unittest
import wave

MICROPYTHON_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = MICROPYTHON_ROOT / 'firmware' / 'lib'
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import tg_model_burst
import tg_stream_detector as sd

BURST_MAIN = MICROPYTHON_ROOT / 'deploy' / 'burst' / 'main.py'
CNN_MAIN = MICROPYTHON_ROOT / 'deploy' / 'cnn_v46' / 'main.py'
V46_MODEL_SRC = MICROPYTHON_ROOT / 'algorithm' / 'results' / 'v4_6_wideband' / 'tg_model_v46.py'
FOREST_4K_WAV = MICROPYTHON_ROOT / 'algorithm' / 'sample_audio' / 'forest-ambience-4k.wav'
TRUCK_4K_WAV = MICROPYTHON_ROOT / 'algorithm' / 'sample_audio' / 'forest-with-truck-4k.wav'


def _load_v46_model():
    if not V46_MODEL_SRC.is_file():
        return None
    spec = importlib.util.spec_from_file_location('tg_model_v46_verify', V46_MODEL_SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read_wav_adc_blocks(wav_path, start_s=0, num_blocks=10):
    with wave.open(str(wav_path), 'rb') as wf:
        wf.setpos(start_s * 4000)
        blocks = []
        for _ in range(num_blocks):
            raw = wf.readframes(4000)
            samples = struct.unpack('<4000h', raw)
            buf = bytearray(8000)
            idx = 0
            for s in samples:
                adc = max(0, min(4095, (s + 32768) >> 4))
                buf[idx] = adc & 0xFF
                buf[idx + 1] = (adc >> 8) & 0xFF
                idx += 2
            blocks.append(buf)
        return blocks


def _load_standalone_with_mocks(main_path, wake_reason=(0, None), pin_values=None,
                                wifi_fail=False, nvs_store=None, http_status=200):
    """Load standalone main.py under mocked Pycom 1.20.2.r6 hardware modules."""
    pin_values = dict(pin_values or {})
    nvs = {} if nvs_store is None else nvs_store
    events = {
        'sleep_wakeup_calls': [],
        'deepsleep_calls': [],
        'wifi_connects': 0,
        'http_sent': [],
    }

    class FakePin:
        IN = 0
        PULL_DOWN = 1

        def __init__(self, pid, mode=0, pull=None):
            self._id = pid

        def id(self):
            return self._id

        def value(self):
            return pin_values.get(self._id, 0)

    class FakeADC:
        ATTN_11DB = 3

        def __init__(self, *args, **kwargs):
            pass

        def channel(self, pin='P16', attn=3):
            return lambda: 2048

    fake_machine = types.ModuleType('machine')
    fake_machine.Pin = FakePin
    fake_machine.ADC = FakeADC
    fake_machine.RTC_WAKE = 2
    fake_machine.PIN_WAKE = 1
    fake_machine.PWRON_WAKE = 0
    fake_machine.WAKEUP_ANY_HIGH = 1
    fake_machine.wake_reason = lambda: wake_reason
    fake_machine.pin_sleep_wakeup = lambda pins, mode=1, enable_pull=False: (
        events['sleep_wakeup_calls'].append((pins, mode, enable_pull))
    )
    fake_machine.deepsleep = lambda *args: events['deepsleep_calls'].append(args)

    class FakeWLAN:
        STA = 1
        WPA2 = 3

        def __init__(self, mode=1):
            self._conn = False

        def isconnected(self):
            return self._conn

        def connect(self, ssid, auth=None, timeout=10000):
            events['wifi_connects'] += 1
            if wifi_fail:
                raise OSError('Connection to AP Timeout!')
            self._conn = True

        def ifconfig(self):
            return ('192.168.1.50', '255.255.255.0', '192.168.1.1', '8.8.8.8')

    fake_network = types.ModuleType('network')
    fake_network.WLAN = FakeWLAN

    class FakeSocket:
        def __init__(self):
            self._sent = b''
            self._resp_read = False

        def settimeout(self, t):
            pass

        def connect(self, addr):
            pass

        def send(self, data):
            self._sent += data
            return len(data)

        def recv(self, n):
            if self._resp_read:
                return b''
            self._resp_read = True
            events['http_sent'].append(self._sent)
            return ('HTTP/1.1 %d OK\r\nContent-Length: 2\r\n\r\nOK' % http_status).encode()

        def close(self):
            pass

    fake_usocket = types.ModuleType('usocket')
    fake_usocket.getaddrinfo = lambda host, port: [(2, 1, 0, '', (host, port))]
    fake_usocket.socket = FakeSocket

    fake_ubinascii = types.ModuleType('ubinascii')
    fake_ubinascii.hexlify = binascii.hexlify

    fake_pycom = types.ModuleType('pycom')
    fake_pycom.heartbeat = lambda flag: None

    def _nvs_get(k):
        if k not in nvs:
            raise ValueError('No matching object for the provided key')
        return nvs[k]

    def _nvs_set(k, v):
        nvs[k] = v

    fake_pycom.nvs_get = _nvs_get
    fake_pycom.nvs_set = _nvs_set

    saved = {}
    injected = {
        'machine': fake_machine,
        'network': fake_network,
        'usocket': fake_usocket,
        'ubinascii': fake_ubinascii,
        'pycom': fake_pycom,
    }
    for k, v in injected.items():
        saved[k] = sys.modules.get(k)
        sys.modules[k] = v

    try:
        src = main_path.read_text(encoding='utf-8')
        mod = types.ModuleType('standalone_fw_test')
        mod.__file__ = str(main_path)
        exec(compile(src, str(main_path), 'exec'), mod.__dict__)
        # Speed up sleep calls in unit tests
        mod.time = types.SimpleNamespace(
            sleep=lambda s: None,
            ticks_ms=lambda: 0,
            ticks_us=lambda: 0,
            ticks_add=lambda a, b: a + b,
            ticks_diff=lambda a, b: a - b,
        )
        return mod, events, nvs
    finally:
        for k, prev in saved.items():
            if prev is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = prev


class TestStandaloneFirmware(unittest.TestCase):
    def test_pycom_v111_api_and_static_constraints(self):
        allowed_mods = {
            'machine', 'network', 'usocket', 'time', 'ubinascii',
            'struct', 'pycom', 'gc', 'array', 'math',
        }
        targets = (
            BURST_MAIN,
            CNN_MAIN,
            LIB_DIR / 'tg_stream_detector.py',
            LIB_DIR / 'tg_burst.py',
            LIB_DIR / 'tg_burst_device.py',
        )
        for path in targets:
            with self.subTest(path=str(path)):
                src = path.read_text(encoding='utf-8')
                self.assertNotIn('pin_deepsleep_wakeup', src)
                tree = ast.parse(src, filename=str(path))
                for node in ast.walk(tree):
                    if path in (BURST_MAIN, CNN_MAIN):
                        if isinstance(node, ast.Import):
                            for a in node.names:
                                self.assertIn(a.name, allowed_mods)
                        elif isinstance(node, ast.ImportFrom):
                            self.assertIn(node.module, allowed_mods)
                    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
                        for side in (node.left, node.right):
                            is_arr = (
                                isinstance(side, ast.Call)
                                and isinstance(side.func, ast.Name)
                                and side.func.id == 'array'
                            )
                            self.assertFalse(is_arr, 'Forbidden array * int in %s' % path)
                    elif (isinstance(node, ast.Call)
                          and isinstance(node.func, ast.Name)
                          and node.func.id == 'array'):
                        for arg in node.args:
                            self.assertNotIsInstance(arg, ast.GeneratorExp)

    def test_signature_return_and_embedded_weight_integrity(self):
        for path in (BURST_MAIN, CNN_MAIN):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            fn = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'analizuj_sygnaly'][0]
            self.assertEqual([a.arg for a in fn.args.args], ['mic_aktywny', 'vib_aktywny'])
            last = fn.body[-1]
            self.assertIsInstance(last, ast.Return)
            self.assertEqual([e.id for e in last.value.elts], ['czy_alarm', 'event_type', 'confidence'])

        # Burst weights (compact `WT` or `WEIGHTS`)
        tree_b = ast.parse(BURST_MAIN.read_text(encoding='utf-8'))
        fn_b = [n for n in tree_b.body if isinstance(n, ast.FunctionDef) and n.name == 'analizuj_sygnaly'][0]
        w_b = [ast.literal_eval(n.value) for n in fn_b.body
               if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
               and n.targets[0].id in ('WEIGHTS', 'WT')][0]
        self.assertEqual(w_b, bytes(tg_model_burst.WEIGHTS))

        # CNN v4.6 weights
        v46 = _load_v46_model()
        if v46 is not None:
            tree_c = ast.parse(CNN_MAIN.read_text(encoding='utf-8'))
            fn_c = [n for n in tree_c.body if isinstance(n, ast.FunctionDef) and n.name == 'analizuj_sygnaly'][0]
            assigns = {
                n.targets[0].id: ast.literal_eval(n.value)
                for n in fn_c.body
                if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                and n.targets[0].id in ('WC', 'WD', 'WO')
            }
            self.assertEqual(assigns['WC'], base64.b64decode(v46.WEIGHT_B64[0]))
            self.assertEqual(assigns['WD'], base64.b64decode(v46.WEIGHT_B64[1]))
            self.assertEqual(assigns['WO'], base64.b64decode(v46.WEIGHT_B64[2]))

    def test_parity_with_modular_detector(self):
        if not (FOREST_4K_WAV.is_file() and TRUCK_4K_WAV.is_file()):
            self.skipTest('Local 4k WAV samples not present')

        forest_blocks = _read_wav_adc_blocks(FOREST_4K_WAV, start_s=0, num_blocks=10)
        truck_blocks = _read_wav_adc_blocks(TRUCK_4K_WAV, start_s=18, num_blocks=10)

        cases = [('burst', BURST_MAIN, tg_model_burst)]
        v46 = _load_v46_model()
        if v46 is not None:
            cases.append(('cnn_v46', CNN_MAIN, v46))

        for label, main_path, model in cases:
            for clip_name, blocks, vib in (('forest_bg', forest_blocks, True), ('truck_eng', truck_blocks, True)):
                with self.subTest(model=label, clip=clip_name):
                    det = sd.Detector(model=model)
                    for blk in blocks:
                        det.process(blk)
                    ref_res = det.finalize(vib_active=vib, mic_active=True)

                    mod, _, _ = _load_standalone_with_mocks(main_path)
                    def _gen():
                        shared = bytearray(8000)
                        for b in blocks:
                            shared[:] = b
                            yield shared
                    mod.nagraj_audio = _gen
                    czy_alarm, event_type, confidence = mod.analizuj_sygnaly(True, vib)

                    self.assertEqual(czy_alarm, ref_res['alarm'])
                    self.assertEqual(event_type, ref_res['event_type'])
                    self.assertEqual(confidence, ref_res['confidence'])

    def test_cold_boot_first_nvs_and_wifi_failure_recovery(self):
        mod, events, nvs = _load_standalone_with_mocks(
            BURST_MAIN, wake_reason=(0, None), wifi_fail=True
        )
        mod.main()
        # Missing NVS keys initialized cleanly without crash
        self.assertEqual(nvs.get('boot_id'), 1)
        self.assertEqual(nvs.get('pkt_cnt'), 1)
        # Wi-Fi failed gracefully and still entered sensor deep sleep via pin_sleep_wakeup
        self.assertEqual(events['wifi_connects'], 1)
        self.assertEqual(len(events['sleep_wakeup_calls']), 1)
        self.assertEqual(events['sleep_wakeup_calls'][0][0], ['P19', 'P20'])
        self.assertEqual(events['deepsleep_calls'], [()])

    def test_stuck_high_pin_avoids_infinite_wakeup_loop(self):
        mod, events, _ = _load_standalone_with_mocks(
            BURST_MAIN, wake_reason=(0, None), pin_values={'P19': 1}, wifi_fail=True
        )
        mod.main()
        # Should fall back to timed hard sleep (CZAS_SNU_SZTYWNEGO_MS) instead of pin sleep
        self.assertEqual(events['deepsleep_calls'], [(mod.CZAS_SNU_SZTYWNEGO_MS,)])

    def test_pin_wake_single_audio_acquisition_and_fail_closed(self):
        # 1. Verify nagraj_audio() is called EXACTLY ONCE per PIN_WAKE session
        mod, events, _ = _load_standalone_with_mocks(
            BURST_MAIN, wake_reason=(1, ['P19']), http_status=200
        )
        calls = {'n': 0}

        def _fake_nagraj():
            calls['n'] += 1
            buf = bytearray(8000)
            for _ in range(3):
                yield buf

        mod.nagraj_audio = _fake_nagraj
        mod.main()
        self.assertEqual(calls['n'], 1)
        self.assertEqual(events['deepsleep_calls'], [(mod.CZAS_SNU_SZTYWNEGO_MS,)])

        # 2. Fail-closed on ADC error: never report clean inference_ok or send alarm
        mod2, events2, _ = _load_standalone_with_mocks(
            BURST_MAIN, wake_reason=(1, ['P19'])
        )
        def _failing_nagraj():
            raise OSError('ADC failure')
            yield bytearray(8000)

        mod2.nagraj_audio = _failing_nagraj
        mod2.main()
        self.assertEqual(events2['http_sent'], [])
        self.assertEqual(events2['deepsleep_calls'], [(mod2.CZAS_SNU_SZTYWNEGO_MS,)])

    def test_http_non_2xx_returns_false(self):
        mod, _, _ = _load_standalone_with_mocks(BURST_MAIN, http_status=500)
        ok = mod.wyslij_payload(b'\x21\x00\x01\x01\x01\x50\x00\x02\x60\x64')
        self.assertFalse(ok)

    def test_compact_burst_size_below_previous_bootable_threshold(self):
        self.assertLessEqual(BURST_MAIN.stat().st_size, 22244)
        src = BURST_MAIN.read_text(encoding='utf-8')
        self.assertNotIn('tryb_diagnostyczny', src)
        self.assertNotIn('_syntetyczne_audio', src)


if __name__ == '__main__':
    unittest.main()
