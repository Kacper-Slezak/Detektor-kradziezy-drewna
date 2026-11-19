"""v4.4 tests without dataset or TensorFlow; CPython and MicroPython parity."""
import math
import tempfile
import unittest
import wave
from pathlib import Path
import numpy as np
from algorithm.core.tg_temporal import TemporalChunk,TemporalFilter,MelFFT,normalize_window,make_row
from algorithm.app.v4_4_prepare import features_per_second
from algorithm.app.v4_4_train import (patches,init,forward,quantize,quant_forward,
                                       export,train)
from algorithm.core.tg_cnn import score_bands
from algorithm.core.tg_presence import Presence
import importlib.util

class TestV44(unittest.TestCase):
    def synth(self,seconds=3):
        t=np.arange(seconds*4000)/4000.0
        sound=(0.19*np.sin(2*np.pi*75*t)+0.12*np.sin(2*np.pi*350*t)+
               0.03*np.sin(2*np.pi*(140*t+15*t*t)))
        return np.rint(sound*32760).astype('<i2')

    def test_temporal_wave_parity_with_desktop(self):
        pcm=self.synth()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'sample.wav'
            with wave.open(str(path),'wb') as wf:
                wf.setnchannels(1);wf.setsampwidth(2);wf.setframerate(4000)
                wf.writeframes(pcm.tobytes())
            pc=features_per_second(path)
            self.assertEqual(pc.shape,(3,4,16))
        filt=TemporalFilter();fft=MelFFT()
        chunks=[]
        for sec in range(3):
            ch=TemporalChunk(float(sec));ch.total_samples=4000
            for v in pcm[sec*4000:(sec+1)*4000]:
                ch.add_sample(filt.update(float(v)/32768.0))
            chunks.append(ch)
        for idx in range(2):
            stream=make_row(chunks[idx],chunks[idx+1],fft)
            offline=normalize_window(pc[idx:idx+2].reshape(-1))
            self.assertLess(np.max(np.abs(np.array(stream['temporal_bands'])-offline)),0.08)
            self.assertEqual(len(stream['temporal_bands']),128)

    def test_bad_samples_fail_closed(self):
        filt=TemporalFilter();fft=MelFFT(); chunks=[]
        for i in range(2):
            ch=TemporalChunk(i);ch.total_samples=4000
            for _ in range(4000):ch.add_sample(filt.update(.5))
            chunks.append(ch)
        chunks[1].late_samples=4000
        row=make_row(chunks[0],chunks[1],fft)
        self.assertFalse(row['valid'])
        self.assertIsNone(row['temporal_bands'])

    def test_quant_model_export(self):
        rng=np.random.default_rng(42)
        X=rng.normal(size=(9,8,16)).astype(np.float32)
        mean=X.mean(axis=(0,1));inv=1/np.maximum(X.std(axis=(0,1)),.02)
        norm=np.clip((X-mean)*inv,-6,6)
        pp=patches(norm)
        params=init(42)
        q=quantize(params)
        qscore=quant_forward(pp,q)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'tg_model_v44.py'
            size=export(path,mean,inv,q,.55)
            self.assertLess(size,32768)
            spec=importlib.util.spec_from_file_location('test_export_model_v44',path)
            m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
            for i in range(9):
                got=score_bands(X[i].reshape(-1),m)
                self.assertAlmostEqual(got,float(qscore[i]),delta=.005)
            self.assertEqual(sum(w.size for w in q[0]),1230)

    def test_train_improves_simple_synthetic_signal(self):
        rng=np.random.default_rng(31)
        n=120
        X=rng.normal(0,.3,size=(n,8,16)).astype(np.float32)
        y=np.array([0]*60+[1]*60)
        X[60:,:,2:5]+=2.0
        pc=patches(X)
        val=pc[::6]; vv=y[::6]
        trainidx=np.setdiff1d(np.arange(n),np.arange(0,n,6))
        before=forward(val,init(17))
        params,epoch=train(pc[trainidx],y[trainidx],y[trainidx].astype(np.float32),
                           np.ones(len(trainidx),np.float32),val,vv,8,24,.01,17)
        after=forward(val,params)
        self.assertGreater(abs(after[vv==1].mean()-after[vv==0].mean()),
                           abs(before[vv==1].mean()-before[vv==0].mean())+.1)
        self.assertGreaterEqual(epoch,1)

if __name__=='__main__':unittest.main()
