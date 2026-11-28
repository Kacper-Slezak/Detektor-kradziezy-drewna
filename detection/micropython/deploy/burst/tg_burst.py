"""Shared burst geometry, spectral features, and quantized inference."""

from array import array
import math

RATE = 4000
FRAMES_PER_SECOND = 4
WINDOW_FRAMES = 8
BAND_EDGES = (30, 65, 100, 145, 200, 265, 345, 440, 550,
              680, 825, 990, 1180, 1390, 1630, 1900)
BANDS = len(BAND_EDGES) - 1
FEATURES = 2 * BANDS + 2


def band_bins(size):
    return tuple((hz * size + RATE - 1) // RATE for hz in BAND_EDGES)


class Spectrum:
    """One reused block of PCM16 and an in-place radix-2 FFT."""

    def __init__(self, size):
        if size not in (256, 512):
            raise ValueError('Expected 256 or 512 PCM16 samples per block')
        self.size = size
        self.pcm = array('h', [0]) * size
        self.real = array('f', [0]) * size
        self.imag = array('f', [0]) * size
        self.cos = array('f', [0]) * (size // 2)
        self.sin = array('f', [0]) * (size // 2)
        self.hann = array('f', [0]) * size
        self.reverse = array('H', [0]) * size
        for k in range(size // 2):
            angle = 2 * math.pi * k / size
            self.cos[k], self.sin[k] = math.cos(angle), -math.sin(angle)
        for i in range(size):
            self.hann[i] = 0.5 - 0.5 * math.cos(2 * math.pi * i / (size - 1))
        for i in range(1, size):
            self.reverse[i] = (self.reverse[i >> 1] >> 1) | ((i & 1) * (size // 2))
        self.bins = band_bins(size)

    def extract(self, out, offset):
        size = self.size
        mean = sum(self.pcm) / size
        rms_squared = 0.0
        real, imag = self.real, self.imag
        for i in range(size):
            value = self.pcm[i] - mean
            rms_squared += value * value
            j = self.reverse[i]
            real[j] = value * self.hann[i]
            imag[j] = 0.0

        width = 2
        while width <= size:
            half = width // 2
            stride = size // width
            for start in range(0, size, width):
                for k in range(half):
                    i = start + k
                    j = i + half
                    twiddle = k * stride
                    c, s = self.cos[twiddle], self.sin[twiddle]
                    u, v = real[j], imag[j]
                    r = c * u - s * v
                    q = s * u + c * v
                    real[j] = real[i] - r
                    imag[j] = imag[i] - q
                    real[i] += r
                    imag[i] += q
            width *= 2

        center = 0.0
        for band in range(BANDS):
            first, end = self.bins[band], self.bins[band + 1]
            power = 0.0
            for k in range(first, end):
                power += real[k] * real[k] + imag[k] * imag[k]
            value = math.log(power / (end - first) + 1e-6)
            center += value
            out[offset + band] = value
        center /= BANDS
        for band in range(BANDS):
            index = offset + band
            out[index] = max(-10.0, min(10.0, out[index] - center))
        out[offset + BANDS] = math.log(math.sqrt(rms_squared / size) / 32768.0 + 1e-7)


def summarize(frames, out):
    """Per-band temporal mean/std, log-RMS std and log-RMS mean."""
    for channel in range(BANDS + 1):
        total = 0.0
        squares = 0.0
        for frame in range(WINDOW_FRAMES):
            value = frames[frame * (BANDS + 1) + channel]
            total += value
            squares += value * value
        mean = total / WINDOW_FRAMES
        std = math.sqrt(max(0.0, squares / WINDOW_FRAMES - mean * mean))
        if channel < BANDS:
            out[channel] = mean
            out[BANDS + channel] = std
        else:
            out[2 * BANDS] = std
            out[2 * BANDS + 1] = mean


def signed(value):
    return value if value < 128 else value - 256


class Classifier:
    """Linear or one-hidden-layer ReLU with symmetric signed int8 weights."""

    def __init__(self, model):
        self.model = model
        self.inputs = model.INPUTS
        self.hidden = model.HIDDEN
        if (model.FEATURE_VERSION != 1 or model.RATE != RATE
                or self.inputs not in (FEATURES - 1, FEATURES)
                or self.hidden not in (0, 16)
                or model.BURST_SAMPLES not in (256, 512)
                or not 0 < model.THRESHOLD < 1
                or not 1 <= model.REQUIRED <= model.SPAN <= 15
                or len(model.MEAN) != self.inputs or len(model.INVERSE_STD) != self.inputs
                or len(model.SCALES) != (2 if self.hidden else 1)
                or len(model.BIASES) != self.hidden + 1
                or len(model.WEIGHTS) != self.inputs * (self.hidden or 1) + self.hidden):
            raise ValueError('Incompatible burst model')
        self.values = array('f', [0]) * self.inputs

    def score(self, features):
        m = self.model
        values = self.values
        for i in range(self.inputs):
            value = (features[i] - m.MEAN[i]) * m.INVERSE_STD[i]
            values[i] = max(-6.0, min(6.0, value))
        weights = m.WEIGHTS
        logit = 0.0
        for unit in range(self.hidden or 1):
            offset = unit * self.inputs
            acc = 0.0
            for i in range(self.inputs):
                acc += values[i] * signed(weights[offset + i])
            value = acc * m.SCALES[0] + m.BIASES[unit]
            if self.hidden:
                logit += max(0.0, value) * signed(weights[self.hidden * self.inputs + unit])
            else:
                logit = value
        if self.hidden:
            logit = logit * m.SCALES[1] + m.BIASES[-1]
        return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, logit))))


class Votes:
    """Bounded rolling votes. Invalid audio clears accumulated evidence."""

    def __init__(self, threshold, span, required):
        self.threshold = threshold
        self.history = bytearray(span)
        self.required = required
        self.reset()

    def reset(self):
        self.used = 0
        self.cursor = 0
        self.count = 0

    def step(self, score):
        if score is None:
            self.reset()
            return False
        hit = int(score >= self.threshold)
        if self.used == len(self.history):
            self.count -= self.history[self.cursor]
        else:
            self.used += 1
        self.count += hit
        self.history[self.cursor] = hit
        self.cursor = (self.cursor + 1) % len(self.history)
        return self.used == len(self.history) and self.count >= self.required
