"""Portable v4 model / time gate tests. Does not pretend to test real LoPy ADC."""
import unittest
from pathlib import Path
from algorithm.core.tg_presence import Presence
from algorithm.core.tg_ml import predict_probability, FEATURES
from algorithm.core import tg_model_1k, tg_model_4k

class FakeModel:
    TREES = (((-1, 0.0, -1, -1, 0.99),),)


def row(t, valid=True):
    return {'time_s':float(t), 'valid':valid, 'audio_rms':0.10,
            'audio_low_ratio':0.5, 'audio_tonality':0.1,
            'audio_engine_score':0.5, 'audio_wide_score':0.0}


class V4Tests(unittest.TestCase):
    def test_model_prediction_range(self):
        r=row(0)
        for model in (tg_model_1k,tg_model_4k):
            self.assertIn(model.RATE,(1000,4000))
            self.assertGreater(len(model.TREES),0)
            self.assertGreaterEqual(predict_probability(r,model),0.0)
            self.assertLessEqual(predict_probability(r,model),1.0)

    def test_requires_full_history(self):
        p=Presence(FakeModel,span=15,fraction=.6,off_hours=True)
        for i in range(14):
            result=p.step(row(i))
            self.assertEqual(result['alarm'],0)
        result=p.step(row(14))
        self.assertEqual(result['state'],'PERSISTENT_ENGINE')
        self.assertEqual(result['engine_vote_count'],15)
        self.assertEqual(result['alarm'],1)

    def test_cannot_alert_in_working_hours(self):
        p=Presence(FakeModel,off_hours=False)
        results=[p.step(row(i)) for i in range(28)]
        self.assertTrue(any(r['engine_confirmed'] for r in results))
        self.assertFalse(any(r['alarm'] for r in results))

    def test_unknown_clock_disables_alert(self):
        p=Presence(FakeModel,off_hours=None)
        results=[p.step(row(i),off_hours=None) for i in range(30)]
        self.assertTrue(any(r['engine_confirmed'] for r in results))
        self.assertFalse(any(r['alarm'] for r in results))

    def test_short_pass_by_never_alerts(self):
        p=Presence(FakeModel,off_hours=True)
        self.assertFalse(any(p.step(row(i))['alarm'] for i in range(8)))

    def test_invalid_data_fails_closed(self):
        p=Presence(FakeModel,off_hours=True)
        for i in range(14):p.step(row(i))
        fail=p.step(row(14,False))
        self.assertEqual(fail['state'],'DATA_INVALID')
        self.assertEqual(fail['alarm'],0)
        self.assertFalse(p.step(row(15))['engine_confirmed'])

    def test_missing_audio_fails_closed(self):
        p=Presence(FakeModel,off_hours=True)
        q=row(0);q['audio_rms']=None
        self.assertEqual(p.step(q)['state'],'DATA_INVALID')

    def test_no_double_alarm(self):
        p=Presence(FakeModel,off_hours=True)
        decisions=[p.step(row(i)) for i in range(50)]
        self.assertEqual(sum(x['alarm'] for x in decisions),1)
        self.assertEqual(p.event_id,1)

    def test_gap_disables_immediate_alert(self):
        p=Presence(FakeModel,off_hours=True)
        for i in range(14):p.step(row(i))
        decision=p.step(row(18))
        self.assertEqual(decision['state'],'DATA_INVALID')
        self.assertEqual(decision['alarm'],0)
        self.assertEqual(p.step(row(19))['engine_vote_count'],1)

    def test_firmware_ml_files_in_sync(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('tg_ml.py','tg_presence.py','tg_model_1k.py','tg_model_4k.py'):
            self.assertEqual((root/'algorithm/core'/name).read_bytes(),
                             (root/'firmware/lib'/name).read_bytes())

if __name__=='__main__':unittest.main()
