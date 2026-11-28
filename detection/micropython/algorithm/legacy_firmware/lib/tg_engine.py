"""Small, explainable engine *candidate* detector for 1 kHz microphone audio.

Uses a 512-point radix-2 FFT of one second of 500 Hz anti-aliased audio.
Searches for *multiple* locally prominent, harmonically related spectral
peaks. Wind, rain and other broadband noise are not enumerated as classes.

This is a lightweight DSP heuristic, NOT an automotive fingerprint or a
calibrated probability; generators and other rotating machinery can match it.
No NumPy, allocations bounded by the FFT length, CPython/MicroPython compatible.
"""
import math
from array import array

FFT_N = 512
FFT_RATE = 500.0
FREQ_RESOLUTION = FFT_RATE / FFT_N
MIN_F0_BIN = 26  # 25.4 Hz
MAX_F0_BIN = 112  # 109.4 Hz
MAX_AUDIO_BIN = 235  # 229.5 Hz, below Nyquist / transition band


class EngineSpectrum:
    def __init__(self):
        self.cos = array('f', [math.cos(2 * math.pi * k / FFT_N)
                               for k in range(FFT_N // 2)])
        self.sin = array('f', [-math.sin(2 * math.pi * k / FFT_N)
                               for k in range(FFT_N // 2)])
        self.hann = array('f', [0.5 - 0.5 * math.cos(2 * math.pi * i / 499.0)
                                for i in range(500)])
        rev = []
        for i in range(FFT_N):
            j, flipped = i, 0
            for _ in range(9):
                flipped = (flipped << 1) | (j & 1)
                j >>= 1
            rev.append(flipped)
        self.reverse = array('H', rev)

    def _powers(self, samples):
        if len(samples) != 500:
            return None
        re = array('f', [0.0]) * FFT_N
        im = array('f', [0.0]) * FFT_N
        for i in range(500):
            re[self.reverse[i]] = samples[i] * self.hann[i]
        size = 2
        while size <= FFT_N:
            half = size // 2
            stride = FFT_N // size
            for start in range(0, FFT_N, size):
                for k in range(half):
                    j = start + k
                    pair = j + half
                    tw = stride * k
                    a = self.cos[tw]
                    b = self.sin[tw]
                    tr = a * re[pair] - b * im[pair]
                    ti = a * im[pair] + b * re[pair]
                    ur = re[j]
                    ui = im[j]
                    re[j] = ur + tr
                    im[j] = ui + ti
                    re[pair] = ur - tr
                    im[pair] = ui - ti
            size *= 2
        return [re[k] * re[k] + im[k] * im[k] for k in range(FFT_N // 2 + 1)]

    def analyze(self, samples):
        powers = self._powers(samples)
        if powers is None:
            return {'audio_engine_score': None, 'audio_harmonic_count': 0,
                    'audio_engine_pitch_hz': None, 'audio_tonality': None,
                    'audio_flatness': None, 'audio_harmonic_score': None,
                    'audio_ridge_score': None, 'audio_low_ridge_score': None,
                    'audio_low_ridge_hz': None, 'audio_high_band_ratio': None,
                    'audio_ridge_hz': None, 'audio_ridge_contrast': None,
                    'audio_engine_method': 'none',
                    'tiny_low_bands': (0.0,) * 12}
        eps = 1e-12
        total = sum(powers[26:MAX_AUDIO_BIN + 1]) + eps
        peak = max(powers[26:MAX_AUDIO_BIN + 1])
        flatlog = 0.0
        for p in powers[26:MAX_AUDIO_BIN + 1]:
            flatlog += math.log(p + eps)
        count_bins = MAX_AUDIO_BIN - 25
        flatness = math.exp(flatlog / count_bins) / (total / count_bins)
        tonality = peak / total

        # Prominence relative to *local* spectral background, not just volume.
        # A broad noisy band may have high energy but little local prominence.
        contrasts = [0.0] * (MAX_AUDIO_BIN + 1)
        for center in range(26, MAX_AUDIO_BIN + 1):
            local_peak = max(powers[max(26, center - 1):min(MAX_AUDIO_BIN + 1, center + 2)])
            near_noise = []
            for offset in (-11, -9, -7, -5, 5, 7, 9, 11):
                pos = center + offset
                if 26 <= pos <= MAX_AUDIO_BIN:
                    near_noise.append(powers[pos])
            if near_noise:
                near_noise.sort()
                noise = near_noise[len(near_noise) // 2] + eps
                contrasts[center] = local_peak / noise

        # A second engine signature: a sustained narrow mechanical ridge.
        # Vehicle engines sometimes have ONE strong order in-band because the
        # fundamental and other harmonics are masked by wind or microphone EQ.
        # A narrow peak alone is NOT sufficient: require substantial energy
        # in the high acoustic band and verify pitch continuity in tg_fusion.
        high_start = 112  # 109 Hz
        high_total = sum(powers[high_start:MAX_AUDIO_BIN + 1])
        high_ratio = high_total / total
        ridge_bin = max(range(high_start, MAX_AUDIO_BIN + 1),
                        key=lambda index: powers[index])
        ridge_contrast = contrasts[ridge_bin]
        ridge_score = (0.50 * min(1.0, max(0.0, (high_ratio - 0.25) / 0.30))
                       + 0.50 * min(1.0, max(0.0, (ridge_contrast - 5.0) / 20.0)))
        # A pure whistle/sine can produce a strong ridge but is NOT enough.
        # Broadband engine texture is expected alongside an order/ridge.
        # The harmonic path remains available for almost purely tonal motors.
        if tonality < 0.035:
            ridge_score *= tonality / 0.035
        if flatness < 0.08:
            ridge_score = 0.0

        # Additional low-band order tracker for diesel / heavy machinery.
        # The original >=109 Hz ridge misses strong, persistent 70-109 Hz
        # orders, which are common in low-revving engines. Restrict this path
        # to recordings with substantial higher-band texture so that a bare
        # low-frequency wind rumble cannot qualify.
        low_bin = max(range(72, 112), key=lambda index: powers[index])
        low_share = powers[low_bin] / total
        low_contrast = contrasts[low_bin]
        low_score = 0.0
        if (high_ratio > 0.29 and low_share > 0.075 and
                low_contrast > 10.0 and flatness > 0.08):
            def clamp01(v):
                return min(1.0, max(0.0, v))
            low_score = (0.45 * clamp01((high_ratio - 0.25) / 0.25)
                         + 0.25 * clamp01((low_contrast - 8.0) / 20.0)
                         + 0.30 * clamp01((low_share - 0.04) / 0.12))

        best = (0.0, 0, None, 0.0)
        for fundamental in range(MIN_F0_BIN, MAX_F0_BIN + 1):
            strong_count = 0
            strength = 0.0
            energy = 0.0
            high_harmonic = False
            harmonic = 1
            while harmonic * fundamental <= MAX_AUDIO_BIN and harmonic <= 6:
                k = harmonic * fundamental
                ratio = contrasts[k]
                if ratio >= 7.0:
                    strong_count += 1
                    strength += min(1.0, (ratio - 7.0) / 20.0)
                    energy += max(powers[max(26, k - 1):min(MAX_AUDIO_BIN + 1, k + 2)])
                    if harmonic >= 2:
                        high_harmonic = True
                harmonic += 1
            if strong_count < 2 or not high_harmonic:
                continue
            # Score emphasizes MULTIPLE peaks. A single tonal whistle cannot pass.
            score = (0.48 * min(1.0, strong_count / 3.0)
                     + 0.32 * min(1.0, strength / 1.5)
                     + 0.20 * min(1.0, energy / max(total * 0.30, eps)))
            # Avoid a tiny spectral line in otherwise very broadband noise.
            if tonality < 0.025:
                score *= tonality / 0.025
            if score > best[0]:
                best = (score, strong_count, fundamental * FREQ_RESOLUTION,
                        energy / total)

        chosen_score = max(best[0], ridge_score, low_score)
        # Other harmonics can be temporarily stronger than this same tracked
        # low order. Preserve the low ridge when its independent evidence is
        # close, instead of making the voted pitch jump between orders.
        use_low = (low_score >= 0.62 and
                   low_score >= max(best[0], ridge_score) - 0.12)
        use_ridge = not use_low and ridge_score > best[0]
        method = ('low_ridge' if use_low else
                  ('ridge' if use_ridge else
                   ('harmonics' if best[1] >= 2 else 'none')))
        pitch = (low_bin * FREQ_RESOLUTION if use_low else
                 (ridge_bin * FREQ_RESOLUTION if use_ridge else best[2]))
        # Report evidence for the SELECTED method, not a larger score from a
        # different peak that is discarded for pitch tracking.
        if use_low:
            chosen_score = low_score
        # 12 bounded log-energy shares, reusable by a learned student network.
        # FFT is already computed for the legacy detector, so this costs only
        # a few power sums. Relative normalization reduces gain dependence.
        band_total = sum(powers[26:236]) + 1e-9
        bands = []
        for i in range(12):
            lo = 26 + (210 * i) // 12
            hi = 26 + (210 * (i + 1)) // 12
            share = sum(powers[lo:hi]) / band_total
            bands.append(round(math.log(1.0 + 128.0 * share), 5))
        return {'tiny_low_bands': tuple(bands),
                'audio_engine_score': round(min(1.0, chosen_score), 4),
                'audio_harmonic_score': round(best[0], 4),
                'audio_ridge_score': round(ridge_score, 4),
                'audio_low_ridge_score': round(low_score, 4),
                'audio_low_ridge_hz': round(low_bin * FREQ_RESOLUTION, 2),
                'audio_high_band_ratio': round(high_ratio, 4),
                'audio_ridge_hz': round(ridge_bin * FREQ_RESOLUTION, 2),
                'audio_ridge_contrast': round(ridge_contrast, 2),
                'audio_engine_method': method,
                'audio_harmonic_count': best[1],
                'audio_engine_pitch_hz': round(pitch, 2) if pitch else None,
                'audio_tonality': round(tonality, 5),
                'audio_flatness': round(flatness, 5)}


_ANALYZER = None


def spectrum_features(samples):
    global _ANALYZER
    if _ANALYZER is None:
        _ANALYZER = EngineSpectrum()
    return _ANALYZER.analyze(samples)
