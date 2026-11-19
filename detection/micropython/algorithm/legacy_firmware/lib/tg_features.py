"""Streaming features for low-memory Pycom LoPy.

2-s windows with a 1-s hop. Audio low-frequency fraction is approximated
by first-order IIR high/low-pass filters (not desktop NumPy FFT).
"""
import math
from array import array
from tg_engine import spectrum_features
from tg_wide import wide_features, empty_wide


def median(values):
    v = sorted(values)
    if not v:
        return 0.0
    i = len(v) // 2
    if len(v) % 2:
        return float(v[i])
    return (float(v[i - 1]) + float(v[i])) / 2.0


def centered_stats(values):
    if values is None or len(values) < 2:
        return None, None
    mean = sum(values) / len(values)
    squared = 0.0
    peak = 0.0
    for v in values:
        d = v - mean
        squared += d * d
        if abs(d) > peak:
            peak = abs(d)
    return math.sqrt(squared / len(values)), peak


def acceleration_stats(samples):
    if samples is None or len(samples) < 2:
        return None, None
    size = len(samples)
    means = [sum(point[axis] for point in samples) / size for axis in (0, 1, 2)]
    energy = 0.0
    peak = 0.0
    for x, y, z in samples:
        dx, dy, dz = x - means[0], y - means[1], z - means[2]
        d2 = dx * dx + dy * dy + dz * dz
        energy += d2
        if d2 > peak:
            peak = d2
    return math.sqrt(energy / size), math.sqrt(peak)


class IIRAudio:
    def __init__(self, rate_hz, frame_ms=50):
        self.lp35 = 0.0
        self.lp250 = 0.0
        self.initialized = False
        self.lp200a = 0.0
        self.lp200b = 0.0
        self.spectral = 0.0
        self.wide_lp1 = 0.0
        self.wide_lp2 = 0.0
        self.wide_spectral = 0.0
        self.sample_rate = rate_hz
        self.wide_a = 1.0 - math.exp(-2 * math.pi * 850.0 / rate_hz)
        self.a200 = 1.0 - math.exp(-2 * math.pi * 200.0 / rate_hz)
        # First-order low-pass coefficients for the nominal sample rate.
        self.a35 = 1.0 - math.exp(-2 * math.pi * 35.0 / rate_hz)
        self.a250 = 1.0 - math.exp(-2 * math.pi * 250.0 / rate_hz)
        self.frame_samples = max(1, int(rate_hz * frame_ms / 1000))

    def update(self, sample_normalized):
        x = sample_normalized
        if not self.initialized:
            self.lp35 = x
            self.lp250 = x
            self.lp200a = x
            self.lp200b = x
            self.wide_lp1 = x
            self.wide_lp2 = x
            self.initialized = True
        self.lp35 += self.a35 * (x - self.lp35)
        self.lp250 += self.a250 * (x - self.lp250)
        self.lp200a += self.a200 * (x - self.lp200a)
        self.lp200b += self.a200 * (self.lp200a - self.lp200b)
        self.spectral = self.lp200b - self.lp35
        if self.sample_rate == 4000:
            self.wide_lp1 += self.wide_a * (x - self.wide_lp1)
            self.wide_lp2 += self.wide_a * (self.wide_lp1 - self.wide_lp2)
            self.wide_spectral = self.wide_lp2
        high = x - self.lp35
        bass = self.lp250 - self.lp35
        return high * high, bass * bass


class Chunk:
    def __init__(self, start_s, has_audio=True, has_vibration=True, has_accel=True):
        self.start_s = float(start_s)
        self.has_audio = has_audio
        self.has_vibration = has_vibration
        self.has_accel = has_accel
        self.audio_n = 0
        self.audio_signal = array('f') if has_audio else None
        self.audio_spectral_cache = None
        self.audio_wide_cache = None
        self.wide_signal = array('f') if has_audio else None
        self.hp2 = 0.0
        self.bass2 = 0.0
        self.frame_energies = []
        self.frame_n = 0
        self.frame_hp2 = 0.0
        self.vibration = [] if has_vibration else None
        self.acceleration = [] if has_accel else None
        self.late_samples = 0
        self.start_gap_us = 0
        self.total_samples = 0

    def add_audio(self, hp2, bass2, frame_size, spectral_sample=None,
                  wide_sample=None, audio_rate=1000):
        self.audio_n += 1
        # The low FFT always sees 500 samples/s (same numerical bandwidth).
        low_div = audio_rate // 500
        if spectral_sample is not None and self.audio_n % low_div == 0:
            self.audio_signal.append(spectral_sample)
        if (wide_sample is not None and audio_rate == 4000 and
                self.audio_n > 1952 and self.audio_n % 2 == 0):
            # Only keep the final 0.512 s; no O(n) list trimming per sample.
            self.wide_signal.append(wide_sample)
        self.hp2 += hp2
        self.bass2 += bass2
        self.frame_hp2 += hp2
        self.frame_n += 1
        if self.frame_n == frame_size:
            self.frame_energies.append(self.frame_hp2 / self.frame_n)
            self.frame_n = 0
            self.frame_hp2 = 0.0


def build_window(old, current, max_late_ratio, audio_rate):
    chunks = (old, current)
    row = {'time_s': old.start_s, 'window_end_s': current.start_s + 1.0, 'valid': True}
    n = old.total_samples + current.total_samples
    late = old.late_samples + current.late_samples
    row['late_samples'] = late
    row['processing_gap_us'] = max(old.start_gap_us, current.start_gap_us)
    row['total_samples'] = n
    if n < int(2 * audio_rate * (1.0 - max_late_ratio)):
        row['valid'] = False
    if late > n * max_late_ratio:
        row['valid'] = False
    if old.has_audio and current.has_audio:
        samples = old.audio_n + current.audio_n
        energy = old.hp2 + current.hp2
        bass_energy = old.bass2 + current.bass2
        row['audio_rms'] = math.sqrt(energy / max(1, samples))
        row['audio_low_ratio'] = bass_energy / max(energy, 1e-15)
        for chunk in chunks:
            if chunk.audio_spectral_cache is None:
                chunk.audio_spectral_cache = spectrum_features(chunk.audio_signal)
            if chunk.audio_wide_cache is None:
                if audio_rate == 4000 and len(chunk.wide_signal) == 1024:
                    chunk.audio_wide_cache = wide_features(chunk.wide_signal)
                else:
                    chunk.audio_wide_cache = empty_wide()
        row.update(current.audio_spectral_cache)
        row.update(current.audio_wide_cache)
        # A 2-second feature map: previous and current 1-second spectra.
        # Always 48 floats, already bounded/log-compressed by FFT modules.
        row['tiny_spectral_bands'] = tuple(
            old.audio_spectral_cache['tiny_low_bands'] +
            old.audio_wide_cache['tiny_high_bands'] +
            current.audio_spectral_cache['tiny_low_bands'] +
            current.audio_wide_cache['tiny_high_bands'])
        frame_energy = old.frame_energies + current.frame_energies
        if frame_energy:
            levels = [math.sqrt(x) for x in frame_energy]
            row['audio_transient'] = max(levels) / max(median(levels), 1e-8)
        else:
            row['audio_transient'] = 0.0
    else:
        row['audio_rms'] = None
        row['audio_low_ratio'] = None
        row['audio_transient'] = None
        row.update(audio_engine_score=None, audio_harmonic_count=0,
                   audio_engine_pitch_hz=None, audio_tonality=None,
                   audio_flatness=None, audio_harmonic_score=None,
                   audio_ridge_score=None, audio_low_ridge_score=None,
                   audio_low_ridge_hz=None, audio_high_band_ratio=None,
                   audio_ridge_hz=None, audio_ridge_contrast=None,
                   audio_engine_method='none')
        row.update(empty_wide())
        row['tiny_spectral_bands'] = (0.0,) * 48
    if old.has_vibration and current.has_vibration:
        row['vibration_rms'], row['vibration_peak'] = centered_stats(
            old.vibration + current.vibration)
    else:
        row['vibration_rms'] = None
        row['vibration_peak'] = None
    if old.has_accel and current.has_accel:
        row['accel_dynamic_rms'], row['accel_peak'] = acceleration_stats(
            old.acceleration + current.acceleration)
    else:
        row['accel_dynamic_rms'] = None
        row['accel_peak'] = None
    return row
