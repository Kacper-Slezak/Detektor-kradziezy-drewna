"""Original LoPy-compatible 8x24 wideband temporal CNN inference.

Weight matrices INT8, float activations. No external libraries, DSP, or
TensorFlow required besides MicroPython math, array, ubinascii.
"""
try:
    import ubinascii as binascii
except ImportError:
    import binascii
import math
from array import array


def _signed(b):
    return b-256 if b>127 else b


def score_features(patch,energy,model):
    if model.MODEL_TYPE!='tiny_cnn_wide_v46' or model.RATE!=4000:
        raise ValueError('Expected v4.6 model at 4kHz')
    if len(patch)!=8*24 or len(energy)!=9:
        raise ValueError('Expected 8x24 bands + 9 energy features')
    channels=int(model.CONV_CHANNELS)
    hidden_n=int(model.HIDDEN)
    cached=getattr(model,'_cached_weights',None)
    if cached is None:
        cached=tuple(binascii.a2b_base64(blob) for blob in model.WEIGHT_B64)
        model._cached_weights=cached
    wc,wd,wo=cached
    size=12*channels+9
    if len(wc)!=9*channels or len(wd)!=size*hidden_n or len(wo)!=hidden_n:
        raise ValueError('Corrupt v4.6 model weights')
    x=array('f',(max(-6.0,min(6.0,
             (float(patch[t*24+f])-model.MEAN[f])*model.INV_STD[f]))
             for t in range(8) for f in range(24)))
    env=array('f',(max(-6.0,min(6.0,
              (float(energy[i])-model.E_MEAN[i])*model.E_INV_STD[i]))
              for i in range(9)))
    conv=array('f',[0.0])*(8*24*channels)
    s0=model.SCALES[0];b0=model.BIASES[0]
    for t in range(8):
        for f in range(24):
            base=(t*24+f)*channels
            for c in range(channels):
                z=b0[c]
                for dt in (-1,0,1):
                    tt=t+dt
                    if tt<0 or tt>=8:continue
                    for df in (-1,0,1):
                        ff=f+df
                        if ff<0 or ff>=24:continue
                        k=((dt+1)*3+(df+1))*channels+c
                        z+=x[tt*24+ff]*(_signed(wc[k])*s0)
                conv[base+c]=max(0.0,z)
    pooled=array('f',[0.0])*(12*channels+9)
    for group in range(6):
        for c in range(channels):
            total=0.0;maximum=0.0
            for t in range(8):
                for f in range(group*4,group*4+4):
                    v=conv[(t*24+f)*channels+c]
                    total+=v
                    if v>maximum:maximum=v
            pooled[group*channels+c]=total/32.0
            pooled[6*channels+group*channels+c]=maximum
    for i in range(9):
        pooled[12*channels+i]=env[i]
    h=array('f',[0.0])*hidden_n
    s1=model.SCALES[1];b1=model.BIASES[1]
    for j in range(hidden_n):
        z=b1[j]
        for i in range(size):
            z+=pooled[i]*(_signed(wd[i*hidden_n+j])*s1)
        h[j]=max(0.0,z)
    z=model.BIASES[2][0]
    s2=model.SCALES[2]
    for i in range(hidden_n):
        z+=h[i]*(_signed(wo[i])*s2)
    z=max(-40.0,min(40.0,z))
    return 1.0/(1.0+math.exp(-z))
