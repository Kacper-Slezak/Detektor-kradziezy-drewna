"""Train wideband-energy v4.6 TinyCNN with optional selective YAMNet supervision.

The old models and results are NOT modified. A 4 kHz 8x24 + RMS9 model
is exported to an original LoPy compatible, INT8-weight Python module.
Teacher runs only on the PC. Tests on new, independent WAV remain necessary.
"""
from __future__ import annotations
import argparse,base64,csv,hashlib,importlib.util,json
from pathlib import Path
import numpy as np
from algorithm.app import _v46_training as baseline
from algorithm.app._v46_training import (selective_targets,
                          teacher_weight_multiplier,choose_operating_threshold)
from algorithm.core.tg_cnn_v46 import score_features

FRAMES=8
BANDS=24
FREQUENCY_GROUPS=6
ENV_FEATURES=9


def patches(X):
    n=len(X)
    if X.shape!=(n,FRAMES,BANDS):
        raise ValueError('Expected [N,8,24] mel features')
    padded=np.pad(X,((0,0),(1,1),(1,1)),mode='constant')
    out=np.empty((n,FRAMES*BANDS,9),dtype=np.float32)
    for dt in range(3):
        for df in range(3):
            out[:,:,(dt*3+df)]=padded[:,dt:dt+FRAMES,df:df+BANDS].reshape(n,FRAMES*BANDS)
    return out


def init(seed,channels,hidden):
    r=np.random.default_rng(seed)
    size=12*channels+ENV_FEATURES
    return [
        (r.standard_normal((9,channels),dtype=np.float32)*np.sqrt(2./9.)).astype(np.float32),
        np.zeros(channels,np.float32),
        (r.standard_normal((size,hidden),dtype=np.float32)*np.sqrt(2./size)).astype(np.float32),
        np.zeros(hidden,np.float32),
        (r.standard_normal((hidden,1),dtype=np.float32)*np.sqrt(2./hidden)).astype(np.float32),
        np.zeros(1,np.float32),
    ]


def forward(P,E,params,with_cache=False):
    wc,bc,wd,bd,wo,bo=params
    channels=len(bc)
    z=P@wc+bc
    activation=np.maximum(z,0).reshape(-1,FRAMES,FREQUENCY_GROUPS,4,channels)
    group=activation.transpose(0,2,1,3,4).reshape(-1,FREQUENCY_GROUPS,32,channels)
    avg=group.mean(axis=2)
    argmax=np.argmax(group,axis=2)
    mx=np.max(group,axis=2)
    pooled=np.concatenate([avg.reshape(-1,FREQUENCY_GROUPS*channels),
                           mx.reshape(-1,FREQUENCY_GROUPS*channels),E],axis=1)
    zh=pooled@wd+bd
    h=np.maximum(zh,0)
    prediction=baseline.sigmoid(h@wo+bo).reshape(-1)
    if with_cache:return prediction,(z,group,argmax,pooled,zh,h)
    return prediction


def train(P,E,y,targets,weights,Pval,Eval,yval,epochs,batch,lr,seed,channels,hidden,
          gain_aug_db=12.0,patience_limit=8):
    params=init(seed,channels,hidden)
    moments=[np.zeros_like(w) for w in params]
    vars_=[np.zeros_like(w) for w in params]
    rng=np.random.default_rng(seed)
    best=None;step=0;patience=0
    for epoch in range(1,epochs+1):
        chunks=np.array_split(rng.permutation(len(P)),max(1,int(np.ceil(len(P)/batch))))
        for ids in chunks:
            pi=P[ids];env=E[ids].copy()
            # Gain perturbation on the absolute RMS channel. The relative
            # mel shape + envelope remain unchanged by uniform mic gain.
            if gain_aug_db:
                env[:,-1]+=rng.uniform(-gain_aug_db,gain_aug_db,size=len(ids))*np.log(10.)/20.
                # Env has already been standardized by E_INV_STD;
                # caller applies the corresponding factor below.
            target=targets[ids];wg=weights[ids]
            pred,cache=forward(pi,env,params,True)
            z,g,argmax,pooled,zh,h=cache
            wc,bc,wd,bd,wo,bo=params
            delta=((pred-target)*wg/(float(np.sum(wg))+1e-9)).reshape(-1,1)
            dwo=h.T@delta+1e-6*wo
            dbo=delta.sum(axis=0)
            dh=(delta@wo.T)*(zh>0)
            dwd=pooled.T@dh+1e-6*wd
            dbd=dh.sum(axis=0)
            dpooled=dh@wd.T
            dgroup=np.zeros_like(g)
            count=FREQUENCY_GROUPS*channels
            dgroup+=dpooled[:,:count].reshape(-1,FREQUENCY_GROUPS,1,channels)/32.0
            np.put_along_axis(dgroup,argmax[:,:,None,:],
                np.take_along_axis(dgroup,argmax[:,:,None,:],axis=2)+
                dpooled[:,count:2*count].reshape(-1,FREQUENCY_GROUPS,1,channels),axis=2)
            dz=(dgroup.reshape(-1,FREQUENCY_GROUPS,FRAMES,4,channels)
                 .transpose(0,2,1,3,4).reshape(-1,FRAMES*BANDS,channels))
            dz*=(z>0)
            dwc=np.einsum('bpk,bpc->kc',pi,dz,optimize=True)+1e-6*wc
            dbc=dz.sum(axis=(0,1))
            grads=[dwc,dbc,dwd,dbd,dwo,dbo]
            step+=1
            for i,grad in enumerate(grads):
                moments[i]=0.9*moments[i]+0.1*grad
                vars_[i]=0.999*vars_[i]+0.001*(grad*grad)
                m=moments[i]/(1.0-0.9**step)
                v=vars_[i]/(1.0-0.999**step)
                params[i]-=lr*m/(np.sqrt(v)+1e-8)
        pv=forward(Pval,Eval,params)
        th,stats=baseline.choose_threshold(yval,pv)
        print('EPOCH %02d val_BA=%.4f recall=%.4f specificity=%.4f th=%.2f'%(
            epoch,stats['balanced_accuracy'],stats['recall'],stats['specificity'],th),flush=True)
        if best is None or stats['balanced_accuracy']>best[0]+1e-6:
            best=(stats['balanced_accuracy'],[p.copy() for p in params],epoch)
            patience=0
        else:patience+=1
        if patience>=patience_limit:break
    return best[1],best[2]


def quantize(params):
    w=[];s=[];b=[]
    for i in range(0,len(params),2):
        p=params[i]
        scale=max(float(np.max(np.abs(p)))/127.0,1e-9)
        w.append(np.rint(np.clip(p/scale,-127,127)).astype(np.int8))
        s.append(scale);b.append(params[i+1])
    return w,s,b


def quant_forward(P,E,q):
    w,s,b=q
    return forward(P,E,[w[0].astype(np.float32)*s[0],b[0],
                        w[1].astype(np.float32)*s[1],b[1],
                        w[2].astype(np.float32)*s[2],b[2]])


def export(path,mean,invstd,emean,einvstd,q,threshold,channels,hidden):
    w,s,b=q
    encode=lambda v:repr(tuple(round(float(x),9) for x in v))
    code='''"""Wideband temporal v4.6 for ORIGINAL Pycom LoPy.
YAMNet is TRAINING ONLY. INT8 weights + float activations.
Diagnostic mode; no physical alarm activation.
"""\n'''
    code+='MODEL_TYPE = "tiny_cnn_wide_v46"\nRATE = 4000\n'
    code+='INPUT_SHAPE = (8,24)\n'
    code+='CONV_CHANNELS = %d\nHIDDEN = %d\n'%(channels,hidden)
    code+='THRESHOLD = %.9f\n'%threshold
    code+='MEAN = '+encode(mean)+'\nINV_STD = '+encode(invstd)+'\n'
    code+='E_MEAN = '+encode(emean)+'\nE_INV_STD = '+encode(einvstd)+'\n'
    code+='SCALES = '+encode(s)+'\n'
    code+='BIASES = '+repr(tuple(tuple(round(float(v),9) for v in values) for values in b))+'\n'
    code+='WEIGHT_B64 = (\n'
    for arr in w:
        code+='    '+repr(base64.b64encode(arr.tobytes()).decode('ascii'))+',\n'
    code+=')\n'
    path.write_text(code,encoding='utf8')
    return len(code.encode('utf8'))


def run(args):
    root=args.results;output=args.output_dir
    if output.resolve()==root.resolve():
        raise ValueError('Output directory must differ from data directory')
    model_path=output/'tg_model_v46.py'
    if model_path.exists() and not args.overwrite:
        raise FileExistsError('v4.6 model exists, use --overwrite if intended')
    prep=json.loads((root/'wide_v46_report.json').read_text(encoding='utf8'))
    for key,name in (('base_windows_sha256','windows.csv'),
                     ('base_features_sha256','features.npz'),
                     ('wide_features_sha256','wide_v46.npz')):
        digest=hashlib.sha256((root/name).read_bytes()).hexdigest()
        if prep[key]!=digest:raise ValueError('Input data changed: '+name)
    with np.load(root/'wide_v46.npz',allow_pickle=False) as f:
        X=f['X'].astype(np.float32)
        R=f['R'].astype(np.float32)
        y=f['y'].astype(np.int8)
        split=f['splits']
    if X.shape!=(len(y),8,24) or R.shape!=(len(y),9):
        raise ValueError('Prepared v4.6 feature shape is invalid')
    with (root/'windows.csv').open(newline='',encoding='utf8') as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=len(y) or any(int(r['label'])!=int(y[i]) or r['split']!=split[i]
                                for i,r in enumerate(rows)):
        raise ValueError('Feature, label and split alignment failure')
    it=np.flatnonzero(split=='train');iv=np.flatnonzero(split=='val');ie=np.flatnonzero(split=='test')
    if any(not len(ids) or set(y[ids])!={0,1} for ids in (it,iv,ie)):
        raise ValueError('Both classes required in each split')
    m=X[it].mean(axis=(0,1));s=np.maximum(X[it].std(axis=(0,1)),0.05)
    em=R[it].mean(axis=0);es=np.maximum(R[it].std(axis=0),0.05)
    norm=np.clip((X-m[None,None,:])/s[None,None,:],-6,6).astype(np.float32)
    enr=np.clip((R-em[None,:])/es[None,:],-6,6).astype(np.float32)
    ptr=patches(norm[it]);pv=patches(norm[iv]);pe=patches(norm[ie])
    sources=[rows[int(i)]['source'] for i in it]
    weights=baseline.weights_for_sources(y[it],sources)
    targets=y[it].astype(np.float32)
    teacher_info={'used':False}
    if args.teacher_alpha>0:
        report=json.loads((root/'teacher_report.json').read_text(encoding='utf8'))
        if report.get('features_sha256')!=prep['base_features_sha256'] or \
           report.get('windows_sha256')!=prep['base_windows_sha256']:
            raise ValueError('YAMNet teacher belongs to different FSC22 preparation')
        teacher=np.load(root/'teacher_scores.npy',allow_pickle=False)
        if teacher.shape!=(len(rows),) or not np.isfinite(teacher[it]).all():
            raise ValueError('Missing YAMNet scores for training set')
        targets,agrees=selective_targets(y[it],teacher[it],args.teacher_alpha,args.teacher_cutoff)
        weights*=teacher_weight_multiplier(y[it],teacher[it],args.teacher_cutoff,
                                           args.hard_negative_boost)
        teacher_info={'used':True,'agree_train_windows':int(agrees.sum()),
                      'disagree_train_windows':int((~agrees).sum())}
    weights/=max(float(weights.mean()),1e-12)
    print('V46 WIDEBAND train=%d val=%d test=%d teacher=%s'%(
        len(it),len(iv),len(ie),teacher_info['used']),flush=True)
    # Convert dB gain jitter to std-normalized absolute log RMS units.
    normalized_gain_aug=args.gain_aug_db/max(float(es[-1]),1e-6)
    params,epoch=train(ptr,enr[it],y[it],targets,weights,pv,enr[iv],y[iv],
                       args.epochs,args.batch,args.lr,args.seed,
                       args.conv_channels,args.hidden,
                       gain_aug_db=normalized_gain_aug)
    q=quantize(params)
    val_sc=quant_forward(pv,enr[iv],q)
    threshold,val_report,selection=choose_operating_threshold(
        y[iv],val_sc,args.min_val_recall,args.target_val_specificity)
    test_sc=quant_forward(pe,enr[ie],q)
    test_report=baseline.metrics(y[ie],test_sc,threshold)
    output.mkdir(parents=True,exist_ok=True)
    size=export(model_path,m,1/s,em,1/es,q,threshold,args.conv_channels,args.hidden)
    if size>args.max_export_bytes:
        model_path.unlink()
        raise ValueError('Model exceeds Flash source budget')
    spec=importlib.util.spec_from_file_location('v46_exported',model_path)
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    idx=np.linspace(0,len(iv)-1,num=min(30,len(iv)),dtype=int)
    maxdev=0.0
    for i in idx:
        source_index=iv[i]
        predicted=score_features(X[source_index].reshape(-1),R[source_index],model)
        maxdev=max(maxdev,abs(float(predicted)-float(val_sc[i])))
    if maxdev>0.005:
        raise ValueError('Quantized export differs from numpy implementation: '+str(maxdev))
    report={'method':'8x24 4kHz mel + RMS envelope CNN, selective teacher',
            'hardware_target':'original Pycom LoPy',
            'teacher':teacher_info,'teacher_alpha':args.teacher_alpha,
            'selected_epoch':epoch,'threshold':threshold,
            'threshold_selection':selection,'model_path':str(model_path),
            'model_flash_file_bytes':size,'int8_weight_bytes':sum(w.size for w in q[0]),
            'architecture':{'input':[8,24],'energy':9,'channels':args.conv_channels,
                            'hidden':args.hidden,'frequency_groups':6},
            'validation':val_report,'test':test_report,
            'export_parity_max_error':maxdev,
            'gain_augmentation_db':args.gain_aug_db,
            'hardware_ram_measured':False,'hardware_runtime_measured':False,
            'warning':'Validation/test windows are NOT independent field false alarms per hour. Real LoPy timing unmeasured.'}
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results',type=Path,default=Path('algorithm/results/v4_2_fsc22'))
    p.add_argument('--output-dir',type=Path,default=Path('algorithm/results/v4_6_wideband'))
    p.add_argument('--conv-channels',type=int,default=16)
    p.add_argument('--hidden',type=int,default=64)
    p.add_argument('--teacher-alpha',type=float,default=.20)
    p.add_argument('--teacher-cutoff',type=float,default=.24)
    p.add_argument('--hard-negative-boost',type=float,default=1.5)
    p.add_argument('--gain-aug-db',type=float,default=9.0)
    p.add_argument('--min-val-recall',type=float,default=.8)
    p.add_argument('--target-val-specificity',type=float,default=.97)
    p.add_argument('--epochs',type=int,default=40)
    p.add_argument('--batch',type=int,default=128)
    p.add_argument('--lr',type=float,default=.001)
    p.add_argument('--seed',type=int,default=2026)
    p.add_argument('--max-export-bytes',type=int,default=65536)
    p.add_argument('--overwrite',action='store_true')
    a=p.parse_args()
    if a.conv_channels not in (8,12,16,24) or a.hidden not in (32,48,64,96):
        p.error('Allowed channels: 8/12/16/24; hidden: 32/48/64/96')
    if 0> a.teacher_alpha or a.teacher_alpha >.5:p.error('teacher-alpha must be 0..0.5')
    if not 0<=a.gain_aug_db<=24:p.error('gain-aug-db must be 0..24')
    if a.epochs<1 or a.batch<1:p.error('epochs/batch must be positive')
    run(a)

if __name__=='__main__':main()
