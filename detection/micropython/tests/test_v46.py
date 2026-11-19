"""No external FSC22 data needed: portable v4.6 regression tests."""
import math,tempfile,wave,importlib.util,unittest
from pathlib import Path
import numpy as np
from algorithm.core.tg_temporal_v46 import RawChunk,MelFFT,make_row,normalize_window,sparse_bands
from algorithm.app.v4_6_prepare import features_per_second
from algorithm.app.v4_6_train import init,quantize,quant_forward,export,patches
from algorithm.core.tg_cnn_v46 import score_features


def synthetic_pcm():
    rate=4000;t=np.arange(8000,dtype=float)/rate
    rng=np.random.default_rng(42)
    return np.rint(10000*np.sin(2*math.pi*225*t)+8000*np.sin(2*math.pi*1300*t)+
                   950*rng.standard_normal(len(t))).clip(-32768,32767).astype('<i2')


def write_pcm(path,pcm):
    with wave.open(str(path),'wb') as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(4000)
        f.writeframes(pcm.tobytes())


class TestV46(unittest.TestCase):
    def test_twenty_four_filters_up_to_1900(self):
        self.assertEqual(len(sparse_bands()),24)
        self.assertGreater(max(j for idx,_ in sparse_bands() for j in idx),420)

    def test_micro_matches_pc_fft_and_energy(self):
        pcm=synthetic_pcm()
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'sample.wav';write_pcm(path,pcm)
            mel,rms=features_per_second(path)
        patch,energy=normalize_window(mel.reshape(-1),rms.reshape(-1))
        a,b=RawChunk(0),RawChunk(1)
        for i,v in enumerate(pcm):
            c=a if i<4000 else b
            c.add_sample((float(v)/32767.0+1.0)/2.0)
            c.total_samples+=1
        r=make_row(a,b,MelFFT())
        self.assertTrue(r['valid'])
        self.assertLess(max(abs(x-y) for x,y in zip(patch,r['wide_patch'])),0.035)
        self.assertLess(max(abs(x-y) for x,y in zip(energy,r['energy_envelope'])),0.005)
        self.assertGreater(r['audio_rms'],0)

    def test_loudness_is_preserved_separately(self):
        pcm=synthetic_pcm()
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            write_pcm(p/'a.wav',pcm)
            write_pcm(p/'b.wav',(pcm//2).astype('<i2'))
            a,ar=features_per_second(p/'a.wav')
            b,br=features_per_second(p/'b.wav')
        x,e=normalize_window(a.reshape(-1),ar.reshape(-1))
        y,f=normalize_window(b.reshape(-1),br.reshape(-1))
        self.assertLess(float(np.mean(np.abs(np.asarray(x)-np.asarray(y)))),0.02)
        self.assertGreater(e[-1]-f[-1],0.6)

    def test_pc_quantized_export_score_parity(self):
        rng=np.random.default_rng(100)
        X=rng.normal(0,2,(4,8,24)).astype(np.float32)
        E=rng.normal(0,.25,(4,9)).astype(np.float32)
        conv,hidden=8,32
        q=quantize(init(1,conv,hidden))
        m=rng.normal(0,.3,24)
        inv=np.ones(24)
        em=rng.normal(0,.1,9)
        einv=np.ones(9)
        P=patches(np.clip((X-m[None,None,:])*inv,-6,6).astype(np.float32))
        s=quant_forward(P,np.clip((E-em[None,:])*einv,-6,6).astype(np.float32),q)
        with tempfile.TemporaryDirectory() as td:
            file=Path(td)/'model.py'
            export(file,m,inv,em,einv,q,.50,conv,hidden)
            spec=importlib.util.spec_from_file_location('v46_example_test',file)
            model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
            for i in range(len(X)):
                value=score_features(X[i].reshape(-1),E[i],model)
                self.assertLess(abs(value-float(s[i])),0.002)

    def test_desktop_and_lopy_event_votes_match(self):
        import sys
        from algorithm.core.tg_presence_v46 import Presence as DesktopPresence
        firmware_lib=str(Path(__file__).resolve().parents[1]/'firmware/lib')
        if firmware_lib not in sys.path:
            sys.path.insert(0,firmware_lib)
        from tg_presence_v46 import Presence as DevicePresence
        rng=np.random.default_rng(999)
        q=quantize(init(10,8,32))
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'weights.py'
            export(path,np.zeros(24),np.ones(24),np.zeros(9),np.ones(9),
                   q,.5,8,32)
            spec=importlib.util.spec_from_file_location('v46_vote_model',path)
            model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
            pc=DesktopPresence(model,threshold=.5,span=15,fraction=.6,off_hours=True)
            lopy=DevicePresence(model,threshold=.5,span=15,fraction=.6,off_hours=True)
            for i in range(30):
                row={'time_s':float(i),'window_end_s':float(i+2),
                     'valid':True,'audio_rms':.1,
                     'wide_patch':rng.normal(size=8*24).tolist(),
                     'energy_envelope':rng.normal(size=9).tolist()}
                a=pc.step(row);b=lopy.step(row)
                for key in ('engine_detected','engine_vote_count','engine_confirmed','alarm'):
                    self.assertEqual(a[key],b[key])

    def test_invalid_timing_fails_closed(self):
        a,b=RawChunk(0),RawChunk(1)
        a.total_samples=4000;b.total_samples=4000
        a.late_samples=1000
        row=make_row(a,b,MelFFT())
        self.assertFalse(row['valid'])
        self.assertIsNone(row['audio_rms'])

if __name__=='__main__':unittest.main()
