"""Unit tests for the portable v4.2 feature path and runtime contract."""
import unittest
from pathlib import Path
from algorithm.app.simulate import iter_simulation
from algorithm.core.tg_nn import feature_vector, predict_score
from algorithm.core.tg_ml import predict_probability
from algorithm.core.tg_presence import Presence

class DummyModel:
    MODEL_TYPE = 'tiny_mlp_v42'
    RATE = 4000
    DIMS = (63,1)
    MEAN = (0.0,) * 63
    INV_STD = (1.0,) * 63
    SCALES = (0.01,)
    BIASES = ((0.0,),)
    WEIGHT_B64 = ('AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA',)


class TinyMLTests(unittest.TestCase):
    def test_same_dsp_for_pc_and_firmware(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('tg_engine.py','tg_wide.py','tg_features.py','tg_nn.py','tg_ml.py'):
            self.assertEqual((root/'algorithm/core'/name).read_bytes(),
                             (root/'firmware/lib'/name).read_bytes())

    def test_4khz_stream_has_exact_features(self):
        rows=list(iter_simulation('engine_only','audio',seconds=4,audio_rate=4000))
        self.assertEqual(len(rows),3)
        for row in rows:
            self.assertTrue(row['valid'])
            self.assertEqual(len(feature_vector(row)),63)
            self.assertEqual(len(row['tiny_spectral_bands']),48)
            self.assertTrue(any(x>0 for x in row['tiny_spectral_bands']))

    def test_firmware_fails_closed_by_default(self):
        from firmware import config
        self.assertEqual(config.MODEL_FLAVOR,'v4_2')
        self.assertFalse(config.ENABLE_PHYSICAL_ALARM)
        self.assertFalse(config.CLOCK_IS_LOCAL_AND_SYNCED)

    def test_student_rejects_legacy_missing_bands(self):
        with self.assertRaises(ValueError):
            feature_vector({'audio_rms':0.1})

if __name__=='__main__':unittest.main()
