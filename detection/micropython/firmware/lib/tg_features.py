"""Streaming features for low-memory Pycom LoPy.

2-s windows with a 1-s hop. Audio low-frequency fraction is approximated
by first-order IIR high/low-pass filters (not desktop NumPy FFT).
"""
import math


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
        # First-order low-pass coefficients for the nominal sample rate.
        self.a35 = 1.0 - math.exp(-2 * math.pi * 35.0 / rate_hz)
        self.a250 = 1.0 - math.exp(-2 * math.pi * 250.0 / rate_hz)
        self.frame_samples = max(1, int(rate_hz * frame_ms / 1000))

    def update(self, sample_normalized):
        x = sample_normalized
        if not self.initialized:
            self.lp35 = x
            self.lp250 = x
            self.initialized = True
        self.lp35 += self.a35 * (x - self.lp35)
        self.lp250 += self.a250 * (x - self.lp250)
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
        self.hp2 = 0.0
        self.bass2 = 0.0
        self.frame_energies = []
        self.frame_n = 0
        self.frame_hp2 = 0.0
        self.vibration = [] if has_vibration else None
        self.acceleration = [] if has_accel else None
        self.late_samples = 0
        self.total_samples = 0

    def add_audio(self, hp2, bass2, frame_size):
        self.audio_n += 1
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
    row = {'time_s': old.start_s, 'valid': True}
    n = old.total_samples + current.total_samples
    late = old.late_samples + current.late_samples
    row['late_samples'] = late
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
