"""Parity: MicroPython-style tg_v2_device vs numpy features.py on simulated sessions.

    cd detection/micropython/engine_v2 && python -m unittest test_v2_device
"""
import unittest

import numpy as np

import features
import tg_v2_device as dev


def _session(seed, kind):
    rng = np.random.default_rng(seed)
    n = 10 * 4000
    t = np.arange(n) / 4000.0
    if kind == 'engine':
        f0 = 31.0 + 0.5 * np.sin(2 * np.pi * 0.1 * t)
        ph = 2 * np.pi * np.cumsum(f0) / 4000.0
        x = sum(np.cos(h * ph) / h for h in range(1, 25)) + 0.3 * rng.normal(0, 1, n)
    else:
        x = np.cumsum(rng.normal(0, 1, n))
        x -= np.convolve(x, np.ones(200) / 200, 'same')
    x = x / x.std() * 150 + 2048
    return np.clip(np.round(x), 0, 4095).astype(np.int32)


def _blocks(codes):
    return [bytearray(codes[i * 4000:(i + 1) * 4000].astype('<u2').tobytes())
            for i in range(len(codes) // 4000)]


class ParityTest(unittest.TestCase):
    def check(self, codes):
        ref = features.session_features(codes)
        st = dev.V2State()
        for b in _blocks(codes):
            st.add_block(b)
        got = np.array(st.session_vector())
        self.assertEqual(got.shape, ref.shape)
        err = np.abs(got - ref) / (np.abs(ref) + 1.0)
        bad = [(features.NAMES[i], ref[i], got[i]) for i in np.where(err > 1e-4)[0]]
        self.assertFalse(bad, bad)

    def test_engine(self):
        self.check(_session(1, 'engine'))

    def test_noise(self):
        self.check(_session(2, 'noise'))

    def test_gain_invariance(self):
        c = _session(3, 'engine')
        a = features.session_features(c)
        c2 = np.clip(np.round((c - 2048) * 0.25 + 2048), 0, 4095).astype(np.int32)
        b = features.session_features(c2)
        i = [features.NAMES.index(n) for n in ('tb_lo', 'harm_mu', 'lowhi_mu', 'cos_bands')]
        np.testing.assert_allclose(a[i], b[i], atol=0.05)


if __name__ == '__main__':
    unittest.main()


class FirmwareTest(unittest.TestCase):
    """deploy/v2/main.py end to end (mocked Pycom) vs the numpy features + int8 model."""

    @classmethod
    def setUpClass(cls):
        import json
        from pathlib import Path
        import firmware_runner
        here = Path(__file__).resolve().parent
        cls.mod = firmware_runner.load_main(here.parent / 'deploy' / 'v2' / 'main.py')
        cls.run_fw = staticmethod(firmware_runner.run_session)
        cls.model = json.loads((here / 'model_v2.json').read_text())

    def numpy_logit(self, codes):
        mm = self.model['models'][0]
        H = len(mm['B1'])
        W1 = np.array(mm['W1']).reshape(H, -1) * mm['S1']
        W2 = np.array(mm['W2']) * mm['S2']
        v = features.session_features(codes)
        z = np.clip((v - np.array(mm['MU'])) / np.array(mm['SD']), -6, 6)
        return float(np.maximum(0, W1 @ z + np.array(mm['B1'])) @ W2 + mm['B2'])

    def test_logit_parity(self):
        for seed, kind in ((4, 'engine'), (5, 'noise')):
            c = _session(seed, kind)
            self.run_fw(self.mod, c)
            self.assertAlmostEqual(self.mod.V2_OSTATNI[0], self.numpy_logit(c), delta=1e-2)

    def test_bench_runs(self):
        self.mod.v2_bench(3)

    def test_engine_scores_above_noise(self):
        self.run_fw(self.mod, _session(6, 'engine'))
        e = self.mod.V2_OSTATNI[0]
        self.run_fw(self.mod, _session(7, 'noise'))
        n = self.mod.V2_OSTATNI[0]
        self.assertGreater(e, n)


class StateMachineTest(unittest.TestCase):
    """Wake logic of deploy/v2/main.py: suspicious -> 2 min timer sleep -> confirm -> alarm."""

    def setUp(self):
        import types
        from pathlib import Path
        import firmware_runner
        here = Path(__file__).resolve().parent
        self.m = firmware_runner.load_main(here.parent / 'deploy' / 'v2' / 'main.py', 'fw_sm')
        self.nvs = {}
        self.log = []
        m = self.m
        m.pycom = types.SimpleNamespace(nvs_get=lambda k: self.nvs.get(k),
                                        nvs_set=lambda k, v: self.nvs.__setitem__(k, v))
        m.idz_spac_na_sztywno = lambda ms: self.log.append(('timer', ms))
        m.idz_spac_na_czujniki = lambda: self.log.append(('gpio',))
        m._v2_alarm = lambda conf, vib: self.log.append(('alarm', conf, vib))
        m.polacz_wifi = lambda: None
        m.wyslij_payload = lambda r: self.log.append(('tx', r[0] & 0x0F))

    def wake(self, reason, logit):
        m = self.m
        m.machine.wake_reason = lambda: (reason, ['P19'] if reason == m.machine.PIN_WAKE else None)

        def fake(mic, vib, prog=None):
            m.V2_OSTATNI[0] = logit
            m.V2_OSTATNI[1] = logit >= m.V2_T_SUSP
            hi = m.V2_T_HIGH if prog is None else prog
            c = logit >= hi
            return c, int(c), 80
        m.analizuj_sygnaly = fake
        m.main()

    def test_direct_alarm(self):
        self.wake(self.m.machine.PIN_WAKE, self.m.V2_T_HIGH + 1)
        self.assertEqual(self.log[0][0], 'alarm')

    def test_confirmed_alarm(self):
        m = self.m
        self.wake(m.machine.PIN_WAKE, m.V2_T_SUSP + 0.1)
        self.assertEqual(self.log, [('timer', m.V2_CONFIRM_SLEEP_MS)])
        self.assertTrue(self.nvs[m.V2_NVS_KEY])
        self.wake(m.machine.RTC_WAKE, m.V2_T_SUSP + 0.1)
        self.assertEqual(self.log[1][0], 'alarm')
        self.assertEqual(self.nvs[m.V2_NVS_KEY], 0)

    def test_not_confirmed(self):
        m = self.m
        self.wake(m.machine.PIN_WAKE, m.V2_T_SUSP + 0.1)
        self.wake(m.machine.RTC_WAKE, m.V2_T_SUSP - 1.0)
        self.assertEqual(self.log[1], ('gpio',))
        self.assertNotIn('alarm', [e[0] for e in self.log])

    def test_quiet_session_goes_back_to_gpio_sleep(self):
        self.wake(self.m.machine.PIN_WAKE, -5.0)
        self.assertEqual(self.log, [('gpio',)])

    def test_heartbeat_unchanged(self):
        self.wake(self.m.machine.RTC_WAKE, 0.0)
        self.assertEqual(self.log[0], ('tx', 2))
