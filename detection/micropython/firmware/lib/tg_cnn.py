"""Quantized v4.4 temporal 3x3 CNN inference; no numpy or TFLite required.

Architecture: 8x16 -> 3x3 conv ReLU with 6 channels -> four frequency
regions, each temporal mean and max pool -> FC24 ReLU -> logistic score.
Weight bytes are signed INT8 packed as base64. All other math is float32-like
Python scalar math; this is weight quantization, NOT full INT8 activations.
"""
try:
    import ubinascii as binascii
except ImportError:
    import binascii
import math
from array import array


def _decode(model):
    cache=getattr(model,'_cached_weights',None)
    if cache is None:
        cache=tuple(binascii.a2b_base64(x) for x in model.WEIGHT_B64)
        model._cached_weights=cache
    return cache


def _signed(b):
    return b-256 if b>127 else b


def score_bands(values, model):
    if model.MODEL_TYPE!='tiny_cnn_mel_v44' or model.RATE!=4000:
        raise ValueError('Not a Timber Guard v4.4 model')
    if len(values)!=128 or len(model.MEAN)!=16:
        raise ValueError('Expected 8x16 log-mel features')
    wconv,wdense,wout=_decode(model)
    channels=6
    if len(wconv)!=54 or len(wdense)!=48*24 or len(wout)!=24:
        raise ValueError('Corrupt quantized weights')
    normalized=array('f',(max(-6.0,min(6.0,(float(values[t*16+f])-model.MEAN[f]) *
                                                    model.INV_STD[f]))
                           for t in range(8) for f in range(16)))
    conv=array('f',[0.0])*(8*16*channels)
    biases=model.BIASES[0]
    s=model.SCALES[0]
    for t in range(8):
        for f in range(16):
            base=(t*16+f)*channels
            for c in range(channels):
                v=biases[c]
                for dt in (-1,0,1):
                    tt=t+dt
                    if tt<0 or tt>=8:continue
                    for df in (-1,0,1):
                        ff=f+df
                        if ff<0 or ff>=16:continue
                        wpos=((dt+1)*3+(df+1))*channels+c
                        v+=normalized[tt*16+ff]*(_signed(wconv[wpos])*s)
                conv[base+c]=v if v>0.0 else 0.0
    pooled=array('f',[0.0])*48
    for group in range(4):
        for c in range(channels):
            total=0.0; peak=0.0
            for t in range(8):
                for f in range(group*4,group*4+4):
                    val=conv[(t*16+f)*channels+c]
                    total+=val
                    if val>peak:peak=val
            pooled[group*channels+c]=total/32.0
            pooled[24+group*channels+c]=peak
    hidden=array('f',[0.0])*24
    bias=model.BIASES[1]; s=model.SCALES[1]
    for j in range(24):
        v=bias[j]
        for i in range(48):
            v+=pooled[i]*(_signed(wdense[i*24+j])*s)
        hidden[j]=v if v>0.0 else 0.0
    v=model.BIASES[2][0];s=model.SCALES[2]
    for i in range(24):
        v+=hidden[i]*(_signed(wout[i])*s)
    v=max(-40.0,min(40.0,v))
    return 1.0/(1.0+math.exp(-v))
