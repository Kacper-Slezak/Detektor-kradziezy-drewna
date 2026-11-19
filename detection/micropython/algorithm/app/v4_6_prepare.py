"""Prepare v4.6 wideband 8x24 log-mel + 9 energy features.

Reuses EXACT FSC22 v4.2 sources, labels, train/val/test split, and teacher
scores. Original train-window teacher WAV files carry all augmented mixtures.
No evaluation WAV may be put into training by this command.

Preparation requires ffmpeg + numpy, but LoPy inference does not.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,ntpath,tempfile,wave,zipfile
from pathlib import Path
import numpy as np
from algorithm.app.v4_2_prepare import convert
from algorithm.core.tg_temporal_v46 import (SAMPLE_RATE,FFT_N,FRAME_N,
                                          N_BANDS,sparse_bands,normalize_window)


def _source_map(manifest):
    with manifest.open(newline='',encoding='utf-8-sig') as f:
        rows=list(csv.DictReader(f))
    return {r['dataset']+'/'+r['audio_member']:r for r in rows
            if r.get('use_for_training')=='1'}


def features_per_second(wav4):
    with wave.open(str(wav4),'rb') as f:
        if (f.getnchannels(),f.getsampwidth(),f.getframerate()) != (1,2,SAMPLE_RATE):
            raise ValueError('Expected mono signed PCM16 WAV at 4000 Hz')
        pcm=np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(np.float64)
    nsec=len(pcm)//SAMPLE_RATE
    if nsec==0:
        return (np.empty((0,4,N_BANDS),np.float32),
                np.empty((0,4),np.float32))
    frames=pcm[:nsec*SAMPLE_RATE].reshape(-1,FRAME_N)
    centered=frames-frames.mean(axis=1,keepdims=True)
    rms=np.sqrt(np.mean(centered*centered,axis=1))/32768.0
    hann=0.5-0.5*np.cos(2.0*np.pi*np.arange(FRAME_N)/(FRAME_N-1))
    power=np.abs(np.fft.rfft(centered*hann[None,:],n=FFT_N,axis=1))**2
    filters=np.zeros((FFT_N//2+1,N_BANDS),dtype=np.float64)
    for i,(idx,weight) in enumerate(sparse_bands()):
        filters[idx,i]=weight
    mel=np.log(power@filters+1e-6).reshape(nsec,4,N_BANDS)
    return (mel.astype(np.float32),
            np.log(rms+1e-7).reshape(nsec,4).astype(np.float32))


def run(args):
    root=args.results
    output=root/'wide_v46.npz'
    report_path=root/'wide_v46_report.json'
    if (output.exists() or report_path.exists()) and not args.overwrite:
        raise FileExistsError('v4.6 prepared output exists. Use --overwrite only if intended.')
    with (root/'windows.csv').open(newline='',encoding='utf8') as f:
        rows=list(csv.DictReader(f))
    if not rows or any(int(r['index'])!=i for i,r in enumerate(rows)):
        raise ValueError('Invalid source windows.csv')
    source_map=_source_map(args.manifest)
    X=np.empty((len(rows),8,N_BANDS),np.float32)
    R=np.empty((len(rows),9),np.float32)
    labels=np.asarray([int(r['label']) for r in rows],dtype=np.int8)
    splits=np.asarray([r['split'] for r in rows],dtype='<U5')
    by_source={}
    for i,row in enumerate(rows):
        key=row['teacher_audio'] if row['split']=='train' else row['source']
        if not key:
            raise ValueError('Missing teacher audio for train row %d'%i)
        by_source.setdefault((row['split'],key),[]).append(i)
    archive={}
    try:
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            for n,((split,key),indices) in enumerate(by_source.items(),1):
                if split=='train':
                    wav=root/'teacher_audio'/key
                    if not wav.is_file():
                        raise FileNotFoundError('Missing cached teacher audio: '+str(wav))
                    convert(wav,td/'audio4.wav',4000)
                else:
                    entry=source_map.get(key)
                    if entry is None:
                        raise ValueError('Source absent from manifest: '+key)
                    container=ntpath.basename(entry['container'].replace('/','\\'))
                    if container not in archive:
                        archive[container]=zipfile.ZipFile(args.data_dir/container)
                    raw=archive[container].read(entry['audio_member'])
                    if hashlib.sha256(raw).hexdigest().lower()!=entry['sha256'].lower():
                        raise ValueError('Audio hash mismatch: '+key)
                    (td/'raw.wav').write_bytes(raw)
                    convert(td/'raw.wav',td/'audio16.wav',16000,args.max_seconds)
                    convert(td/'audio16.wav',td/'audio4.wav',4000)
                mel,rms=features_per_second(td/'audio4.wav')
                for i in indices:
                    start=float(rows[i]['time_s'])
                    at=int(round(start))
                    if abs(start-at)>0.03 or at<0 or at+1>=len(mel):
                        raise ValueError('2 s window out of range in '+key+' at '+str(start))
                    patch,energy=normalize_window(mel[at:at+2].reshape(-1),
                                                  rms[at:at+2].reshape(-1))
                    X[i]=np.asarray(patch,dtype=np.float32).reshape(8,N_BANDS)
                    R[i]=np.asarray(energy,dtype=np.float32)
                if n%100==0 or n==len(by_source):
                    print('V46 FEATURES %d/%d sources'%(n,len(by_source)),flush=True)
    finally:
        for z in archive.values():z.close()
    if not np.isfinite(X).all() or not np.isfinite(R).all():
        raise ValueError('Non-finite wideband features')
    np.savez_compressed(output,X=X,R=R,y=labels,splits=splits)
    report={
        'windows':len(rows),'sources':len(by_source),
        'input_patch':[8,N_BANDS],'energy_features':9,
        'sample_rate':4000,'mel_max_hz':1900,'no_downsampling':True,
        'normalization':'global logmel mean subtraction, per-frame RMS + mean log RMS',
        'base_windows_sha256':hashlib.sha256((root/'windows.csv').read_bytes()).hexdigest(),
        'base_features_sha256':hashlib.sha256((root/'features.npz').read_bytes()).hexdigest(),
        'wide_features_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
        'source_split':'Original v4.2 grouped split; no random windows split',
        'requires_independent_test':'Use real forest/truck WAV for evaluation only',
    }
    report_path.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,default=Path('algorithm/results/v4_2_fsc22'))
    p.add_argument('--manifest',type=Path,default=Path('algorithm/data/dataset_manifest_fsc22.csv'))
    p.add_argument('--data-dir',type=Path,default=Path('algorithm/data'))
    p.add_argument('--max-seconds',type=float,default=8.0)
    p.add_argument('--overwrite',action='store_true')
    run(p.parse_args())
if __name__=='__main__':main()
