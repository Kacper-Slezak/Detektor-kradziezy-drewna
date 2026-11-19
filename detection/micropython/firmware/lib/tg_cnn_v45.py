"""Parametric int8-weight CNN for Pycom LoPy, 8x16 log-mel input.

The same v4.4 feature extractor is used to isolate the effect of model
capacity. CNN activations and normalization use float Python arithmetic;
no TensorFlow, numpy, or TFLite required on the microcontroller.
"""
try:
    import ubinascii as binascii
except ImportError:
    import binascii
import math
from array import array


def _signed(b):
    return b-256 if b > 127 else b


def score_bands(values, model):
    if model.MODEL_TYPE != 'tiny_cnn_mel_v45' or model.RATE != 4000:
        raise ValueError('Expected v4.5 model')
    if len(values) != 128 or len(model.MEAN) != 16 or len(model.INV_STD) != 16:
        raise ValueError('Expected 8x16 bands')
    channels = int(model.CONV_CHANNELS)
    hidden_n = int(model.HIDDEN)
    if channels < 1 or hidden_n < 1:
        raise ValueError('Invalid model dimensions')
    cached = getattr(model, '_cached_weights', None)
    if cached is None:
        cached = tuple(binascii.a2b_base64(blob) for blob in model.WEIGHT_B64)
        model._cached_weights = cached
    wconv, wdense, wout = cached
    if (len(wconv) != 9*channels or
            len(wdense) != (8*channels)*hidden_n or
            len(wout) != hidden_n):
        raise ValueError('Corrupt model weight lengths')
    x = array('f', (max(-6., min(6.,
                (float(values[t*16+f])-model.MEAN[f])*model.INV_STD[f]))
                for t in range(8) for f in range(16)))
    conv = array('f', [0.0]) * (128*channels)
    b0 = model.BIASES[0]
    s0 = model.SCALES[0]
    for t in range(8):
        for f in range(16):
            base = (t*16+f)*channels
            for c in range(channels):
                z = b0[c]
                for dt in (-1,0,1):
                    tt=t+dt
                    if tt<0 or tt>=8:continue
                    for df in (-1,0,1):
                        ff=f+df
                        if ff<0 or ff>=16:continue
                        wpos=((dt+1)*3+(df+1))*channels+c
                        z+=x[tt*16+ff]*(_signed(wconv[wpos])*s0)
                conv[base+c] = max(0.0,z)
    p = array('f',[0.0])*(8*channels)
    for group in range(4):
        for c in range(channels):
            total = 0.;peak=0.
            for t in range(8):
                for f in range(group*4,group*4+4):
                    val=conv[(t*16+f)*channels+c]
                    total+=val
                    if val>peak:peak=val
            p[group*channels+c]=total/32.0
            p[4*channels+group*channels+c]=peak
    h=array('f',[0.0])*hidden_n
    b1=model.BIASES[1];s1=model.SCALES[1]
    for j in range(hidden_n):
        z=b1[j]
        for i in range(8*channels):
            z+=p[i]*(_signed(wdense[i*hidden_n+j])*s1)
        h[j]=max(0.0,z)
    z=model.BIASES[2][0]
    s2=model.SCALES[2]
    for i in range(hidden_n):
        z+=h[i]*(_signed(wout[i])*s2)
    z=max(-40., min(40.,z))
    return 1.0/(1.0+math.exp(-z))
