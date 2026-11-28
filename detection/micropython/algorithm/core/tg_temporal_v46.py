"""Portable v4.6 4 kHz audio features for the ORIGINAL Pycom LoPy.

Eight 250 ms frames / 2 s, 24 mel bands 35..1900 Hz. Crucially, we
no longer downsample 4 kHz -> 2 kHz or normalize against a single
largest frequency bin. We retain window-centered log-mel plus nine
energy envelope features (8 relative log RMS values + 1 absolute log RMS).

Pure Python/MicroPython; 1024-point radix-2 FFT, array('f') buffers.
Original LoPy real-time performance MUST be measured on hardware.
"""
import math
from array import array

SAMPLE_RATE = 4000
FFT_N = 1024
FRAME_N = 1000
N_BANDS = 24
N_FRAMES = 8
BAND_MIN_HZ = 35.0
BAND_MAX_HZ = 1900.0
FEATURE_TYPE = 'v46_mel24_rms9'


def sparse_bands():
    mel = lambda hz: 1127.0 * math.log(1.0 + hz / 700.0)
    inv = lambda x: 700.0 * (math.exp(x / 1127.0) - 1.0)
    low = mel(BAND_MIN_HZ)
    high = mel(BAND_MAX_HZ)
    hz = [inv(low + (high-low)*i/(N_BANDS+1)) for i in range(N_BANDS+2)]
    out = []
    for i in range(N_BANDS):
        left, center, right = hz[i:i+3]
        ids, weights = [], []
        for k in range(1,FFT_N//2+1):
            f = SAMPLE_RATE*k/FFT_N
            if left < f < right:
                w = (f-left)/(center-left) if f <= center else (right-f)/(right-center)
                if w > 0.0:
                    ids.append(k); weights.append(w)
        s=sum(weights)
        if s <= 0.0:
            raise ValueError('Empty mel filter at band %d'%i)
        out.append((ids,[w/s for w in weights]))
    return out


def normalize_window(logmel,logrms):
    """Return (8x24 patch flattened, 9 energy features), gain-aware.

    Mel uses window MEAN centering rather than MAX. Relative RMS captures
    temporal modulation; final feature preserves overall amplitude. Signal
    gain mismatch across real microphones remains a calibration risk.
    """
    if len(logmel) != N_FRAMES*N_BANDS or len(logrms) != N_FRAMES:
        raise ValueError('Expected 8x24 mel and 8 RMS features')
    center=sum(logmel)/float(len(logmel))
    patch=[max(-10.0,min(10.0,float(v)-center)) for v in logmel]
    mean_rms=sum(logrms)/float(len(logrms))
    energy=[max(-4.0,min(4.0,float(v)-mean_rms)) for v in logrms]
    energy.append(float(mean_rms))
    return patch,energy


class RawChunk:
    """One second of 4 kHz PCM16, ~8 KiB. ADC normalized 0..1."""
    def __init__(self,start_s):
        self.start_s=float(start_s)
        self.samples=array('h')
        self.total_samples=0
        self.late_samples=0
        self.start_gap_us=0
        self.cached_features=None
        self.energy_sum=0.0
        self.sample_sum=0.0

    def add_sample(self,adc_0_1):
        x=max(0.0,min(1.0,float(adc_0_1)))
        v=int(round((x*2.0-1.0)*32767.0))
        self.samples.append(v)
        self.energy_sum+=float(v)*float(v)
        self.sample_sum+=float(v)


class MelFFT:
    """Reusable radix-2 FFT with exact same window/bands as PC path."""
    def __init__(self):
        self.cos=array('f',(math.cos(2*math.pi*k/FFT_N) for k in range(FFT_N//2)))
        self.sin=array('f',(-math.sin(2*math.pi*k/FFT_N) for k in range(FFT_N//2)))
        self.hann=array('f',(0.5-0.5*math.cos(2*math.pi*i/(FRAME_N-1)) for i in range(FRAME_N)))
        rev=[]
        for i in range(FFT_N):
            n=i;j=0
            for _ in range(10):
                j=(j<<1)|(n&1);n >>= 1
            rev.append(j)
        self.reverse=array('H',rev)
        self.bands=sparse_bands()
        self.re=array('f',[0.0])*FFT_N
        self.im=array('f',[0.0])*FFT_N

    def frame(self,samples):
        if len(samples)!=FRAME_N:
            raise ValueError('Expected 1000 PCM16 samples')
        # input in natural PCM units; power spectrum in PCM units, matching PC
        mean=sum(samples)/float(FRAME_N)
        re=self.re;im=self.im
        for i in range(FFT_N):
            re[i]=0.0;im[i]=0.0
        msq=0.0
        for i in range(FRAME_N):
            v=(float(samples[i])-mean)
            msq+=v*v
            re[self.reverse[i]]=v*self.hann[i]
        n=2
        while n<=FFT_N:
            half=n//2;stride=FFT_N//n
            for start in range(0,FFT_N,n):
                for k in range(half):
                    i=start+k;j=i+half;tw=stride*k
                    r=self.cos[tw]*re[j]-self.sin[tw]*im[j]
                    q=self.cos[tw]*im[j]+self.sin[tw]*re[j]
                    u=re[i];v=im[i]
                    re[i]=u+r;im[i]=v+q
                    re[j]=u-r;im[j]=v-q
            n*=2
        powers=[re[k]*re[k]+im[k]*im[k] for k in range(FFT_N//2+1)]
        mel=[]
        for ids,weights in self.bands:
            e=0.0
            for k,w in zip(ids,weights):
                e+=powers[k]*w
            mel.append(math.log(e+1e-6))
        rms=math.sqrt(msq/float(FRAME_N))/32768.0
        return mel, math.log(rms+1e-7)

    def second(self,chunk):
        if chunk.cached_features is not None:
            return chunk.cached_features
        if len(chunk.samples)!=SAMPLE_RATE:
            raise ValueError('Expected 4000 PCM16 samples per second')
        logmel=[];logrms=[]
        for f in range(4):
            mel,rms=self.frame(chunk.samples[f*FRAME_N:(f+1)*FRAME_N])
            logmel.extend(mel);logrms.append(rms)
        chunk.cached_features=(logmel,logrms)
        return chunk.cached_features


def make_row(previous,current,extractor,max_late_ratio=0.08,max_gap_us=20000):
    valid=(len(previous.samples)==4000 and len(current.samples)==4000
           and previous.total_samples>=4000 and current.total_samples>=4000
           and previous.late_samples <= previous.total_samples*max_late_ratio
           and current.late_samples <= current.total_samples*max_late_ratio
           and previous.start_gap_us<=max_gap_us
           and current.start_gap_us<=max_gap_us)
    row={'time_s':previous.start_s,'window_end_s':current.start_s+1.0,
         'valid':bool(valid),'audio_rms':None,
         'late_samples':previous.late_samples+current.late_samples,
         'processing_gap_us':max(previous.start_gap_us,current.start_gap_us)}
    if not valid:
        row['wide_patch']=None;row['energy_envelope']=None
        return row
    a,b=extractor.second(previous)
    c,d=extractor.second(current)
    row['wide_patch'],row['energy_envelope']=normalize_window(a+c,b+d)
    total_energy=previous.energy_sum+current.energy_sum
    total_samples=previous.sample_sum+current.sample_sum
    centered_energy=max(0.0,total_energy-total_samples*total_samples/8000.0)
    row['audio_rms']=math.sqrt(centered_energy/8000.0)/32768.0
    return row
