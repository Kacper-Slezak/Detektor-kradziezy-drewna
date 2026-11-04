"""Runs on a PC: python -m unittest discover -s tests -v
Verifies decision logic against existing Python project output from the uploaded ZIP.
"""
import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'firmware' / 'lib'))

from tg_fusion import Detector
from tg_features import Chunk, IIRAudio, build_window, centered_stats, acceleration_stats
from tg_calibration import calibrate
from tg_hardware import ADXL345


class CoreTests(unittest.TestCase):
    def test_matches_source_classifier_on_same_features(self):
        fixture = ROOT / 'tests' / 'fixtures'
        with (fixture / 'reference_desktop_model.json').open(encoding='utf-8') as handle:
            model = json.load(handle)
        with (fixture / 'reference_features.csv').open(newline='') as handle:
            features = list(csv.DictReader(handle))
        with (fixture / 'reference_predictions.csv').open(newline='') as handle:
            expected = list(csv.DictReader(handle))
        self.assertEqual(len(features), len(expected))
        engine = Detector(model['thresholds'], model['settings'], 'fusion')
        num_alerts = 0
        for sample, reference in zip(features, expected):
            values = {key: float(value) for key, value in sample.items()}
            result = engine.step(values)
            for field in ('engine_detected', 'engine_confirmed', 'audio_impact',
                          'vibration_detected', 'accelerometer_detected',
                          'motion_detected', 'recent_motion_events', 'alarm'):
                self.assertEqual(int(reference[field]), result[field],
                                 'Field %s at t=%s' % (field, values['time_s']))
            self.assertEqual(reference['state'], result['state'])
            num_alerts += result['alarm']
        self.assertGreater(num_alerts, 0)

    def test_bad_sampling_forbids_alarm_and_resets_state(self):
        s = {'hop_s': 1, 'low_ratio_min': 0.4, 'engine_confirm_windows': 1,
             'engine_memory_s': 18, 'impact_memory_s': 14,
             'impacts_for_alarm': 1, 'cooldown_s': 15}
        t = {'audio_rms': .1, 'audio_transient': 3,
             'vibration_rms': .03, 'vibration_peak': .1}
        detector = Detector(t, s, 'fusion')
        strong = {'audio_rms': .3, 'audio_low_ratio': .9, 'audio_transient': 8,
                  'vibration_rms': .2, 'vibration_peak': .5}
        alarm = detector.step(dict(strong, time_s=0))
        self.assertEqual(alarm['alarm'], 1)
        bad = detector.step(dict(strong, time_s=1, valid=False))
        self.assertEqual(bad['alarm'], 0)
        self.assertEqual(bad['state'], 'DATA_INVALID')
        quiet = {'audio_rms': .0, 'audio_low_ratio': .0, 'audio_transient': 0.0,
                 'vibration_rms': .0, 'vibration_peak': .0, 'time_s': 2}
        followup = detector.step(quiet)
        self.assertEqual(followup['alarm'], 0)
        self.assertEqual(followup['state'], 'BACKGROUND')

    def test_audio_mode_never_generates_theft_alert(self):
        s = {'hop_s': 1, 'low_ratio_min': 0.5, 'engine_confirm_windows': 1,
             'engine_memory_s': 18, 'impact_memory_s': 14,
             'impacts_for_alarm': 1, 'cooldown_s': 15}
        th = {'audio_rms': 0.1, 'audio_transient': 3}
        detector = Detector(th, s, 'audio')
        row = {'time_s': 1, 'audio_rms': .7, 'audio_low_ratio': .8,
               'audio_transient': 8}
        self.assertEqual(detector.step(row)['alarm'], 0)

    def test_missing_sensor_fails_closed(self):
        s = {'hop_s': 1, 'low_ratio_min': 0.5, 'engine_confirm_windows': 1,
             'engine_memory_s': 18, 'impact_memory_s': 14,
             'impacts_for_alarm': 1, 'cooldown_s': 15}
        f = Detector({'audio_rms': .2, 'audio_transient': 3}, s, 'fusion')
        self.assertEqual(f.step({'time_s': 0, 'audio_rms': .5,
                                 'audio_low_ratio': .9, 'audio_transient': 4})['state'],
                         'SENSOR_MISSING')

    def test_feature_calculation(self):
        self.assertEqual(centered_stats([1, 2, 3])[1], 1.0)
        self.assertAlmostEqual(acceleration_stats([(0, 0, 1), (0, 0, 2)])[0], .5)
        a = IIRAudio(1000)
        x1, x2 = a.update(0.5)
        self.assertEqual(x1, 0)
        self.assertEqual(x2, 0)
        for _ in range(1000):
            e, b = a.update(0.5)
        self.assertAlmostEqual(e, 0)
        old = Chunk(0)
        new = Chunk(1)
        for c in (old, new):
            c.total_samples = 1000
            c.audio_n = 1000
            c.hp2 = 1.0
            c.bass2 = 0.75
            c.frame_energies = [0.01] * 20
            c.vibration = [0, 1] * 50
            c.acceleration = [(0, 0, 0), (0, 0, 1)] * 25
        row = build_window(old, new, 0.08, 1000)
        self.assertTrue(row['valid'])
        self.assertAlmostEqual(row['audio_low_ratio'], .75)
        self.assertGreater(row['vibration_peak'], .4)

    def test_late_sample_fails(self):
        a, b = Chunk(0), Chunk(1)
        a.total_samples, b.total_samples = 1000, 1000
        a.late_samples, b.late_samples = 140, 140
        self.assertFalse(build_window(a, b, 0.08, 1000)['valid'])

    def test_robust_calibration(self):
        rows = [{'valid': True, 'audio_rms': x / 1000.0}
                for x in (10, 11, 9, 12, 10, 11)]
        floors = {'audio_rms': 0.008}
        th = calibrate(rows, floors)
        self.assertGreaterEqual(th['audio_rms'], floors['audio_rms'])

    def test_adxl345_signed_axes(self):
        self.assertEqual(ADXL345._i16(0x00, 0x80), -32768)
        self.assertEqual(ADXL345._i16(0xFF, 0xFF), -1)
        self.assertEqual(ADXL345._i16(0xFF, 0x7F), 32767)


if __name__ == '__main__':
    unittest.main()
