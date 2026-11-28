"""Decision contracts and sensor-safety regression checks."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'firmware' / 'lib'))
sys.path.insert(0, str(ROOT / 'firmware'))

from algorithm.core.tg_fusion import Detector
from algorithm.core.tg_engine import EngineSpectrum
from algorithm.core.tg_features import Chunk, IIRAudio, build_window, centered_stats, acceleration_stats
from algorithm.core.tg_calibration import calibrate
from tg_device import floors, settings
from tg_hardware import ADXL345


def signals(t, score=0.0, pitch=None, motion=False):
    return {'time_s': float(t), 'valid': True, 'audio_rms': .08,
            'audio_low_ratio': .8, 'audio_transient': 1.0,
            'audio_engine_score': score, 'audio_engine_pitch_hz': pitch,
            'audio_engine_method': 'ridge' if score > 0 else 'none',
            'vibration_rms': .20 if motion else 0.0,
            'vibration_peak': .50 if motion else 0.0,
            'accel_dynamic_rms': None, 'accel_peak': None}


class CoreTests(unittest.TestCase):
    def test_high_volume_and_bass_alone_do_not_confirm_engine(self):
        d = Detector(floors(), settings(), 'audio')
        rows = [d.step(signals(t, 0.0, None)) for t in range(10)]
        self.assertFalse(any(r['engine_confirmed'] for r in rows))
        self.assertFalse(any(r['alarm'] for r in rows))

    def test_three_coherent_engine_votes_required(self):
        d = Detector(floors(), settings(), 'audio')
        rows = [d.step(signals(t, .99, 145.0)) for t in range(4)]
        self.assertEqual([r['engine_confirmed'] for r in rows], [0, 0, 1, 1])
        self.assertEqual(rows[-1]['engine_reason'], 'ridge')
        self.assertEqual(rows[-1]['state'], 'ENGINE_DETECTED')

    def test_wide_multi_ridge_votes_can_confirm_without_fixed_f0(self):
        d = Detector(floors(), settings(), 'audio')
        peaks = ([305.0, 525.0, 750.0],
                 [310.0, 532.0, 762.0],
                 [317.0, 540.0, 770.0])
        rows = []
        for t, tones in enumerate(peaks):
            r = signals(t, 0.0, None)
            r.update(audio_wide_score=.93, audio_wide_ratio=3.0,
                     audio_wide_peaks_hz=tones)
            rows.append(d.step(r))
        self.assertEqual([r['engine_wide_confirmed'] for r in rows], [0, 0, 1])
        self.assertEqual(rows[-1]['engine_reason'], 'wide_multi')
        self.assertEqual(rows[-1]['engine_wide_vote_count'], 3)

    def test_wide_unrelated_peaks_not_confirmed(self):
        d = Detector(floors(), settings(), 'audio')
        rows = []
        for t, tones in enumerate(([260, 360, 460], [570, 670, 770],
                                   [340, 440, 540])):
            r = signals(t, 0.0, None)
            r.update(audio_wide_score=.93, audio_wide_ratio=3.0,
                     audio_wide_peaks_hz=tones)
            rows.append(d.step(r))
        self.assertFalse(any(r['engine_wide_confirmed'] for r in rows))

    def test_unrelated_three_pitches_do_not_confirm(self):
        d = Detector(floors(), settings(), 'audio')
        rows = [d.step(signals(t, .99, p)) for t, p in enumerate((36, 85, 140))]
        self.assertFalse(any(r['engine_confirmed'] for r in rows))

    def test_one_shot_alarm_after_three_separate_motion_events(self):
        d = Detector(floors(), settings(), 'fusion')
        rows = [d.step(signals(t, .99, 145.0, t in (5, 9, 13))) for t in range(30)]
        alarms = [r for r in rows if r['alarm']]
        self.assertEqual(len(alarms), 1)
        self.assertEqual(alarms[0]['state'], 'ALARM')
        self.assertEqual(alarms[0]['eligible_motion_events'], 3)
        self.assertTrue(any(r['state'] == 'ALARM_LATCHED' for r in rows))

    def test_motion_before_engine_does_not_count_as_loading(self):
        d = Detector(floors(), settings(), 'fusion')
        rows = []
        for t in range(22):
            # Three impacts well before a subsequently detected engine.
            scores = .99 if t >= 12 else 0.0
            rows.append(d.step(signals(t, scores, 145.0 if scores else None,
                                       t in (1, 4, 7))))
        self.assertFalse(any(r['alarm'] for r in rows))

    def test_audio_only_or_vibration_only_never_alert(self):
        for mode in ('audio', 'vibration'):
            d = Detector(floors(), settings(), mode)
            rows = [d.step(signals(t, .99, 145, t in (5, 9, 13))) for t in range(18)]
            self.assertFalse(any(r['alarm'] for r in rows))

    def test_missing_spectral_features_fail_closed(self):
        d = Detector(floors(), settings(), 'fusion')
        old_style = {'time_s': 0, 'valid': True, 'audio_rms': .8,
                     'audio_low_ratio': .8, 'audio_transient': 8,
                     'vibration_rms': .8, 'vibration_peak': .9}
        row = d.step(old_style)
        self.assertEqual(row['state'], 'SENSOR_MISSING')
        self.assertEqual(row['alarm'], 0)

    def test_invalid_window_clears_all_votes_and_alarm_latch(self):
        d = Detector(floors(), settings(), 'fusion')
        for t in range(5):
            d.step(signals(t, .99, 145))
        bad = d.step(dict(signals(5, .99, 145, True), valid=False))
        self.assertEqual(bad['state'], 'DATA_INVALID')
        self.assertEqual(bad['alarm'], 0)
        clean = d.step(signals(6, .99, 145, True))
        self.assertEqual(clean['engine_confirmed'], 0)
        self.assertEqual(clean['alarm'], 0)

    def test_alert_latch_survives_invalid_samples(self):
        d = Detector(floors(), settings(), 'fusion')
        events = []
        for t in range(20):
            row = d.step(signals(t, .99, 145, t in (5,9,13)))
            if row['alarm']:
                events.append(t)
        self.assertEqual(events,[13])
        invalid = d.step(dict(signals(20), valid=False))
        self.assertEqual(invalid['alarm'], 0)
        for t in range(21,40):
            row = d.step(signals(t, .99, 145, t in (24,28,32)))
            if row['alarm']:
                events.append(t)
        self.assertEqual(events,[13])

    def test_time_gap_resets_engine_votes(self):
        d = Detector(floors(), settings(), 'audio')
        d.step(signals(0,.99,145));d.step(signals(1,.99,145))
        self.assertFalse(d.step(signals(6,.99,145))['engine_confirmed'])

    def test_fft_identifies_two_harmonics_not_sine(self):
        import math
        a = EngineSpectrum()
        one = [math.sin(2*math.pi*143*i/500) for i in range(500)]
        two = [(math.sin(2*math.pi*70*i/500) +
                .5*math.sin(2*math.pi*140*i/500) +
                .3*math.sin(2*math.pi*210*i/500)) for i in range(500)]
        self.assertEqual(a.analyze(one)['audio_harmonic_count'], 0)
        self.assertGreater(a.analyze(two)['audio_harmonic_count'], 1)
        self.assertLess(a.analyze(one)['audio_engine_score'], .72)
        self.assertGreater(a.analyze(two)['audio_engine_score'], .72)

    def test_feature_calculation(self):
        self.assertEqual(centered_stats([1, 2, 3])[1], 1.0)
        self.assertAlmostEqual(acceleration_stats([(0,0,1),(0,0,2)])[0],.5)
        a = IIRAudio(1000)
        self.assertEqual(a.update(.5), (0.0, 0.0))
        for _ in range(1000):
            e,b = a.update(.5)
        self.assertAlmostEqual(e,0.0)
        old,new = Chunk(0),Chunk(1)
        for c in (old,new):
            c.total_samples = 1000
            c.audio_n=1000;c.hp2=1.0;c.bass2=.75
            c.frame_energies=[.01]*20
            c.vibration=[0,1]*50
            c.acceleration=[(0,0,0),(0,0,1)]*25
        row=build_window(old,new,.08,1000)
        self.assertTrue(row['valid'])
        self.assertAlmostEqual(row['audio_low_ratio'],.75)
        self.assertEqual(row['audio_engine_score'],None)
        self.assertGreater(row['vibration_peak'],.4)

    def test_late_samples_or_processing_gap_fail_closed(self):
        a,b=Chunk(0),Chunk(1)
        a.total_samples=b.total_samples=1000
        a.late_samples=0;b.late_samples=1000
        b.start_gap_us=25000
        row=build_window(a,b,.08,1000)
        self.assertFalse(row['valid'])
        self.assertEqual(row['processing_gap_us'],25000)

    def test_calibration_and_accel(self):
        rows=[{'valid':True,'audio_rms':v/1000} for v in (10,11,9,12,10,11)]
        self.assertGreaterEqual(calibrate(rows,{'audio_rms':.008})['audio_rms'],.008)
        self.assertEqual(ADXL345._i16(0,128),-32768)
        self.assertEqual(ADXL345._i16(255,255),-1)


if __name__ == '__main__':
    unittest.main()
