"""Keep firmware copies in sync with desktop source."""
import unittest
from pathlib import Path
from algorithm.app.simulate import run_simulation

ROOT = Path(__file__).resolve().parents[1]


class LayoutTests(unittest.TestCase):
    def test_firmware_algorithm_matches_desktop_core(self):
        for name in ('tg_features.py','tg_engine.py','tg_fusion.py','tg_calibration.py'):
            with self.subTest(name=name):
                self.assertEqual((ROOT/'algorithm/core'/name).read_bytes(),
                                 (ROOT/'firmware/lib'/name).read_bytes())

    def test_audio_demo_confirmed_and_no_alarm(self):
        rows=run_simulation('background','audio',
                            wav_path=ROOT/'algorithm/sample_audio/engine_demo.wav')
        self.assertTrue(any(r['engine_confirmed'] for r in rows))
        self.assertFalse(any(r['alarm'] for r in rows))

    def test_fusion_demo(self):
        rows=run_simulation('background','fusion',
                            wav_path=ROOT/'algorithm/sample_audio/engine_demo.wav',
                            vibration_path=ROOT/'algorithm/data/vibration_demo.csv')
        self.assertEqual(sum(r['alarm'] for r in rows),1)


if __name__=='__main__':
    unittest.main()
