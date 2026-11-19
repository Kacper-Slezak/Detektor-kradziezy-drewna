"""V3 regression: explicit positives and broadband negatives (not field accuracy)."""
import math
import random
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

from algorithm.app.simulate import run_simulation

SAMPLES = Path(__file__).resolve().parents[1] / 'algorithm' / 'sample_audio'


class WidebandV3Tests(unittest.TestCase):
    def test_caterpillar_wideband_finds_more_than_low_rate(self):
        path = SAMPLES / 'catterpillar.wav'
        low = run_simulation('background', 'audio', wav_path=path, audio_rate=1000)
        wide = run_simulation('background', 'audio', wav_path=path, audio_rate=4000)
        low_hits = sum(int(r['engine_confirmed']) for r in low)
        wide_hits = sum(int(r['engine_confirmed']) for r in wide)
        self.assertGreaterEqual(wide_hits, 10)
        self.assertGreater(wide_hits, low_hits)
        self.assertTrue(any(r['engine_wide_confirmed'] for r in wide))
        self.assertTrue(all(r['audio_wide_score'] == 0 for r in low))

    def test_mixed_weather_does_not_become_fake_confident_alarm(self):
        rows = run_simulation('background', 'audio',
                              wav_path=SAMPLES / 'rain-wind-truck.wav')
        self.assertTrue(rows)
        self.assertEqual(sum(r['alarm'] for r in rows), 0)
        self.assertTrue(any(r['engine_detected'] for r in rows))

    def test_stochastic_broadband_noise_not_engine(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'noise.wav'
            rng = random.Random(458)
            fs = 8000
            seconds = 30
            data = array('h')
            smooth = 0.0
            for i in range(seconds * fs):
                # White noise plus colored gust energy and occasional clicks.
                noise = rng.gauss(0, 0.4)
                smooth = 0.985 * smooth + 0.015 * noise
                gust = 0.25 + 0.75 * math.sin(i * 2 * math.pi / fs * .19) ** 2
                value = gust * noise * .70 + smooth * .23
                if i % 12409 == 0:
                    value += .9
                data.append(round(max(-1.0, min(1.0, value)) * 32767))
            with wave.open(str(path), 'wb') as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(fs)
                f.writeframes(data.tobytes())
            rows = run_simulation('background', 'audio', wav_path=path)
            self.assertFalse(any(r['engine_confirmed'] for r in rows))

    def test_fusion_alarm_requires_actual_motion_events(self):
        vibration = Path(__file__).resolve().parents[1] / 'algorithm' / 'data' / 'truck_loading_demo.csv'
        for name, expected in [('catterpillar.wav', 1),
                               ('rain-wind-truck.wav', 0),
                               ('forest-ambience.wav', 0)]:
            with self.subTest(name=name):
                rows = run_simulation('background', 'fusion', seconds=44,
                                      wav_path=SAMPLES / name, vibration_path=vibration)
                self.assertEqual(sum(r['alarm'] for r in rows), expected)

    def test_firmware_modules_same_as_source(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('tg_engine.py', 'tg_wide.py', 'tg_features.py', 'tg_fusion.py'):
            self.assertEqual((root / 'algorithm' / 'core' / name).read_bytes(),
                             (root / 'firmware' / 'lib' / name).read_bytes())


if __name__ == '__main__':
    unittest.main()
