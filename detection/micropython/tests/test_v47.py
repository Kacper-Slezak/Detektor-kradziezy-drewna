"""Tests for source-safe and window-aware augmentation in v4.7."""
import random
import unittest
import numpy as np
from algorithm.app.v4_7_prepare import (background_bed,passing_mixture,
                                           label_window,RATE16)
from algorithm.app.v4_7_train import scene_weights

class TestPassingAugmentation(unittest.TestCase):
    def setUp(self):
        t=np.arange(RATE16*5)/RATE16
        self.engine=(.03*np.sin(2*np.pi*240*t)).astype('f4')
        self.forest=(.025*np.sin(2*np.pi*70*t)+.005*np.sin(2*np.pi*630*t)).astype('f4')

    def test_background_has_no_nan(self):
        x=background_bed([self.forest],RATE16*11,random.Random(7))
        self.assertEqual(len(x),RATE16*11)
        self.assertTrue(np.isfinite(x).all())

    def test_engine_scene_has_clean_prefix_and_positive_middle(self):
        bg=background_bed([self.forest],RATE16*11,random.Random(7))
        mixed,added=passing_mixture(self.engine,bg,6,random.Random(8))
        self.assertTrue(np.isfinite(mixed).all())
        self.assertLess(np.max(np.abs(mixed)),.96)
        self.assertEqual(label_window(added,mixed-added,0),0)
        self.assertIn(1,[label_window(added,mixed-added,sec*RATE16) for sec in range(8)])

    def test_near_silent_engine_is_not_automatically_negative(self):
        b=np.ones(RATE16*2,dtype=np.float32)*0.4
        a=(.0001*np.sin(np.arange(RATE16*2)*.1)).astype(np.float32)
        self.assertIsNone(label_window(a,b,0))

    def test_zero_injection_is_negative(self):
        b=np.sin(np.arange(RATE16*2)*.1).astype(np.float32)*.05
        self.assertEqual(label_window(np.zeros_like(b),b,0),0)

    def test_pair_class_source_weights(self):
        labels=np.array([0,0,0,1,1,0,1])
        sources=np.array(['a','a','a','a','a','b','b'])
        weights=scene_weights(labels,sources)
        self.assertAlmostEqual(float(weights[0]*3),float(weights[3]*2))
        self.assertTrue(np.isfinite(weights).all())

if __name__=='__main__':unittest.main()
