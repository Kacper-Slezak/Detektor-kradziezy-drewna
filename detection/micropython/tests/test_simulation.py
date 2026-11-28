"""Deterministic integration tests using the same firmware DSP modules."""
import array
from pathlib import Path
import tempfile
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
from algorithm.app.simulate import (run_simulation, write_csv,
                                    read_pcm_wav, read_vibration_csv)


class SimulationTests(unittest.TestCase):
    def test_synthetic_no_engine_scenarios(self):
        for name in ('background','motion_only','wind_like','whistle_only','audio_impacts'):
            with self.subTest(name=name):
                mode='audio' if name in ('wind_like','whistle_only','audio_impacts') else 'fusion'
                rows=run_simulation(name,mode,seconds=30)
                self.assertTrue(rows)
                self.assertFalse(any(r['engine_confirmed'] for r in rows))
                self.assertFalse(any(r['alarm'] for r in rows))

    def test_engine_only(self):
        rows=run_simulation('engine_only')
        self.assertTrue(any(r['engine_confirmed'] for r in rows))
        self.assertFalse(any(r['alarm'] for r in rows))

    def test_loading_alarm_three_impacts(self):
        rows=run_simulation('loading')
        alarms=[r for r in rows if r['alarm']]
        self.assertEqual(len(alarms),1)
        self.assertGreaterEqual(alarms[0]['eligible_motion_events'],3)
        self.assertEqual(alarms[0]['state'],'ALARM')

    def test_only_two_impacts_not_enough(self):
        rows=run_simulation('loading',seconds=12)
        self.assertTrue(any(r['engine_confirmed'] for r in rows))
        self.assertTrue(any(r['recent_motion_events']==2 for r in rows))
        self.assertFalse(any(r['alarm'] for r in rows))

    def test_audio_mode_no_alert(self):
        rows=run_simulation('engine_only','audio')
        self.assertTrue(any(r['engine_confirmed'] for r in rows))
        self.assertFalse(any(r['alarm'] for r in rows))

    def test_vibration_only_no_alert(self):
        rows=run_simulation('motion_only','vibration')
        self.assertTrue(any(r['motion_detected'] for r in rows))
        self.assertFalse(any(r['alarm'] for r in rows))

    def test_own_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'silence.wav'
            with wave.open(str(path),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000)
                f.writeframes(array.array('h',[0]*16000).tobytes())
            self.assertEqual(len(read_pcm_wav(path,1000)),2000)
            rows=run_simulation('background','audio',wav_path=path)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['state'],'BACKGROUND')
            out=Path(tmp)/'results.csv';write_csv(rows,out)
            self.assertIn('audio_engine_score',out.read_text())

    def test_vibration_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'vib.csv';path.write_text('time_s,value\n0,0.5\n3,0.5\n')
            self.assertEqual(len(read_vibration_csv(path)),2)
            rows=run_simulation('background','vibration',seconds=3,vibration_path=path)
            self.assertEqual(len(rows),2)
            self.assertFalse(any(r['alarm'] for r in rows))

    def test_real_forest_and_truck(self):
        samples=ROOT/'algorithm/sample_audio'
        forest=run_simulation('background','audio',wav_path=samples/'forest-ambience.wav')
        truck=run_simulation('background','audio',wav_path=samples/'forest-with-truck.wav')
        self.assertTrue(len(forest)>250)
        self.assertFalse(any(r['engine_confirmed'] for r in forest))
        self.assertTrue(any(r['engine_confirmed'] for r in truck))
        self.assertTrue(any(19 <= r['time_s'] <= 36 and r['engine_confirmed'] for r in truck))
        self.assertFalse(any(r['alarm'] for r in forest+truck))

    def test_real_catterpillar_low_ridge_detection(self):
        samples = ROOT / 'algorithm/sample_audio'
        rows = run_simulation('background', 'audio',
                              wav_path=samples / 'catterpillar.wav')
        confirmed = [r for r in rows if r['engine_confirmed']]
        self.assertGreaterEqual(len(confirmed), 3)
        self.assertTrue(any(24 <= r['time_s'] <= 28 for r in confirmed))
        self.assertTrue(any(r['audio_engine_method'] == 'low_ridge'
                            for r in confirmed))
        self.assertFalse(any(r['alarm'] for r in rows))

    def test_real_audio_plus_synthetic_impact_fusion(self):
        samples=ROOT/'algorithm/sample_audio'
        impulses=ROOT/'algorithm/data/truck_loading_demo.csv'
        forest=run_simulation('background','fusion',
                              wav_path=samples/'forest-ambience.wav',
                              vibration_path=None,seconds=45)
        truck=run_simulation('background','fusion',
                             wav_path=samples/'forest-with-truck.wav',
                             vibration_path=impulses)
        self.assertFalse(any(r['alarm'] for r in forest))
        self.assertEqual(sum(r['alarm'] for r in truck),1)


if __name__=='__main__':
    unittest.main()
