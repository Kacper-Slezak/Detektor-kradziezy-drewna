"""Run YAMNet teacher on original/augmented 16 kHz TRAIN audio only.

Needs Python 3.11/3.12, tensorflow-cpu and tensorflow-hub; downloads a
pretrained YAMNet SavedModel on the first run. No YAMNet model is deployed.
"""
import argparse
import csv
import json
import hashlib
import wave
from collections import defaultdict
from pathlib import Path

import numpy as np

ENGINE_CLASSES=('Vehicle','Car','Truck','Bus','Engine','Engine starting',
                'Idling','Accelerating, revving, vroom','Motor vehicle (road)')


def load_audio(path):
    with wave.open(str(path),'rb') as w:
        if w.getframerate()!=16000 or w.getnchannels()!=1 or w.getsampwidth()!=2:
            raise ValueError('Expected 16 kHz mono PCM16: '+str(path))
        return np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float32)/32768.0


def run(args):
    # Lazy import so --help and data validation work without TensorFlow.
    import tensorflow as tf
    import tensorflow_hub as hub
    print('Loading teacher:',args.hub_url,flush=True)
    teacher=hub.load(args.hub_url)
    class_map=teacher.class_map_path().numpy().decode('utf-8')
    with open(class_map,newline='',encoding='utf-8') as f:
        names=[r['display_name'] for r in csv.DictReader(f)]
    picks=[(n,names.index(n)) for n in ENGINE_CLASSES if n in names]
    if not picks:
        raise RuntimeError('YAMNet class map contains no vehicle/engine classes')
    print('Teacher classes:',picks,flush=True)
    with (args.results/'windows.csv').open(newline='',encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    by_file=defaultdict(list)
    for r in rows:
        if r['split']=='train':
            if not r['teacher_audio']:
                raise ValueError('Missing teacher audio for training window '+r['index'])
            by_file[r['teacher_audio']].append(r)
    soft=np.full(len(rows),np.nan,dtype=np.float32)
    for ix,(filename,windows) in enumerate(sorted(by_file.items()),1):
        path=args.results/'teacher_audio'/filename
        audio=load_audio(path)
        scores, _, _=teacher(tf.convert_to_tensor(audio,dtype=tf.float32))
        scores=np.asarray(scores.numpy(),dtype=np.float32)
        # YAMNet: 0.96 s frames, 0.48 s hop, center at t+0.48 s.
        centers=np.arange(len(scores),dtype=np.float32)*0.48 + 0.48
        chosen=scores[:,[i for _,i in picks]].max(axis=1)
        for r in windows:
            t=float(r['time_s'])
            sel=chosen[(centers>=t) & (centers < t+2.0)]
            if not len(sel):
                sel=chosen[np.argmin(abs(centers-(t+1.0))):][:1]
            # Two best patches preserve short, recognizable engine events.
            top=sorted(sel,reverse=True)[:2]
            soft[int(r['index'])]=float(np.mean(top))
        if ix%50==0 or ix==len(by_file):
            print('YAMNET %d/%d files' % (ix,len(by_file)),flush=True)
    missing=[int(r['index']) for r in rows if r['split']=='train' and not np.isfinite(soft[int(r['index'])])]
    if missing:
        raise RuntimeError('Teacher predictions missing: '+str(missing[:5]))
    np.save(args.results/'teacher_scores.npy',soft)
    summary={'model':args.hub_url,
             'features_sha256':hashlib.sha256((args.results/'features.npz').read_bytes()).hexdigest(),
             'windows_sha256':hashlib.sha256((args.results/'windows.csv').read_bytes()).hexdigest(),
             'target_classes':[n for n,_ in picks],
             'train_windows':int(np.isfinite(soft).sum()),
             'mean_teacher_train_score':float(np.nanmean(soft)),
             'teacher_is_not_ground_truth':True}
    (args.results/'teacher_report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,default=Path('algorithm/results/v4_2'))
    p.add_argument('--hub-url',default='https://tfhub.dev/google/yamnet/1')
    args=p.parse_args()
    run(args)

if __name__=='__main__':main()
