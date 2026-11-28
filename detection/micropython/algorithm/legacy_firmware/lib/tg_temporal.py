"""Timber Guard v4.4: portable 8x16 log-mel input for original LoPy.

8 frames of 250 ms at a 2 kHz anti-aliased decimation of 4 kHz audio.
FFT size 512, 500 usable points/frame. No numpy / TensorFlow on LoPy.
Input gain is removed over the 2-second window; timing and signal
validation are still mandatory. Flash/RAM/timing MUST be measured on hardware.
"""
import math
from array import array

SAMPLE_RATE = 4000
DECIMATED_RATE = 2000
FRAME_N = 500
FFT_N = 512
N_BANDS = 16
N_FRAMES = 8
HOP_SECONDS = 1
N_CHANNELS = 1
BAND_MIN_HZ = 35.0
BAND_MAX_HZ = 900.0


def band_limits():
    mel = lambda hz: 1127.0 * math.log(1.0 + hz / 700.0)
    inv = lambda x: 700.0 * (math.exp(x / 1127.0) - 1.0)
    a = mel(BAND_MIN_HZ)
    b = mel(BAND_MAX_HZ)
    return [inv(a + (b-a)*i/(N_BANDS+1)) for i in range(N_BANDS+2)]


def sparse_bands():
    hz = band_limits()
    bands = []
    for i in range(N_BANDS):
        left,center,right = hz[i:i+3]
        indices = []
        values = []
        for k in range(1, FFT_N//2+1):
            f = DECIMATED_RATE*k/FFT_N
            if left < f < right:
                w = ((f-left)/(center-left) if f <= center else
                     (right-f)/(right-center))
                if w > 0:
                    indices.append(k)
                    values.append(w)
        total = sum(values)
        if total < 1e-8:
            raise ValueError('Empty mel filter')
        bands.append((indices, [v/total for v in values]))
    return bands


class TemporalFilter:
    """Two one-pole 850 Hz lowpasses before decimation; stateful."""
    def __init__(self):
        self.a = 1.0-math.exp(-2.0*math.pi*850.0/SAMPLE_RATE)
        self.p = 0.0
        self.q = 0.0
        self.ready = False

    def update(self, x):
        if not self.ready:
            self.p = x
            self.q = x
            self.ready = True
        self.p += self.a*(x-self.p)
        self.q += self.a*(self.p-self.q)
        return self.q


class TemporalChunk:
    """One second; only 4 kB of signed int16 waveform storage."""
    def __init__(self, start_s):
        self.start_s = float(start_s)
        self.samples = array('h')
        self.n = 0
        self.total_samples = 0
        self.late_samples = 0
        self.start_gap_us = 0
        self.cached_logbands = None

    def add_sample(self, filtered):
        self.n += 1
        if self.n % 2 == 0:
            v = int(filtered * 16384.0)
            if v > 32767: v = 32767
            if v < -32768: v = -32768
            self.samples.append(v)


class MelFFT:
    """512 point radix-2 FFT with precomputed twiddles; reusable arrays."""
    def __init__(self):
        self.cos = array('f', (math.cos(2*math.pi*k/FFT_N) for k in range(FFT_N//2)))
        self.sin = array('f', (-math.sin(2*math.pi*k/FFT_N) for k in range(FFT_N//2)))
        self.hann = array('f', (0.5-0.5*math.cos(2*math.pi*i/(FRAME_N-1))
                               for i in range(FRAME_N)))
        rev=[]
        for i in range(FFT_N):
            n=i; j=0
            for _ in range(9):
                j=(j<<1)|(n&1); n >>= 1
            rev.append(j)
        self.reverse=array('H', rev)
        self.bands=sparse_bands()
        self.re=array('f',[0.0])*FFT_N
        self.im=array('f',[0.0])*FFT_N

    def frame(self, samples):
        if len(samples) != FRAME_N:
            raise ValueError('Expected 500 samples per frame')
        mean=sum(samples)/float(FRAME_N)
        re=self.re; im=self.im
        for i in range(FFT_N):
            re[i]=0.0; im[i]=0.0
        for i in range(FRAME_N):
            re[self.reverse[i]]=(samples[i]-mean)*self.hann[i]
        n=2
        while n <= FFT_N:
            half=n//2; stride=FFT_N//n
            for start in range(0,FFT_N,n):
                for k in range(half):
                    i=start+k; j=i+half; tw=stride*k
                    r=self.cos[tw]*re[j]-self.sin[tw]*im[j]
                    v=self.cos[tw]*im[j]+self.sin[tw]*re[j]
                    ur=re[i]; ui=im[i]
                    re[i]=ur+r; im[i]=ui+v
                    re[j]=ur-r; im[j]=ui-v
            n*=2
        powers=[re[k]*re[k]+im[k]*im[k] for k in range(FFT_N//2+1)]
        out=[]
        for indices,weights in self.bands:
            energy=0.0
            for k,w in zip(indices,weights):
                energy+=powers[k]*w
            out.append(math.log(energy+1e-6))
        return out

    def second(self, chunk):
        if chunk.cached_logbands is not None:
            return chunk.cached_logbands
        if len(chunk.samples)!=2000:
            raise ValueError('Not a complete 4 kHz second')
        values=[]
        for frame in range(4):
            values.extend(self.frame(chunk.samples[frame*FRAME_N:(frame+1)*FRAME_N]))
        chunk.cached_logbands=values
        return values


def normalize_window(logbands):
    if len(logbands)!=N_FRAMES*N_BANDS:
        raise ValueError('Invalid temporal feature shape')
    ceiling=max(logbands)
    return [max(-10.0,min(0.0,float(v)-ceiling)) for v in logbands]


def make_row(previous, current, extractor, max_late_ratio=0.08, max_gap_us=20000):
    """Build a 2 sec streaming row from 1 sec overlapping chunks."""
    valid=(previous.total_samples>=4000 and current.total_samples>=4000
           and previous.late_samples<=previous.total_samples*max_late_ratio
           and current.late_samples<=current.total_samples*max_late_ratio
           and previous.start_gap_us<=max_gap_us
           and current.start_gap_us<=max_gap_us)
    row={'time_s':previous.start_s,'window_end_s':current.start_s+1.0,
         'valid':bool(valid), 'audio_rms':None,
         'late_samples':previous.late_samples+current.late_samples,
         'processing_gap_us':max(previous.start_gap_us,current.start_gap_us)}
    if not valid:
        row['temporal_bands']=None
        return row
    combined=extractor.second(previous)+extractor.second(current)
    row['temporal_bands']=normalize_window(combined)
    # non-null audio_rms is the existing Presence validity contract
    row['audio_rms']=1.0
    return row
