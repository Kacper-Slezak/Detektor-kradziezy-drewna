"""Build and cache device-domain ADC sessions for all evaluation items.

Each item is rendered at several microphone gains (RMS in ADC counts) so that level
dependence can be measured.  Tag 'v2' adds the soundsofchanges engine set (soc2) and
engine + background mixtures:
  * ESC-50 / soc2 engines + an ESC-50 nature/weather clip *from the same CV fold*,
  * ICE engines + synthetic gusty brown noise ("wind") or sparse clicks + pink noise
    ("rain"), so no real negative recording leaks into training through mixing.
Cache: $TG_DATA/cache/sessions_<tag>.npz
"""

import sys
import time

import numpy as np

import devsim

LEVELS = (40.0, 120.0, 360.0)        # ADC-count RMS: quiet / nominal / loud (~ -34/-25/-15 dBFS)
WEATHER = {'rain', 'wind', 'thunderstorm', 'insects', 'crickets', 'chirping_birds',
           'sea_waves', 'crackling_fire', 'water_drops', 'crow', 'frog'}
STORMY = {'rain', 'wind', 'thunderstorm'}


def synth_noise(n, rng, kind):
    """Synthetic 4 kHz background: 'wind' = gusty brown noise, 'rain' = pink + clicks,
    'hum' = mains hum (50 Hz +-0.2 %, random harmonic amplitudes, fixed for the session),
    'vent' = pink noise + one steady fan tone 80-250 Hz."""
    w = rng.normal(0, 1, n)
    t = np.arange(n) / 4000.0
    if kind == 'hum':
        f0 = 50.0 * (1 + rng.uniform(-0.002, 0.002))
        x = sum(rng.uniform(0.05, 1.0) * (0.75 ** k) * np.sin(2 * np.pi * f0 * (k + 1) * t + rng.uniform(0, 6.3))
                for k in range(39) if f0 * (k + 1) < 1990)
        return (x + 0.02 * w) / (np.std(x) + 1e-12)
    if kind == 'vent':
        X = np.fft.rfft(w)
        x = np.fft.irfft(X / np.sqrt(np.arange(len(X)) + 1.0), n=n)
        x = x / x.std() + rng.uniform(0.2, 1.0) * np.sin(2 * np.pi * rng.uniform(80, 250) * t)
        return x / x.std()
    if kind == 'wind':
        x = np.cumsum(w)
        x -= np.convolve(x, np.ones(400) / 400, 'same')          # remove drift (< ~10 Hz)
        g = np.cumsum(rng.normal(0, 1, n // 400 + 2))
        g = np.exp(0.8 * (g - g.mean()) / (g.std() + 1e-9))      # slow gusts, log-normal
        x *= np.interp(np.arange(n), np.arange(len(g)) * 400, g)
    else:
        X = np.fft.rfft(w)
        f = np.arange(len(X)) + 1.0
        x = np.fft.irfft(X / np.sqrt(f), n=n)
        clicks = (rng.random(n) < 0.004) * rng.normal(0, 8 * x.std(), n)
        x = x + np.convolve(clicks, np.exp(-np.arange(12) / 3.0), 'same')
    return x / (x.std() + 1e-12)


def all_items(tag):
    items = devsim.esc50_items() + devsim.ice_items() + devsim.long_items()
    if tag == 'v1':
        return items
    items += devsim.soc2_items()
    if tag in ('v4', 'v5'):
        items += devsim.fsd_items()             # v4: held-out corpus; v5: third CV corpus
    rng = np.random.default_rng(2026)
    esc = devsim.esc50_items()
    bg_by_fold = {f: [e for e in esc if e['cls'] in WEATHER and e['fold'] == f] for f in range(1, 6)}
    fsd_bg = [e for e in items if e['src'] == 'fsd' and e['label'] == 0 and e['kind'] == 'forest'
              and e['cls'] in ('fsd_Rain', 'fsd_Raindrop', 'fsd_Wind', 'fsd_Thunderstorm',
                               'fsd_Thunder', 'fsd_Stream', 'fsd_Insect', 'fsd_Cricket', 'fsd_Bird')]
    fsd_storm = [e for e in fsd_bg if e['cls'] in ('fsd_Rain', 'fsd_Raindrop', 'fsd_Wind',
                                                   'fsd_Thunderstorm', 'fsd_Thunder')]
    mixes = []
    for i, it in enumerate(items):
        if it['label'] != 1 or it['src'] not in ('esc50', 'soc2', 'ice', 'fsd'):
            continue
        snr = (0.0, 6.0)[i % 2]
        m = dict(it)
        m['kind'] = 'engine_mix'
        m['snr'] = snr
        if it['src'] == 'ice':
            m['bg'] = ('synth', ('wind', 'rain')[(i // 2) % 2])
        elif it['src'] == 'fsd':
            pool = [e for e in fsd_bg if tag != 'v5' or e['fold'] == it['fold']]
            b = pool[rng.integers(len(pool))]
            m['bg'] = (str(b['path']), b['cls'])
        else:
            b = bg_by_fold[it['fold']][rng.integers(len(bg_by_fold[it['fold']]))]
            m['bg'] = (str(b['path']), b['cls'])
        mixes.append(m)
        if tag not in ('v3', 'v4', 'v5'):
            continue
        # v3: a second, harder mixture with storm / rain / wind only (theft during bad weather)
        m2 = dict(it)
        m2['kind'] = 'engine_mix'
        m2['snr'] = (-3.0, 3.0)[(i // 2) % 2]
        if it['src'] == 'ice':
            m2['bg'] = ('synth', ('wind', 'rain')[i % 2])
        elif it['src'] == 'fsd':
            pool = [e for e in fsd_storm if tag != 'v5' or e['fold'] == it['fold']]
            b = pool[rng.integers(len(pool))]
            m2['bg'] = (str(b['path']), b['cls'])
        else:
            pool = [b for b in bg_by_fold[it['fold']] if b['cls'] in STORMY]
            b = pool[rng.integers(len(pool))]
            m2['bg'] = (str(b['path']), b['cls'])
        mixes.append(m2)
    extra = []
    if tag == 'v5':
        # corridor / mains: pure hum and ventilation sessions (negatives, CV folds 1-5)
        for j in range(250):
            k = 'hum' if j < 200 else 'vent'
            extra.append(dict(path='synth:' + k, start=0.0, dur=10.0, label=0, kind='forest',
                              cls='synth_' + k, group='synth%d' % j, fold=1 + j % 5, src='synth'))
        # mains hum under a quarter of the nature negatives and of the engines
        pool = [e for e in items if e['src'] in ('esc50', 'soc2', 'fsd') and e['kind'] in ('forest', 'engine')]
        for j, e in enumerate(pool):
            if j % 4 == 0:
                h = dict(e)
                h['hum'] = float(rng.uniform(6.0, 20.0))      # hum this many dB below the sound
                h['cls'] = e['cls'] + '+hum'
                extra.append(h)
    return items + mixes + extra


def render(it, level, seed):
    rng = np.random.default_rng(seed)
    if str(it['path']).startswith('synth:'):
        x = synth_noise(int(it['dur'] * 4000), rng, str(it['path'])[6:])
        return devsim.to_adc(x, level, rng)
    x = devsim.device_float(it['path'], it['start'], it['dur'], seed=seed)
    if 'bg' in it:
        src, k = it['bg']
        if src == 'synth':
            b = synth_noise(len(x), rng, k)
        else:
            b = devsim.device_float(src, 0.0, None, seed=seed + 1)
            if len(b) < len(x):
                b = np.tile(b, int(np.ceil(len(x) / len(b))))
            b = b[:len(x)]
        # SNR on active parts: engine RMS vs background RMS
        b = b * (np.sqrt(np.mean(x ** 2)) / (np.sqrt(np.mean(b ** 2)) + 1e-12)) * 10 ** (-it['snr'] / 20)
        x = x + b
    if 'hum' in it:
        x = x + synth_noise(len(x), rng, 'hum') * np.std(x) * 10 ** (-it['hum'] / 20)
    return devsim.to_adc(x, level, rng)


def build(tag='v2'):
    items = all_items(tag)
    out = devsim.DATA / 'cache' / ('sessions_%s.npz' % tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    codes = []
    meta = []
    t0 = time.time()
    for i, it in enumerate(items):
        for li, lv in enumerate(LEVELS):
            c = render(it, lv, seed=i * 7 + li)
            n = (len(c) // 4000) * 4000
            if n < 3 * 4000:            # burst needs >= 3 blocks for a 2-of-2 decision
                continue
            codes.append(c[:n].astype(np.int16))
            m = {k: str(v) for k, v in it.items() if k not in ('path', 'bg', 'snr', 'hum')}
            m['path'] = str(it['path'])
            m['level'] = str(lv)
            m['snr'] = str(it.get('snr', ''))
            m['bg'] = str(it['bg'][1]) if 'bg' in it else ''
            meta.append(m)
        if i % 500 == 0:
            print(i, len(items), '%.0fs' % (time.time() - t0), flush=True)
    lens = np.array([len(c) for c in codes])
    flat = np.concatenate(codes)
    keys = sorted(meta[0].keys())
    np.savez_compressed(out, flat=flat, lens=lens,
                        **{'m_' + k: np.array([m[k] for m in meta]) for k in keys})
    print('saved', out, len(codes), 'sessions')


def load(tag='v2'):
    z = np.load(devsim.DATA / 'cache' / ('sessions_%s.npz' % tag))
    flat, lens = z['flat'], z['lens']
    offs = np.concatenate([[0], np.cumsum(lens)])
    sessions = [flat[offs[i]:offs[i + 1]] for i in range(len(lens))]
    meta = {k[2:]: z[k] for k in z.files if k.startswith('m_')}
    return sessions, meta


if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else 'v2')
