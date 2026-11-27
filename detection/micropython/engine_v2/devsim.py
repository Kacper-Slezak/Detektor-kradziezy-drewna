"""Device-domain simulation and dataset index for the engine detector (PC only).

The LoPy records the SparkFun BOB-12758 electret microphone through the ESP32
ADC: 12 bit, software-timed 4 kHz polling, *no anti-aliasing filter*.  Public
recordings are 44.1-96 kHz studio-ish captures, so before any feature is computed
we push them through a crude model of that chain:

    full-rate mono -> 1st-order high-pass ~100 Hz (BOB-12758 spec 100 Hz-10 kHz)
                   -> pick every n-th sample (no low-pass: aliasing like the ADC)
                   -> gain to a chosen RMS in ADC counts, +ADC noise, 12-bit, clip

Output of `to_adc` is an int array of raw ADC codes 0..4095, exactly what
`nagraj_audio()` in deploy/burst/main.py stores in its byte buffers.

Dataset roots default to ~/tg-data (see engine_v2/README.md for download commands).
"""

import csv
import os
import wave
from pathlib import Path

import numpy as np

FS = 4000                 # device sampling rate [Hz]
BLOCK = 4000              # samples per device block (1 s)
DATA = Path(os.environ.get('TG_DATA', Path.home() / 'tg-data'))
REPO_DET = Path(__file__).resolve().parents[2]          # detection/


def read_wav(path):
    """Return (mono float64 in [-1, 1], fs)."""
    with wave.open(str(path), 'rb') as w:
        ch, sw, fs, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw == 2:
        x = np.frombuffer(raw, '<i2').astype(np.float64) / 32768.0
    elif sw == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
        x = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8)
             | (b[:, 2].astype(np.int8).astype(np.int32) << 16)) / 8388608.0
    elif sw == 4:
        x = np.frombuffer(raw, '<i4').astype(np.float64) / 2147483648.0
    else:
        raise ValueError('sample width %d' % sw)
    x = x.reshape(-1, ch).mean(axis=1)      # (n,)
    return x, fs


def highpass(x, fs, fc=100.0):
    """1st-order high-pass |H| = (f/fc)/sqrt(1+(f/fc)^2), applied in the frequency domain."""
    X = np.fft.rfft(x)                                   # (n//2+1,)
    f = np.fft.rfftfreq(len(x), 1.0 / fs)
    jr = 1j * f / fc
    return np.fft.irfft(X * jr / (1.0 + jr), n=len(x))


def decimate_no_filter(x, fs, jitter_us=0.0, rng=None):
    """Sample x at 4 kHz by nearest-sample picking (ADC without anti-alias filter)."""
    n_out = int(len(x) * FS / fs)
    t = np.arange(n_out) / FS
    if jitter_us and rng is not None:
        t = t + rng.normal(0.0, jitter_us * 1e-6, n_out)
    idx = np.clip(np.round(t * fs).astype(np.int64), 0, len(x) - 1)
    return x[idx]


def to_adc(x4k, rms_counts, rng, noise_lsb=1.5, bias=2048):
    """Scale to a target RMS in ADC counts, add ADC noise, quantise to 12 bit codes."""
    r = np.sqrt(np.mean(x4k ** 2)) + 1e-12
    y = x4k * (rms_counts / r) + bias + rng.normal(0.0, noise_lsb, len(x4k))
    return np.clip(np.round(y), 0, 4095).astype(np.int32)


_WAV_CACHE = {}


def read_wav_cached(path):
    p = str(path)
    if p not in _WAV_CACHE:
        if len(_WAV_CACHE) > 4:
            _WAV_CACHE.clear()
        _WAV_CACHE[p] = read_wav(p)
    return _WAV_CACHE[p]


def device_float(path, start_s=0.0, dur_s=None, seed=0, hp=True):
    """Mic high-pass + no-filter decimation -> float signal at 4 kHz (before ADC gain)."""
    rng = np.random.default_rng(seed)
    x, fs = read_wav_cached(path)
    a = int(start_s * fs)
    b = len(x) if dur_s is None else min(len(x), a + int(dur_s * fs))
    x = x[a:b]
    if hp:
        x = highpass(x, fs)
    return decimate_no_filter(x, fs, jitter_us=2.0, rng=rng)


def device_pcm(path, start_s=0.0, dur_s=None, rms_counts=120.0, seed=0, hp=True):
    """Full chain for one recording slice -> raw ADC codes at 4 kHz."""
    rng = np.random.default_rng(seed)
    x, fs = read_wav(path)
    a = int(start_s * fs)
    b = len(x) if dur_s is None else min(len(x), a + int(dur_s * fs))
    x = x[a:b]
    if hp:
        x = highpass(x, fs)
    x4 = decimate_no_filter(x, fs, jitter_us=2.0, rng=rng)
    return to_adc(x4, rms_counts, rng)


# --------------------------------------------------------------------------- dataset

ESC_POS = {'engine'}
ESC_MECH = {'helicopter', 'airplane', 'train'}                 # passing machines: must not alarm
ESC_AMBIG = {'chainsaw', 'hand_saw'}                           # work at the pile: team decision
ESC_FOREST = {'rain', 'wind', 'thunderstorm', 'crickets', 'insects', 'chirping_birds', 'crow',
              'frog', 'sea_waves', 'crackling_fire', 'water_drops', 'footsteps',
              'door_wood_knock', 'door_wood_creaks', 'breathing', 'coughing', 'sneezing',
              'clapping', 'laughing', 'dog', 'rooster', 'hen', 'cow', 'pig', 'sheep', 'cat',
              'church_bells', 'fireworks', 'pouring_water'}


def esc50_items():
    root = DATA / 'esc50' / 'ESC-50-master'
    out = []
    with open(root / 'meta' / 'esc50.csv') as f:
        for r in csv.DictReader(f):
            c = r['category']
            if c in ESC_POS:
                kind = 'engine'
            elif c in ESC_MECH:
                kind = 'mech'
            elif c in ESC_AMBIG:
                kind = 'ambig'
            elif c in ESC_FOREST:
                kind = 'forest'
            else:
                kind = 'other'
            out.append(dict(path=root / 'audio' / r['filename'], start=0.0, dur=None,
                            label=int(kind == 'engine'), kind=kind, cls=c,
                            group='esc%s' % r['src_file'], fold=int(r['fold']), src='esc50'))
    return out


def ice_items():
    """Niš 'Sounds of Vehicle ICE' (Zenodo 18777405): training positives only.
    No vehicle IDs; consecutive REC numbers are often the same car, so group by REC//2."""
    out = []
    for p in sorted((DATA / 'ice').glob('*/*/*.wav')):
        n = int(''.join(ch for ch in p.stem if ch.isdigit()) or 0)
        fuel = 'd' if 'iesel' in str(p) else 'p'
        out.append(dict(path=p, start=0.0, dur=None, label=1, kind='engine', cls='ice_' + fuel,
                        group='ice%s%d' % (fuel, n // 2), fold=0, src='ice'))
    return out


def _sessions(path, total_s, label_fn, kind, cls, group, src, step=10.0):
    out = []
    t = 0.0
    while t + 5.0 <= total_s:
        out.append(dict(path=path, start=t, dur=min(10.0, total_s - t), label=label_fn(t),
                        kind=kind if label_fn(t) else 'forest', cls=cls, group=group, fold=0,
                        src=src))
        t += step
    return out


def long_items():
    """External recordings cut into 10 s device sessions. Never used for training."""
    out = []
    soc = DATA / 'soc'
    meta = [('554ca6d54da48.wav', 'john_deere'), ('5666a6150aeff.wav', 'ursus_c342'),
            ('5d8887ef96767.wav', 'peugeot_boxer'), ('5d4ac07608725.wav', 'gdynia_lorries')]
    for fn, name in meta:
        p = soc / fn
        if p.exists():
            x, fs = read_wav(p)
            out += _sessions(p, len(x) / fs, lambda t: 1, 'engine', name, 'soc_' + name, 'soc')
    sa = REPO_DET / 'python' / 'algorithm' / 'sample_audio'
    p = sa / 'forest-ambience.wav'
    if p.exists():
        out += _sessions(p, 288.0, lambda t: 0, 'forest', 'forest_ambience', 'forest', 'sample')
    p = sa / 'forest-with-truck.wav'
    if p.exists():
        # annotated engine 19-40 s (BURST_TECHNICAL_REPORT.md); sessions starting 15..35 s
        out.append(dict(path=p, start=20.0, dur=10.0, label=1, kind='engine', cls='truck',
                        group='truck', fold=0, src='sample'))
        out.append(dict(path=p, start=0.0, dur=10.0, label=0, kind='forest', cls='truck_pre',
                        group='truck', fold=0, src='sample'))
    return out


def soc2_items(max_sessions=12):
    """Extra soundsofchanges.eu engine recordings (CC BY 4.0), manifest in $TG_DATA/soc2.
    Each recording is assigned to a CV fold 1..5 by a stable hash of its slug."""
    import hashlib
    out = []
    man = DATA / 'soc2' / 'manifest.csv'
    if not man.exists():
        return out
    for line in open(man):
        parts = line.strip().split(',')
        if len(parts) < 3 or parts[0] not in ('pos', 'neg'):
            continue
        lab, slug = parts[0], parts[1]
        p = DATA / 'soc2' / (slug + '.wav')
        with wave.open(str(p)) as w:
            total = w.getnframes() / w.getframerate()
        fold = 1 + int(hashlib.sha256(slug.encode()).hexdigest(), 16) % 5
        starts = np.arange(0.0, max(0.0, total - 5.0), 10.0)
        if len(starts) > max_sessions:
            starts = starts[np.linspace(0, len(starts) - 1, max_sessions).round().astype(int)]
        for t in starts:
            out.append(dict(path=p, start=float(t), dur=min(10.0, total - t),
                            label=int(lab == 'pos'), kind='engine' if lab == 'pos' else 'forest',
                            cls=slug[:40], group='soc2_' + slug, fold=fold, src='soc2'))
    return out


FSD_KEY = ('Thunderstorm', 'Thunder', 'Rain', 'Raindrop', 'Wind', 'Stream', 'Waves_and_surf',
           'Ocean', 'Fire', 'Crackle', 'Cricket', 'Insect', 'Bird', 'Frog', 'Crow',
           'Rustling_leaves', 'Walk_and_footsteps', 'Chop', 'Knock', 'Wood', 'Water',
           'Helicopter', 'Fixed-wing_aircraft_and_airplane', 'Aircraft', 'Train',
           'Rail_transport', 'Car_passing_by', 'Idling', 'Heavy_engine_(low_frequency)',
           'Truck', 'Bus', 'Tractor', 'Motorcycle', 'Engine_starting',
           'Accelerating_and_revving_and_vroom', 'Medium_engine_(mid_frequency)',
           'Light_engine_(high_frequency)', 'Engine')


def fsd_items():
    """FSD50K eval clips selected by fsd50k_extract.py: an independent test corpus.
    Never used for training or threshold selection (src='fsd', fold=0, not ICE)."""
    out = []
    sel = DATA / 'fsd50k' / 'selected.csv'
    if not sel.exists():
        return out
    with open(sel) as f:
        for r in csv.DictReader(f):
            p = DATA / 'fsd50k' / 'audio' / (r['fname'] + '.wav')
            with wave.open(str(p)) as w:
                total = w.getnframes() / w.getframerate()
            if total < 3.0:
                continue
            labs = r['labels'].split(',')
            cls = next((k for k in FSD_KEY if k in labs), labs[0])
            for t in (0.0, 10.0)[:1 + int(total >= 20.0)]:
                out.append(dict(path=p, start=t, dur=min(10.0, total - t),
                                label=int(r['kind'] == 'engine'), kind=r['kind'],
                                cls='fsd_' + cls, group='fsd' + r['fname'], fold=0, src='fsd'))
    return out
