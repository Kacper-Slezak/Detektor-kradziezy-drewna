"""Desktop inference for v4.6 wideband CNN on real WAV recordings.

The output is a continuous event report, NOT hardware timing evidence.
No validation audio is inserted into the training data.
"""
from __future__ import annotations
import argparse,csv,importlib.util,tempfile,wave
from pathlib import Path
import numpy as np
from algorithm.app.v4_2_prepare import convert
from algorithm.app.v4_6_prepare import features_per_second
from algorithm.core.tg_temporal_v46 import normalize_window
from algorithm.core.tg_presence_v46 import Presence


def load_model(path):
    if not path.is_file():raise FileNotFoundError(path)
    spec=importlib.util.spec_from_file_location('v46_infer_export',path)
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    if model.MODEL_TYPE!='tiny_cnn_wide_v46' or model.RATE!=4000:
        raise ValueError('Expected trained 4kHz v4.6 model')
    return model


def run(args):
    model=load_model(args.model)
    if not args.audio_wav.is_file():raise FileNotFoundError(args.audio_wav)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    detector=Presence(model,threshold=model.THRESHOLD if args.threshold is None else args.threshold,
                      span=args.span,fraction=args.fraction,off_hours=args.off_hours)
    with tempfile.TemporaryDirectory() as td:
        wav4=Path(td)/'4k.wav'
        convert(args.audio_wav,wav4,4000)
        mel,env=features_per_second(wav4)
        with wave.open(str(wav4),'rb') as wf:
            samples=np.frombuffer(wf.readframes(wf.getnframes()),dtype='<i2')
    if len(mel)<2:raise ValueError('Audio must last at least 2 seconds')
    counts=dict(windows=0,hits=0,persistent=0,alarms=0)
    with args.output.open('w',newline='',encoding='utf8') as f:
        writer=None
        for n in range(len(mel)-1):
            patch,energy=normalize_window(mel[n:n+2].reshape(-1),env[n:n+2].reshape(-1))
            block=samples[n*4000:(n+2)*4000].astype(np.float64)
            rms=float(np.sqrt(np.mean((block-block.mean())**2)) / 32768.0)
            row=dict(time_s=float(n),window_end_s=float(n+2),valid=True,
                     audio_rms=rms,wide_patch=patch,energy_envelope=energy)
            decision=detector.step(row)
            # Raw 8x24 bands are intentionally excluded from the CSV.
            decision.pop('wide_patch',None);decision.pop('energy_envelope',None)
            if writer is None:
                writer=csv.DictWriter(f,fieldnames=list(decision.keys()))
                writer.writeheader()
            writer.writerow(decision)
            counts['windows']+=1
            counts['hits']+=int(decision['engine_detected'])
            counts['persistent']+=int(decision['engine_confirmed'])
            counts['alarms']+=int(decision['alarm'])
            if not args.quiet:
                print('%.1fs score=%.3f votes=%d alarm=%d'%(decision['time_s'],
                    decision['ml_engine_score'],decision['engine_vote_count'],decision['alarm']))
    print('MODEL:',args.model,'THRESHOLD:',detector.threshold)
    print('SUMMARY:',counts)
    print('CSV:',args.output)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model',type=Path,default=Path('algorithm/results/v4_6_wideband/tg_model_v46.py'))
    p.add_argument('--audio-wav',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--off-hours',action='store_true')
    p.add_argument('--quiet',action='store_true')
    p.add_argument('--threshold',type=float)
    p.add_argument('--span',type=int,default=15)
    p.add_argument('--fraction',type=float,default=.60)
    run(p.parse_args())
if __name__=='__main__':main()
