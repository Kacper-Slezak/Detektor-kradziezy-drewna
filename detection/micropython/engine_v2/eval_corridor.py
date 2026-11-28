"""Demo-condition test: recordings played through a small loudspeaker in a corridor.

Chain (before the usual LoPy mic/ADC simulation):
  loudspeaker: 2nd-order high-pass at FC_SPK (small Bluetooth speaker ~150 Hz, laptop ~300 Hz)
               and 1st-order low-pass at 7 kHz
  corridor:    convolution with a synthetic room impulse response, exponentially decaying
               noise with RT60 = 1.2 s plus a direct path (direct-to-reverberant ~ +3 dB)
  background:  corridor noise at SNR_BG below the playback: ventilation (pink noise +
               steady fan tone 120 Hz) and mains hum (50 Hz and harmonics, exact frequency)
Negatives: the corridor background alone (ventilation, hum) and forest/weather clips played
through the same chain.  Uses the deployed model (model_v2.json) and the numpy features.

    python eval_corridor.py
"""

import json
import multiprocessing as mp
import os
from pathlib import Path

import numpy as np

import devsim
import features

HERE = Path(__file__).resolve().parent
FS_SIM = 16000


def butter2_hp(f, fc):
    w = f / fc
    return (w * w) / np.sqrt((1 - w * w) ** 2 + (np.sqrt(2) * w) ** 2 + 1e-30)


def speaker_room(x, fs, fc_spk, rng, rt60=1.2):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1.0 / fs)
    H = butter2_hp(f, fc_spk) / np.sqrt(1 + (f / 7000.0) ** 2)
    y = np.fft.irfft(X * H, n=len(x))
    n_ir = int(rt60 * fs)
    t = np.arange(n_ir) / fs
    ir = rng.normal(0, 1, n_ir) * np.exp(-6.91 * t / rt60)        # -60 dB at rt60
    ir[:int(0.003 * fs)] = 0.0
    ir *= 0.7 / np.sqrt(np.sum(ir ** 2))
    ir[0] = 1.0                                                     # direct path
    n = len(y) + n_ir
    Y = np.fft.irfft(np.fft.rfft(y, n) * np.fft.rfft(ir, n), n)[:len(y)]
    return Y


def corridor_noise(n, fs, rng, kind):
    t = np.arange(n) / fs
    if kind == 'vent':
        w = rng.normal(0, 1, n)
        X = np.fft.rfft(w)
        f = np.arange(len(X)) + 1.0
        x = np.fft.irfft(X / np.sqrt(f), n=n)
        x /= x.std()
        x += 0.5 * np.sin(2 * np.pi * 120.0 * t) + 0.2 * np.sin(2 * np.pi * 240.0 * t)
    else:  # mains hum, exact 50 Hz comb
        x = sum((0.6 ** k) * np.sin(2 * np.pi * 50.0 * (k + 1) * t + rng.uniform(0, 6.28)) for k in range(8))
        x += 0.05 * rng.normal(0, 1, n)
    return x / x.std()


def render(item, fc_spk, bg, snr_bg, seed, level=200.0):
    rng = np.random.default_rng(seed)
    if item is None:
        n = 10 * FS_SIM
        x = corridor_noise(n, FS_SIM, rng, bg)
    else:
        x, fs = devsim.read_wav(item['path'])
        a = int(item['start'] * fs)
        x = x[a:a + int(item['dur'] * fs)]
        # resample to FS_SIM by nearest index (signal is band-limited by the speaker anyway)
        idx = np.clip(np.round(np.arange(int(len(x) * FS_SIM / fs)) * fs / FS_SIM).astype(int), 0, len(x) - 1)
        x = x[idx]
        x = speaker_room(x, FS_SIM, fc_spk, rng)
        if bg:
            b = corridor_noise(len(x), FS_SIM, rng, bg)
            x = x + b * x.std() * 10 ** (-snr_bg / 20)
    x = devsim.highpass(x, FS_SIM)
    x4 = devsim.decimate_no_filter(x, FS_SIM, jitter_us=2.0, rng=rng)
    c = devsim.to_adc(x4, level, rng)
    return c[:len(c) // 4000 * 4000]


def logit(v, mm):
    H = len(mm['B1'])
    W1 = np.array(mm['W1']).reshape(H, -1) * mm['S1']
    W2 = np.array(mm['W2']) * mm['S2']
    z = np.clip((v - np.array(mm['MU'])) / np.array(mm['SD']), -6, 6)
    return float(np.maximum(0, W1 @ z + np.array(mm['B1'])) @ W2 + mm['B2'])


def job(args):
    item, fc, bg, snr, seed = args
    c = render(item, fc, bg, snr, seed)
    if len(c) < 3 * 4000:
        return None
    return features.session_features(c)


def main():
    model = json.loads((HERE / 'model_v2.json').read_text())
    mm = model['models'][0]
    th, ts = model['T_HIGH'], model['T_SUSP']
    rng = np.random.default_rng(7)
    # positives never trained on: external machine recordings + FSD50K engines
    ext = [it for it in devsim.long_items() if it['label'] == 1]
    fsd = devsim.fsd_items()
    fsd_e = [it for it in fsd if it['kind'] == 'engine']
    fsd_n = [it for it in fsd if it['kind'] == 'forest']
    fsd_e = [fsd_e[i] for i in rng.permutation(len(fsd_e))[:150]]
    fsd_n = [fsd_n[i] for i in rng.permutation(len(fsd_n))[:300]]
    truck = [dict(path=devsim.REPO_DET / 'python' / 'algorithm' / 'sample_audio' / 'forest-with-truck.wav',
                  start=s, dur=10.0, label=1, kind='engine', cls='demo_truck') for s in (25.0, 28.0, 30.0, 33.0, 36.0)]
    sets = [('maszyny zewnętrzne (soc)', ext, 1), ('ciężarówka z demo 25-46 s', truck, 1),
            ('FSD50K silniki', fsd_e, 1), ('FSD50K przyroda/pogoda', fsd_n, 0)]
    out = {}
    for fc in (0.0, 150.0, 300.0):
        for bg, snr in ((None, 0), ('vent', 15.0), ('hum', 15.0)):
            for name, items, lab in sets:
                if fc == 0.0 and bg is not None:
                    continue
                args = [(it, fc if fc else 1.0, bg, snr, 100 + i) for i, it in enumerate(items)]
                with mp.Pool(mp.cpu_count()) as p:
                    V = [v for v in p.map(job, args) if v is not None]
                L = np.array([logit(v, mm) for v in V])
                key = (fc, bg, name)
                out[key] = (len(L), float((L >= ts).mean()), float((L >= th).mean()))
                print('speaker HP %3.0f Hz  bg=%-5s  %-28s n=%3d  podejrzenie %5.1f%%  alarm od razu %5.1f%%'
                      % (fc, bg, name, len(L), 100 * out[key][1], 100 * out[key][2]), flush=True)
    for bg in ('vent', 'hum'):
        with mp.Pool(mp.cpu_count()) as p:
            V = p.map(job, [(None, 1.0, bg, 0, 900 + i) for i in range(40)])
        L = np.array([logit(v, mm) for v in V])
        print('corridor background only: %-5s n=40  podejrzenie %5.1f%%  alarm od razu %5.1f%%  median logit %.2f'
              % (bg, 100 * (L >= ts).mean(), 100 * (L >= th).mean(), np.median(L)), flush=True)


if __name__ == '__main__':
    main()
