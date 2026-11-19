"""v4.5 scalable model and firmware compatibility smoke tests."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
import numpy as np
from algorithm.app.v4_5_capacity_train import (patches,init,forward,train,
                                                   quantize,quant_forward,export)
from algorithm.core.tg_cnn_v45 import score_bands
from algorithm.core.tg_presence import Presence

class TestV45Capacity(unittest.TestCase):
    def test_small_and_large_export_parity(self):
        rng=np.random.default_rng(20)
        X=rng.normal(0,1,size=(8,8,16)).astype(np.float32)
        mean=X.mean(axis=(0,1))
        inv=1/np.maximum(X.std(axis=(0,1)),.02)
        P=patches(np.clip((X-mean)*inv,-6,6))
        for channels,hidden in ((6,24),(16,64),(24,128)):
            with self.subTest(channels=channels,hidden=hidden):
                params=init(14,channels,hidden)
                q=quantize(params)
                expected=quant_forward(P,q)
                with tempfile.TemporaryDirectory() as td:
                    model_path=Path(td)/'tg_model_v45.py'
                    size=export(model_path,mean,inv,q,.58,channels,hidden)
                    spec=importlib.util.spec_from_file_location('model_v45',model_path)
                    model=importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(model)
                    self.assertEqual(model.CONV_CHANNELS,channels)
                    self.assertEqual(model.HIDDEN,hidden)
                    self.assertLess(size,65536)
                    for i in range(len(X)):
                        score=score_bands(X[i].reshape(-1),model)
                        self.assertAlmostEqual(score,float(expected[i]),delta=.005)

    def test_presence_works_with_v45_model(self):
        rng=np.random.default_rng(23)
        X=rng.normal(size=(8,16)).astype(np.float32)
        mean=np.zeros(16,dtype=np.float32)
        inv=np.ones(16,dtype=np.float32)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'model.py'
            export(path,mean,inv,quantize(init(9,12,48)),.5,12,48)
            spec=importlib.util.spec_from_file_location('test_v45_model',path)
            model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
            det=Presence(model,threshold=.5,off_hours=False)
            row={'time_s':0.0,'valid':True,'audio_rms':1.0,
                 'temporal_bands':X.reshape(-1).tolist()}
            d=det.step(row)
            self.assertGreaterEqual(d['ml_engine_score'],0)
            self.assertLessEqual(d['ml_engine_score'],1)
            self.assertEqual(d['alarm'],0)

    def test_optimizer_one_epoch(self):
        rng=np.random.default_rng(123)
        X=rng.normal(0,1,(70,8,16)).astype(np.float32)
        y=(X[:,:2,:].mean((1,2))>0).astype(np.int8)
        p=patches(X)
        params,epoch=train(p[:50],y[:50],y[:50],np.ones(50,np.float32),
                           p[50:],y[50:],2,25,.003,30,16,64)
        self.assertGreaterEqual(epoch,1)
        self.assertTrue(np.isfinite(forward(p[50:],params)).all())

if __name__=='__main__':unittest.main()
