"""Optional 512-point feature probe for the original LoPy, outside the boot path."""

from array import array
import math

try:
    from tg_burst import BANDS, FEATURES, Spectrum, WINDOW_FRAMES, signed, summarize
except ImportError:
    from .tg_burst import BANDS, FEATURES, Spectrum, WINDOW_FRAMES, signed, summarize

# Half-open FFT bin ranges, about 45–350 Hz and 1,300–1,900 Hz at 4 kHz.
REGIONS = ((6, 45), (167, 244))
STRIDE = 6
FEATURE_WIDTHS = (32, 36, 40)


def peak(real, imag, start, stop):
    """Return 3-bin concentration, local shoulder contrast, and peak center."""
    prev2 = prev1 = total = best = 0.0
    center = start + 1
    for k in range(start, stop):
        p = real[k] * real[k] + imag[k] * imag[k]
        total += p
        triple = p + prev1 + prev2
        if k >= start + 2 and triple > best:
            best, center = triple, k - 1
        prev2, prev1 = prev1, p
    if total < 1e-3:
        return 0.0, 0.0, -1
    shoulder, count = 0.0, 0
    for k in range(max(start, center - 5), min(stop, center + 6)):
        if abs(k - center) >= 2:
            shoulder += real[k] * real[k] + imag[k] * imag[k]
            count += 1
    concentration = math.log((best + 1e-6) / (total + 1e-6))
    contrast = math.log((best / 3 + 1e-6) / (shoulder / count + 1e-6))
    return max(-9.0, concentration), max(-2.0, min(8.0, contrast)), center


def summarize_peaks(ring, cursor, out):
    """Aggregate chronological peaks, avoiding adjacency across the ring boundary."""
    for region in range(2):
        column = 3 * region
        concentration = contrast = strongest_pair = stable = 0.0
        previous_center, previous_contrast = -1, 0.0
        for i in range(WINDOW_FRAMES):
            offset = ((cursor + i) % WINDOW_FRAMES) * STRIDE + column
            share, local, center = ring[offset], ring[offset + 1], ring[offset + 2]
            concentration += share
            contrast += local
            if previous_center >= 0 and center >= 0 and abs(center - previous_center) <= 2:
                stable += 1
                strongest_pair = max(strongest_pair, min(previous_contrast, local))
            previous_center, previous_contrast = center, local
        out[FEATURES + 2 * region] = concentration / WINDOW_FRAMES
        out[FEATURES + 2 * region + 1] = contrast / WINDOW_FRAMES
        out[FEATURES + 4 + 2 * region] = stable / (WINDOW_FRAMES - 1)
        out[FEATURES + 5 + 2 * region] = strongest_pair


class SpectralProbe:
    """Shared FFT and bounded rings. Caller supplies valid quarter-second blocks."""

    def __init__(self):
        self.spectrum = Spectrum(512)
        self.bands = array('f', [0]) * (WINDOW_FRAMES * (BANDS + 1))
        self.peaks = array('f', [0]) * (WINDOW_FRAMES * STRIDE)
        self.features = array('f', [0]) * FEATURE_WIDTHS[-1]
        self.cursor = self.used = self.phase = 0

    def push(self, valid=True):
        if not valid:
            self.used = self.phase = self.cursor = 0
            return False
        self.spectrum.extract(self.bands, self.cursor * (BANDS + 1))
        for i, (start, stop) in enumerate(REGIONS):
            share, contrast, center = peak(self.spectrum.real, self.spectrum.imag, start, stop)
            offset = self.cursor * STRIDE + 3 * i
            self.peaks[offset] = share
            self.peaks[offset + 1] = contrast
            self.peaks[offset + 2] = center
        self.cursor = (self.cursor + 1) % WINDOW_FRAMES
        self.used = min(WINDOW_FRAMES, self.used + 1)
        self.phase = (self.phase + 1) % 4
        if self.used != WINDOW_FRAMES or self.phase:
            return False
        summarize(self.bands, self.features)
        summarize_peaks(self.peaks, self.cursor, self.features)
        return True


class LinearProbe:
    """Portable int8 logistic head for benchmark exports."""

    def __init__(self, model):
        if (model.FEATURE_VERSION != 2 or model.INPUTS not in FEATURE_WIDTHS
                or len(model.WEIGHTS) != model.INPUTS or len(model.MEAN) != model.INPUTS
                or len(model.INVERSE_STD) != model.INPUTS):
            raise ValueError('Incompatible spectral probe model')
        self.model = model

    def score(self, values):
        model = self.model
        dot = 0.0
        for i in range(model.INPUTS):
            value = (values[i] - model.MEAN[i]) * model.INVERSE_STD[i]
            dot += max(-6.0, min(6.0, value)) * signed(model.WEIGHTS[i])
        z = dot * model.SCALE + model.BIAS
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))
