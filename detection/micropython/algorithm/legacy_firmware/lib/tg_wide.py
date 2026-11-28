"""Optional wideband (250..900 Hz) engine texture, pure MicroPython DSP.

Enabled for a 4 kHz input: 2:1 decimation after a two-stage 900 Hz IIR
low-pass, 1024-point FFT of the latest ~0.51 s. This is complementary
positive evidence, NOT a 'wind/rain classifier'. The numerical thresholds are
EXPERIMENTAL and scores are not calibrated probabilities.

On original LoPy a software-sampled 4 kHz ADC with an FFT1024 is likely too
expensive. The 1 kHz fallback omits this evidence; timing failure suppresses
alarms. Do not claim that offline and original hardware have equal recall.
"""
import math
from array import array

N = 1024
RATE = 2000.0


class WideSpectrum:
    def __init__(self):
        self.twre = array('f', [math.cos(2 * math.pi * i / N) for i in range(N // 2)])
        self.twim = array('f', [-math.sin(2 * math.pi * i / N) for i in range(N // 2)])
        self.window = array('f', [0.5 - 0.5 * math.cos(2 * math.pi * i / (N - 1))
                                  for i in range(N)])
        reverse = []
        for i in range(N):
            j, flipped = i, 0
            for _ in range(10):
                flipped = (flipped << 1) | (j & 1)
                j >>= 1
            reverse.append(flipped)
        self.reverse = array('H', reverse)

    def analyze(self, samples):
        if samples is None or len(samples) != N:
            return empty_wide()
        re = array('f', [0.0]) * N
        im = array('f', [0.0]) * N
        mean = sum(samples) / N
        for j in range(N):
            re[self.reverse[j]] = (samples[j] - mean) * self.window[j]
        size = 2
        while size <= N:
            half, skip = size // 2, N // size
            for i in range(0, N, size):
                for j in range(half):
                    p, q = i + j, i + j + half
                    c, s = self.twre[j * skip], self.twim[j * skip]
                    a, b = c * re[q] - s * im[q], c * im[q] + s * re[q]
                    u, v = re[p], im[p]
                    re[p], im[p] = u + a, v + b
                    re[q], im[q] = u - a, v - b
            size *= 2
        # Comparable time-average power: FFT window normalization and per-bin
        # spectral correction cancel in relative spectral-band ratios below.
        power = [re[k] * re[k] + im[k] * im[k] for k in range(N // 2 + 1)]
        # Low band 35-230 Hz uses this same FFT, so the ratio uses identical
        # normalization/windowing, rather than incomparable filter outputs.
        low = sum(power[18:118]) + 1e-12
        high = sum(power[128:461]) + 1e-12
        ratio = high / low
        logs = 0.0
        for k in range(128, 461):
            logs += math.log(power[k] + 1e-12)
        flatness = math.exp(logs / 333) / (high / 333 + 1e-12)
        # Find sharp peaks of meaningful energy, not the noisy maximum bin.
        found = []
        for k in range(130, 460):
            if power[k] < power[k - 1] or power[k] <= power[k + 1]:
                continue
            floor = [power[k + d] for d in (-11, -9, -7, -5, 5, 7, 9, 11)]
            floor.sort()
            contrast = power[k] / (floor[4] + 1e-12)
            if contrast >= 7.0 and power[k] >= 0.004 * high:
                # Prefer well-separated prominent peaks; avoid counting the
                # side lobes of one narrow whistle as multiple independent tones.
                found.append((min(30.0, contrast), power[k], k))
        found.sort(reverse=True)
        selected = []
        for contrast, amplitude, bin_index in found:
            if all(abs(bin_index - prev) >= 5 for prev in selected):
                selected.append(bin_index)
                if len(selected) >= 8:
                    break
        peaks_hz = [round(k * RATE / N, 2) for k in selected]
        count = len(peaks_hz)
        # A broadband stochastic signal can produce several random local FFT
        # maxima. Demand spectral concentration beyond what random peaks alone
        # produce; otherwise white noise/rain gives frequent false positives.
        top = sorted(power[128:461], reverse=True)
        concentration = sum(top[:6]) / high
        strongest_share = top[0] / high
        # Positive engine signature: sustained wide-band *textured* sound
        # with several distinct tonal ridges; no categorical 'wind' veto.
        if (ratio < 0.8 or count < 2 or flatness > 0.70 or
                flatness < 0.10 or concentration < 0.115 or
                strongest_share < 0.028):
            score = 0.0
        else:
            def clip(v):
                return min(1.0, max(0.0, v))
            score = (0.43 * clip((ratio - 0.45) / 1.7)
                     + 0.40 * clip((count - 1.0) / 3.0)
                     + 0.17 * clip((0.70 - flatness) / 0.37))
        band_total = sum(power[118:461]) + 1e-9
        bands = []
        for i in range(12):
            lo = 118 + (343 * i) // 12
            hi = 118 + (343 * (i + 1)) // 12
            share = sum(power[lo:hi]) / band_total
            bands.append(round(math.log(1.0 + 128.0 * share), 5))
        return {'tiny_high_bands': tuple(bands),
                'audio_wide_score': round(score, 4),
                'audio_wide_ratio': round(min(ratio, 100.0), 4),
                'audio_wide_flatness': round(flatness, 4),
                'audio_wide_concentration': round(concentration, 4),
                'audio_wide_max_share': round(strongest_share, 4),
                'audio_wide_peak_count': count,
                'audio_wide_peaks_hz': peaks_hz}


def empty_wide():
    return {'tiny_high_bands': (0.0,) * 12,
            'audio_wide_score': 0.0, 'audio_wide_ratio': None,
            'audio_wide_flatness': None, 'audio_wide_concentration': None,
            'audio_wide_max_share': None, 'audio_wide_peak_count': 0,
            'audio_wide_peaks_hz': []}


_ANALYZER = None


def wide_features(samples):
    global _ANALYZER
    if _ANALYZER is None:
        _ANALYZER = WideSpectrum()
    return _ANALYZER.analyze(samples)
