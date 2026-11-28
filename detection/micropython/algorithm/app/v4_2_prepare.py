"""Prepare source-disjoint TinyML windows and 16 kHz teacher audio.

Run from micropython/ root with the existing Python 3.13 .venv-v4.
All three dataset ZIPs and dataset_manifest.csv must exist in algorithm/data.
Only training samples are augmented, and only training audio is cached for YAMNet.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import ntpath
import random
import subprocess
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
from algorithm.app._dataset_utils import (manifest_rows, check_archives, info,
                                         pcm_read, pcm_write, create_mix)
from algorithm.app.simulate import iter_simulation
from algorithm.core.tg_nn import feature_vector

RATE = 4000
TEACHER_RATE = 16000


def convert(inp: Path, out: Path, rate: int, seconds: float | None = None):
    cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
           '-i', str(inp)]
    if seconds is not None:
        cmd += ['-t', str(seconds)]
    cmd += ['-ac', '1', '-ar', str(rate), '-c:a', 'pcm_s16le', str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError('FFmpeg failed for %s: %s' % (inp,r.stderr[-1200:]))


def read_file_rows(wav_4k, split, label, filename, group, augmented, teacher_audio,
                   rows, X, y, splits):
    for row in iter_simulation(wav_path=wav_4k, mode='audio', audio_rate=RATE):
        if not row.get('valid', True):
            continue
        X.append(feature_vector(row))
        y.append(label)
        splits.append(split)
        rows.append(dict(index=len(X)-1, source=filename, split=split,
                         label=label, group=group, augmented=int(augmented),
                         time_s=float(row['time_s']),
                         teacher_audio=teacher_audio if split=='train' else ''))


def run(args):
    _, chosen = manifest_rows(args.manifest)
    info(chosen)
    names = check_archives(chosen,args.data_dir)
    args.output.mkdir(parents=True,exist_ok=True)
    cache=args.output/'teacher_audio'
    cache.mkdir(parents=True,exist_ok=True)
    rng=random.Random(args.seed)
    X=[];y=[];splits=[];rows=[]
    engine_sources=[];noise_sources=[]
    opened={n:zipfile.ZipFile(args.data_dir/n) for n in names}
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp=Path(td)
            for pos,r in enumerate(chosen,1):
                name=ntpath.basename(r['container'].replace('/','\\'))
                src_id=r['dataset']+'/'+r['audio_member']
                key=hashlib.sha256(src_id.encode('utf-8')).hexdigest()[:20]
                raw_bytes=opened[name].read(r['audio_member'])
                if hashlib.sha256(raw_bytes).hexdigest().lower() != r['sha256'].lower():
                    raise ValueError('SHA mismatch for '+src_id)
                (tmp/'raw.wav').write_bytes(raw_bytes)
                convert(tmp/'raw.wav',tmp/'audio16.wav',TEACHER_RATE,args.max_seconds)
                convert(tmp/'audio16.wav',tmp/'audio4.wav',RATE)
                _, s16=pcm_read(tmp/'audio16.wav')
                label=int(r['target_engine']); split=r['split']; group=r['group']
                if len(s16) < 2*TEACHER_RATE:
                    continue
                audio_ref=''
                if split == 'train':
                    audio_ref=key+'.wav'
                    (cache/audio_ref).write_bytes((tmp/'audio16.wav').read_bytes())
                    if label == 1:
                        engine_sources.append((src_id,s16.astype(np.float32)))
                    elif group == 'background' and label == 0:
                        noise_sources.append((src_id,s16.astype(np.float32)))
                read_file_rows(tmp/'audio4.wav',split,label,src_id,group,False,
                               audio_ref,rows,X,y,splits)
                if pos%100==0 or pos==len(chosen):
                    print('PREPARE %d/%d files, %d windows' % (pos,len(chosen),len(X)),flush=True)

            if args.aug_per_engine and not noise_sources:
                raise ValueError('No training background for augmentation')
            for pos,(src,engine) in enumerate(engine_sources,1):
                for aug_id in range(args.aug_per_engine):
                    _,noise=rng.choice(noise_sources)
                    snr=rng.choice(args.snr)
                    # Mix at 16 kHz, then resample the SAME mixture to 4 kHz.
                    # YAMNet and the student see the same exact audio event.
                    mixture=create_mix(engine,noise,snr,rng)
                    gain=10.0**rng.uniform(-0.4,0.4)
                    safe_gain=min(gain,0.98/(float(np.max(np.abs(mixture)))+1e-9))
                    mixture=mixture*safe_gain
                    tag=src+':aug:'+str(aug_id)
                    key=hashlib.sha256(tag.encode()).hexdigest()[:20]
                    pcm_write(tmp/'mix16.wav',mixture,TEACHER_RATE)
                    audio_ref=key+'.wav'
                    (cache/audio_ref).write_bytes((tmp/'mix16.wav').read_bytes())
                    convert(tmp/'mix16.wav',tmp/'mix4.wav',RATE)
                    read_file_rows(tmp/'mix4.wav','train',1,tag,'augmented_engine',True,
                                   audio_ref,rows,X,y,splits)
                if pos%100==0 or pos==len(engine_sources):
                    print('AUGMENT %d/%d engines, %d windows' % (pos,len(engine_sources),len(X)),flush=True)
    finally:
        for z in opened.values(): z.close()
    if not X:
        raise ValueError('No complete 2-second windows produced')
    shape=len(X[0]); assert shape==63, shape
    np.savez_compressed(args.output/'features.npz',X=np.asarray(X,np.float32),
                        y=np.asarray(y,np.int8),
                        splits=np.asarray(splits,dtype='<U5'))
    with (args.output/'windows.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    stats=dict(files=len(chosen),windows=len(X),features=shape,
               splits=dict(Counter(splits)),labels=dict(Counter(y)),
               augmented_per_engine=args.aug_per_engine,
               snr_db=args.snr, teacher_rate=TEACHER_RATE, student_rate=RATE,
               teacher_audio_files=len(list(cache.glob('*.wav'))),
               leakage_protection='Augmentation from train originals and train backgrounds only')
    (args.output/'prepare_report.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
    print('PREPARED:',args.output)
    print(json.dumps(stats,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,default=Path('algorithm/data/dataset_manifest.csv'))
    p.add_argument('--data-dir',type=Path,default=Path('algorithm/data'))
    p.add_argument('--output',type=Path,default=Path('algorithm/results/v4_2'))
    p.add_argument('--max-seconds',type=float,default=8.0)
    p.add_argument('--aug-per-engine',type=int,default=2)
    p.add_argument('--snr',type=float,nargs='+',default=[-15,-10,-5,0,5,10])
    p.add_argument('--seed',type=int,default=2026)
    a=p.parse_args()
    if a.max_seconds < 2 or a.aug_per_engine<0:
        p.error('Invalid max seconds or augmentation count')
    run(a)

if __name__=='__main__':main()
