"""Legacy manifest/PCM utilities used only to rebuild v4.2 FSC22 source cache.

Kept without the unused RandomForest trainer and scikit-learn dependencies.
"""
from __future__ import annotations
import csv,hashlib,math,ntpath,wave,zipfile
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np

def manifest_rows(path: Path):
    with path.open(newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        required = {'dataset','container','audio_member','source_id','group',
                    'target_engine','use_for_training','split','sha256'}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError('Missing CSV fields: ' + ', '.join(sorted(missing)))
        rows = list(reader)
    chosen = [r for r in rows if r['use_for_training'] == '1' and
              r['target_engine'] in ('0', '1') and r['split'] in ('train','val','test')]
    keys = [(r['dataset'],r['audio_member']) for r in chosen]
    if len(set(keys)) != len(keys):
        raise ValueError('Duplicate audio members')
    if len({r['sha256'] for r in chosen}) != len(chosen):
        raise ValueError('Exact audio duplicates among selected entries')
    # For ESC-50 one source ID can map to several cuts; those must not leak.
    sources = defaultdict(set)
    for r in chosen:
        sources[(r['dataset'],r['source_id'])].add(r['split'])
    overlapping = [k for k,v in sources.items() if len(v)>1]
    if overlapping:
        raise ValueError('Source ID found across splits: ' + str(overlapping[:5]))
    return rows, chosen



def locate_archive(row, data_dir: Path):
    filename = ntpath.basename(row['container'].replace('/', '\\'))
    path = data_dir / filename
    if not path.is_file():
        raise FileNotFoundError('Missing archive: ' + str(path))
    return path



def check_archives(chosen, data_dir):
    names = sorted(set(ntpath.basename(r['container'].replace('/', '\\')) for r in chosen))
    present = {}
    for filename in names:
        path = data_dir/filename
        if not path.is_file():
            raise FileNotFoundError('Archive not found: '+str(path))
        with zipfile.ZipFile(path) as z:
            present[filename]=set(z.namelist())
    missing = []
    for r in chosen:
        fname=ntpath.basename(r['container'].replace('/', '\\'))
        if r['audio_member'] not in present[fname]:
            missing.append((fname,r['audio_member']))
    if missing:
        raise ValueError('Audio members missing (first 5): '+str(missing[:5]))
    return names



def info(chosen):
    print('Selected:',len(chosen))
    print('By split and label:')
    for split in ('train','val','test'):
        print(' ',split, 'NO_ENGINE',sum(r['target_engine']=='0' and r['split']==split for r in chosen),
              'ENGINE',sum(r['target_engine']=='1' and r['split']==split for r in chosen))
    print('Too short (<2s):',sum(float(r['duration_s']) < 2 for r in chosen))



def pcm_read(path):
    with wave.open(str(path),'rb') as w:
        if w.getnchannels()!=1 or w.getsampwidth()!=2:
            raise ValueError('Expected mono PCM16: '+str(path))
        rate=w.getframerate()
        data=np.frombuffer(w.readframes(w.getnframes()),'<i2').astype(np.float64)/32768.0
    return rate,data



def pcm_write(path, signal, rate):
    values=np.asarray(np.clip(signal,-0.999,0.999)*32767.0,dtype='<i2')
    with wave.open(str(path),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate)
        w.writeframes(values.tobytes())



def create_mix(engine, noise, snr_db, rng):
    if len(engine)==0 or len(noise)==0:
        raise ValueError('Empty audio')
    n=len(engine)
    shift=rng.randrange(len(noise))
    indices=(np.arange(n)+shift)%len(noise)
    bg=noise[indices]
    power_e=np.mean(engine*engine)+1e-12
    power_bg=np.mean(bg*bg)+1e-12
    gain=math.sqrt(power_e/(power_bg*10**(snr_db/10.0)))
    mixed=engine + bg*gain
    peak=np.max(np.abs(mixed))
    if peak>0.98:
        mixed*=0.98/peak  # common scaling, preserves SNR (no clipping)
    return mixed

