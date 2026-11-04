"""Median/MAD threshold calibration; only use quiet physical sensor data."""
try:
    import ujson as json
except ImportError:
    import json

from tg_features import median


METRICS = ('audio_rms', 'audio_transient', 'vibration_rms',
           'vibration_peak', 'accel_dynamic_rms', 'accel_peak')


def calibrate(rows, floors):
    if len(rows) < 5:
        raise ValueError('Need >= 5 quiet windows')
    thresholds = {}
    for key in METRICS:
        values = [float(r[key]) for r in rows if r.get('valid', True)
                  and r.get(key) is not None]
        if not values:
            continue
        mid = median(values)
        mad = median([abs(v - mid) for v in values])
        factor = 8.0 if key in ('audio_rms', 'audio_transient') else 9.0
        thresholds[key] = max(float(floors[key]), mid + factor * 1.4826 * mad)
    return thresholds


def save(path, profile, thresholds):
    payload = {'version': 1, 'profile': profile,
               'method': 'quiet_baseline_median_mad',
               'thresholds': thresholds}
    with open(path, 'w') as f:
        json.dump(payload, f)


def load(path, profile):
    with open(path, 'r') as f:
        value = json.load(f)
    if value.get('version') != 1 or value.get('profile') != profile:
        raise ValueError('Calibration mismatch: recalibrate this hardware profile')
    return value['thresholds']
