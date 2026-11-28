"""Memory-bounded streaming ADC audio detector for Pycom LoPy 1.0 firmware.

Adapts the trained Timber Guard v4.6 wideband CNN (and optional burst MLP)
to the streaming 1-second ADC block interface provided by external firmware
(`nagraj_audio()` in `firmware/main4.py`).

Design constraints (Pycom LoPy 1.0, ESP32 @ 160 MHz, MicroPython v1.11):
- Pure MicroPython / CPython standard library only (array, math, ubinascii, gc).
- Lazy backend imports: Burst MLP does not load v4.6 code, and v4.6 CNN does
  not require `tg_burst.py` or `tg_temporal_v46.py` on flash.
- Never retains references to the caller's reusable 8000-byte bytearray.
- Decodes one sub-frame at a time (1000 samples for v4.6, 512 for burst).
- Fuses v4.6 3x3 Conv2D + ReLU + frequency-group pooling (zero conv tensor)
  and supports streaming dense INT8 weights directly from a binary flash file
  (`WEIGHT_BIN`) in 201-byte rows to save ~30 KB RAM without altering weights.
"""

from array import array
import math

try:
    import ubinascii as binascii
except ImportError:
    import binascii

# Audio & v4.6 geometry constants (inlined to avoid extra module imports on LoPy)
SAMPLE_RATE = 4000
FFT_N = 1024
FRAME_N = 1000
N_BANDS = 24
N_FRAMES = 8
BAND_MIN_HZ = 35.0
BAND_MAX_HZ = 1900.0

# Audio block contract matching external firmware/main4.py::nagraj_audio()
BLOCK_SAMPLES = SAMPLE_RATE       # 4000 samples (1.0 s at 4000 Hz)
BYTES_PER_SAMPLE = 2              # unsigned 16-bit little-endian
BLOCK_BYTES = BLOCK_SAMPLES * BYTES_PER_SAMPLE  # 8000 bytes
ADC_BITS = 12
ADC_MAX = (1 << ADC_BITS) - 1     # 4095
FRAMES_PER_BLOCK = 4              # 4 x 250 ms frames per 1-second block

# V2 protocol constants (aligned with firmware/main4.py; source_bits configurable)
EVENT_TYPE_NONE = 0
EVENT_TYPE_THEFT = 1              # Matches firmware/main4.py::analizuj_sygnaly()
SOURCE_BIT_MIC = 0x01             # Bit 0: microphone / audio detection
SOURCE_BIT_VIB = 0x02             # Bit 1: vibration wake-up metadata


def _signed_i8(b):
    return b - 256 if b > 127 else b


def _sparse_bands():
    """24 triangular mel filters over 35..1900 Hz matching tg_temporal_v46."""
    low = 1127.0 * math.log(1.0 + BAND_MIN_HZ / 700.0)
    high = 1127.0 * math.log(1.0 + BAND_MAX_HZ / 700.0)
    hz = [
        700.0 * (math.exp((low + (high - low) * i / (N_BANDS + 1)) / 1127.0) - 1.0)
        for i in range(N_BANDS + 2)
    ]
    out = []
    for i in range(N_BANDS):
        left = hz[i]
        center = hz[i + 1]
        right = hz[i + 2]
        ids = []
        weights = []
        for k in range(1, FFT_N // 2 + 1):
            f = SAMPLE_RATE * k / float(FFT_N)
            if left < f < right:
                w = (f - left) / (center - left) if f <= center else (right - f) / (right - center)
                if w > 0.0:
                    ids.append(k)
                    weights.append(w)
        s = sum(weights)
        if s <= 0.0:
            raise ValueError('Empty mel filter at band %d' % i)
        out.append((array('H', ids), array('f', (w / s for w in weights))))
    return tuple(out)


def decode_adc_frame_into(raw_bytes, sample_offset, count, out_pcm):
    """Decode `count` uint16 LE 12-bit ADC samples into `out_pcm` (array('h')).

    Maps 12-bit ADC codes 0..4095 to signed PCM16 via `(raw << 4) - 32768`,
    matching `tg_burst_device.capture()`. Out-of-range codes are clamped to
    0..4095. Returns the number of rail-clipped samples (`raw == 0` or `>= 4095`).
    """
    clipped = 0
    byte_idx = sample_offset * 2
    for i in range(count):
        raw = raw_bytes[byte_idx] | (raw_bytes[byte_idx + 1] << 8)
        byte_idx += 2
        if raw <= 0:
            raw = 0
            clipped += 1
        elif raw >= ADC_MAX:
            raw = ADC_MAX
            clipped += 1
        out_pcm[i] = (raw << 4) - 32768
    return clipped


def decode_adc_u16_le(raw_bytes, out=None):
    """Decode an entire uint16 LE 12-bit ADC buffer into signed PCM16 array('h').

    Primarily a helper for tests and diagnostics; `Detector.process()` decodes
    one sub-frame at a time to avoid allocating an 8 KB decoded buffer.
    """
    n_bytes = len(raw_bytes)
    if n_bytes % 2 != 0:
        raise ValueError('ADC buffer length must be even, got %d bytes' % n_bytes)
    n_samples = n_bytes // 2
    if out is None:
        out = array('h', [0]) * n_samples
    elif len(out) < n_samples:
        raise ValueError('Output array too small for %d samples' % n_samples)
    decode_adc_frame_into(raw_bytes, 0, n_samples, out)
    return out


def _load_default_model():
    """Attempt to import an installed trained model (v4.6 bin, v4.6, or burst)."""
    for name in ('tg_model_v46_bin', 'tg_model_v46', 'tg_model_burst'):
        try:
            return __import__(name)
        except ImportError:
            pass
    try:
        from . import tg_model_burst as model
        return model
    except ImportError:
        raise ImportError(
            'No trained model found. Pass `model=` explicitly or place '
            '`tg_model_v46_bin.py`, `tg_model_v46.py`, or `tg_model_burst.py` on sys.path.'
        )


def _resolve_weight_bin_path(model):
    """Resolve binary weight path relative to model module or /flash."""
    rel = model.WEIGHT_BIN
    # Try exact path first (works for absolute /flash/... or CWD-relative paths)
    for candidate in (rel, '/flash/tg_demo/' + rel, '/flash/lib/' + rel, '/flash/' + rel):
        try:
            with open(candidate, 'rb'):
                return candidate
        except OSError:
            pass
    # Fallback: resolve next to model.__file__ (CPython / desktop tests)
    mod_file = getattr(model, '__file__', None)
    if mod_file:
        norm = mod_file.replace('\\', '/')
        if '/' in norm:
            base = norm.rsplit('/', 1)[0]
            candidate = base + '/' + rel
            try:
                with open(candidate, 'rb'):
                    return candidate
            except OSError:
                pass
    raise OSError('Cannot find binary weight file: %s' % rel)


class _StreamingMelFFT:
    """In-place 1024-pt radix-2 FFT + 24 mel bands with compact RAM footprint.

    Uses half-Hann symmetry (500 floats instead of 1000) and overwrites `re`
    in-place with the power spectrum (zero Python list allocations per frame).
    """

    def __init__(self):
        half_fft = FFT_N // 2
        self.cos = array('f', (math.cos(2.0 * math.pi * k / FFT_N) for k in range(half_fft)))
        self.sin = array('f', (-math.sin(2.0 * math.pi * k / FFT_N) for k in range(half_fft)))
        half_frame = FRAME_N // 2
        self.hann_half = array(
            'f',
            (0.5 - 0.5 * math.cos(2.0 * math.pi * i / (FRAME_N - 1)) for i in range(half_frame)),
        )
        rev = array('H', [0]) * FFT_N
        for i in range(FFT_N):
            n = i
            j = 0
            for _ in range(10):
                j = (j << 1) | (n & 1)
                n >>= 1
            rev[i] = j
        self.reverse = rev
        self.bands = _sparse_bands()
        self.re = array('f', [0.0]) * FFT_N
        self.im = array('f', [0.0]) * FFT_N

    def extract_frame(self, pcm_frame, mel_out, mel_offset):
        """Extract 24 log-mel values into `mel_out[mel_offset:]`.

        Returns `(log_rms, norm_rms, crest_factor)` for the 1000-sample frame.
        """
        mean = 0.0
        for i in range(FRAME_N):
            mean += pcm_frame[i]
        mean /= float(FRAME_N)

        re = self.re
        im = self.im
        for i in range(FFT_N):
            re[i] = 0.0
            im[i] = 0.0

        msq = 0.0
        peak = 0.0
        rev = self.reverse
        hann_half = self.hann_half
        half_frame = FRAME_N // 2
        last_idx = FRAME_N - 1
        for i in range(FRAME_N):
            v = float(pcm_frame[i]) - mean
            av = -v if v < 0.0 else v
            if av > peak:
                peak = av
            msq += v * v
            w = hann_half[i] if i < half_frame else hann_half[last_idx - i]
            re[rev[i]] = v * w

        # In-place radix-2 Cooley-Tukey FFT
        n = 2
        cos_t = self.cos
        sin_t = self.sin
        while n <= FFT_N:
            half = n // 2
            stride = FFT_N // n
            for start in range(0, FFT_N, n):
                for k in range(half):
                    i = start + k
                    j = i + half
                    tw = stride * k
                    c = cos_t[tw]
                    s = sin_t[tw]
                    rj = re[j]
                    ij = im[j]
                    r = c * rj - s * ij
                    q = c * ij + s * rj
                    u = re[i]
                    v = im[i]
                    re[i] = u + r
                    im[i] = v + q
                    re[j] = u - r
                    im[j] = v - q
            n *= 2

        # Overwrite re[0..FFT_N//2] with power spectrum in-place (zero allocation)
        for k in range(FFT_N // 2 + 1):
            rk = re[k]
            ik = im[k]
            re[k] = rk * rk + ik * ik

        for b_idx in range(N_BANDS):
            ids, weights = self.bands[b_idx]
            energy = 0.0
            for m in range(len(ids)):
                energy += re[ids[m]] * weights[m]
            mel_out[mel_offset + b_idx] = math.log(energy + 1e-6)

        rms_pcm = math.sqrt(msq / float(FRAME_N))
        norm_rms = rms_pcm / 32768.0
        crest = peak / (rms_pcm + 1e-6)
        return math.log(norm_rms + 1e-7), norm_rms, crest


class _V46Backend:
    """Memory-optimized v4.6 wideband CNN backend with fused Conv2D+ReLU+Pool.

    Supports both in-RAM `WEIGHT_B64` models and flash-streamed `WEIGHT_BIN`
    models (where the 12,864-byte dense matrix is read in 201-byte rows).
    """

    model_type = 'tiny_cnn_wide_v46'

    def __init__(self, model):
        if getattr(model, 'MODEL_TYPE', None) != 'tiny_cnn_wide_v46' or model.RATE != SAMPLE_RATE:
            raise ValueError('Expected v4.6 model at 4000 Hz')
        self.model = model
        self.channels = int(model.CONV_CHANNELS)
        self.hidden_n = int(model.HIDDEN)
        self.threshold = float(model.THRESHOLD)
        self.pool_size = 12 * self.channels + 9

        self._weight_bin_path = None
        self._wd_offset = 0
        self._wd_row_buf = None
        self.wd = None

        if hasattr(model, 'WEIGHT_BIN'):
            path = _resolve_weight_bin_path(model)
            wc_len = 9 * self.channels
            wd_len = self.pool_size * self.hidden_n
            wo_len = self.hidden_n
            with open(path, 'rb') as f:
                wc = f.read(wc_len)
                f.seek(wc_len + wd_len)
                wo = f.read(wo_len)
            if len(wc) != wc_len or len(wo) != wo_len:
                raise ValueError('Corrupt binary v4.6 weight file')
            self.wc = wc
            self.wo = wo
            self._weight_bin_path = path
            self._wd_offset = wc_len
            self._wd_row_buf = bytearray(self.pool_size)
        else:
            cached = getattr(model, '_cached_weights', None)
            if cached is None:
                cached = tuple(binascii.a2b_base64(blob) for blob in model.WEIGHT_B64)
                model._cached_weights = cached
            wc, wd, wo = cached
            if (len(wc) != 9 * self.channels
                    or len(wd) != self.pool_size * self.hidden_n
                    or len(wo) != self.hidden_n):
                raise ValueError('Corrupt v4.6 model weights')
            self.wc = wc
            self.wd = wd
            self.wo = wo

        self.fft = _StreamingMelFFT()
        self.frame_pcm = array('h', [0]) * FRAME_N
        self.prev_mel = array('f', [0.0]) * (FRAMES_PER_BLOCK * N_BANDS)
        self.prev_rms = array('f', [0.0]) * FRAMES_PER_BLOCK
        self.curr_mel = array('f', [0.0]) * (FRAMES_PER_BLOCK * N_BANDS)
        self.curr_rms = array('f', [0.0]) * FRAMES_PER_BLOCK
        self.x_norm = array('f', [0.0]) * (N_FRAMES * N_BANDS)
        self.env_norm = array('f', [0.0]) * 9
        self.pooled = array('f', [0.0]) * self.pool_size
        self.hidden = array('f', [0.0]) * self.hidden_n
        self.has_prev = False

    def reset(self):
        self.has_prev = False

    def clear_window(self):
        self.has_prev = False

    def _score_fused(self):
        """Normalize 8x24 + 9 features and run fused Conv2D+ReLU+Pool+MLP."""
        m = self.model
        half_mel = FRAMES_PER_BLOCK * N_BANDS

        mel_sum = 0.0
        for i in range(half_mel):
            mel_sum += self.prev_mel[i] + self.curr_mel[i]
        mel_center = mel_sum / float(N_FRAMES * N_BANDS)

        x = self.x_norm
        mean_f = m.MEAN
        inv_std_f = m.INV_STD
        for t in range(FRAMES_PER_BLOCK):
            base = t * N_BANDS
            for f in range(N_BANDS):
                v = self.prev_mel[base + f] - mel_center
                if v < -10.0:
                    v = -10.0
                elif v > 10.0:
                    v = 10.0
                z = (v - mean_f[f]) * inv_std_f[f]
                x[base + f] = -6.0 if z < -6.0 else (6.0 if z > 6.0 else z)

        for t in range(FRAMES_PER_BLOCK):
            src_base = t * N_BANDS
            dst_base = (t + FRAMES_PER_BLOCK) * N_BANDS
            for f in range(N_BANDS):
                v = self.curr_mel[src_base + f] - mel_center
                if v < -10.0:
                    v = -10.0
                elif v > 10.0:
                    v = 10.0
                z = (v - mean_f[f]) * inv_std_f[f]
                x[dst_base + f] = -6.0 if z < -6.0 else (6.0 if z > 6.0 else z)

        rms_sum = 0.0
        for i in range(FRAMES_PER_BLOCK):
            rms_sum += self.prev_rms[i] + self.curr_rms[i]
        rms_mean = rms_sum / float(N_FRAMES)

        env = self.env_norm
        e_mean = m.E_MEAN
        e_inv_std = m.E_INV_STD
        for i in range(FRAMES_PER_BLOCK):
            v = self.prev_rms[i] - rms_mean
            if v < -4.0:
                v = -4.0
            elif v > 4.0:
                v = 4.0
            z = (v - e_mean[i]) * e_inv_std[i]
            env[i] = -6.0 if z < -6.0 else (6.0 if z > 6.0 else z)
        for i in range(FRAMES_PER_BLOCK):
            v = self.curr_rms[i] - rms_mean
            if v < -4.0:
                v = -4.0
            elif v > 4.0:
                v = 4.0
            idx = i + FRAMES_PER_BLOCK
            z = (v - e_mean[idx]) * e_inv_std[idx]
            env[idx] = -6.0 if z < -6.0 else (6.0 if z > 6.0 else z)
        z_abs = (rms_mean - e_mean[8]) * e_inv_std[8]
        env[8] = -6.0 if z_abs < -6.0 else (6.0 if z_abs > 6.0 else z_abs)

        # Fused 3x3 Conv2D + ReLU + 6 frequency-group mean/max pooling (zero conv tensor)
        channels = self.channels
        wc = self.wc
        s0 = m.SCALES[0]
        b0 = m.BIASES[0]
        pooled = self.pooled

        for group in range(6):
            f_start = group * 4
            f_end = f_start + 4
            for c in range(channels):
                total = 0.0
                maximum = 0.0
                bc = b0[c]
                for t in range(N_FRAMES):
                    for f in range(f_start, f_end):
                        z = bc
                        for dt in (-1, 0, 1):
                            tt = t + dt
                            if tt < 0 or tt >= N_FRAMES:
                                continue
                            row_base = tt * N_BANDS
                            k_row = (dt + 1) * 3
                            for df in (-1, 0, 1):
                                ff = f + df
                                if ff < 0 or ff >= N_BANDS:
                                    continue
                                k = (k_row + (df + 1)) * channels + c
                                z += x[row_base + ff] * (_signed_i8(wc[k]) * s0)
                        if z > 0.0:
                            total += z
                            if z > maximum:
                                maximum = z
                pooled[group * channels + c] = total / 32.0
                pooled[(6 + group) * channels + c] = maximum

        base_env = 12 * channels
        for i in range(9):
            pooled[base_env + i] = env[i]

        # Dense hidden layer (ReLU): stream transposed rows from flash or read RAM
        h = self.hidden
        s1 = m.SCALES[1]
        b1 = m.BIASES[1]
        size = self.pool_size
        hidden_n = self.hidden_n

        if self._weight_bin_path is not None:
            row_buf = self._wd_row_buf
            with open(self._weight_bin_path, 'rb') as wf:
                wf.seek(self._wd_offset)
                for j in range(hidden_n):
                    n_read = wf.readinto(row_buf)
                    if n_read != size:
                        raise ValueError('Short read on binary dense weights')
                    z = b1[j]
                    for i in range(size):
                        z += pooled[i] * (_signed_i8(row_buf[i]) * s1)
                    h[j] = z if z > 0.0 else 0.0
        else:
            wd = self.wd
            for j in range(hidden_n):
                z = b1[j]
                for i in range(size):
                    z += pooled[i] * (_signed_i8(wd[i * hidden_n + j]) * s1)
                h[j] = z if z > 0.0 else 0.0

        # Output sigmoid
        wo = self.wo
        s2 = m.SCALES[2]
        z = m.BIASES[2][0]
        for i in range(hidden_n):
            z += h[i] * (_signed_i8(wo[i]) * s2)
        if z < -40.0:
            z = -40.0
        elif z > 40.0:
            z = 40.0
        return 1.0 / (1.0 + math.exp(-z))

    def process_block(self, raw_bytes):
        """Process one 8000-byte block. Returns (score_or_None, block_stats)."""
        clipped_total = 0
        rms_sq_sum = 0.0
        max_frame_rms = 0.0
        max_crest = 0.0
        min_frame_rms = 1.0

        for f in range(FRAMES_PER_BLOCK):
            clipped_total += decode_adc_frame_into(
                raw_bytes, f * FRAME_N, FRAME_N, self.frame_pcm
            )
            log_rms, norm_rms, crest = self.fft.extract_frame(
                self.frame_pcm, self.curr_mel, f * N_BANDS
            )
            self.curr_rms[f] = log_rms
            rms_sq_sum += norm_rms * norm_rms
            if norm_rms > max_frame_rms:
                max_frame_rms = norm_rms
            if norm_rms < min_frame_rms:
                min_frame_rms = norm_rms
            if crest > max_crest:
                max_crest = crest

        score = self._score_fused() if self.has_prev else None

        self.prev_mel, self.curr_mel = self.curr_mel, self.prev_mel
        self.prev_rms, self.curr_rms = self.curr_rms, self.prev_rms
        self.has_prev = True

        block_rms = math.sqrt(rms_sq_sum / float(FRAMES_PER_BLOCK))
        return score, (clipped_total, block_rms, max_frame_rms, min_frame_rms, max_crest)


class _BurstBackend:
    """Compact burst MLP backend (tg_model_burst.py) over 1-second ADC blocks."""

    model_type = 'burst_mlp'

    def __init__(self, model):
        # Lazy import so v4.6-only deployments do not require tg_burst.py
        try:
            import tg_burst as tb
        except ImportError:
            from . import tg_burst as tb
        self._tb = tb
        self.model = model
        self.threshold = float(model.THRESHOLD)
        self.burst_samples = int(model.BURST_SAMPLES)
        self.spectrum = tb.Spectrum(self.burst_samples)
        self.classifier = tb.Classifier(model)
        self.frames = array('f', [0.0]) * (tb.WINDOW_FRAMES * (tb.BANDS + 1))
        self.features = array('f', [0.0]) * tb.FEATURES
        self.cursor = 0
        self.valid_frames = 0

    def reset(self):
        self.cursor = 0
        self.valid_frames = 0

    def clear_window(self):
        self.cursor = 0
        self.valid_frames = 0

    def process_block(self, raw_bytes):
        """Extract 4 burst frames from a 4000-sample block and score if 8 frames ready."""
        tb = self._tb
        clipped_total = 0
        rms_sq_sum = 0.0
        max_frame_rms = 0.0
        min_frame_rms = 1.0
        max_crest = 0.0
        n = self.burst_samples
        pcm = self.spectrum.pcm

        for f in range(tb.FRAMES_PER_SECOND):
            clipped_total += decode_adc_frame_into(raw_bytes, f * FRAME_N, n, pcm)
            mean = 0.0
            for i in range(n):
                mean += pcm[i]
            mean /= float(n)
            msq = 0.0
            peak = 0.0
            for i in range(n):
                v = float(pcm[i]) - mean
                av = -v if v < 0.0 else v
                if av > peak:
                    peak = av
                msq += v * v
            rms_pcm = math.sqrt(msq / float(n))
            norm_rms = rms_pcm / 32768.0
            crest = peak / (rms_pcm + 1e-6)
            rms_sq_sum += norm_rms * norm_rms
            if norm_rms > max_frame_rms:
                max_frame_rms = norm_rms
            if norm_rms < min_frame_rms:
                min_frame_rms = norm_rms
            if crest > max_crest:
                max_crest = crest

            self.spectrum.extract(self.frames, self.cursor * (tb.BANDS + 1))
            self.cursor = (self.cursor + 1) % tb.WINDOW_FRAMES
            if self.valid_frames < tb.WINDOW_FRAMES:
                self.valid_frames += 1

        score = None
        if self.valid_frames == tb.WINDOW_FRAMES:
            tb.summarize(self.frames, self.features)
            score = self.classifier.score(self.features)

        block_rms = math.sqrt(rms_sq_sum / float(tb.FRAMES_PER_SECOND))
        return score, (clipped_total, block_rms, max_frame_rms, min_frame_rms, max_crest)


class Detector:
    """Incremental streaming audio detector for external LoPy firmware.

    Usage:
        detector = Detector(model=tg_model_burst)
        for audio_chunk in nagraj_audio():
            detector.process(audio_chunk)
        result = detector.finalize(vib_active=vib_aktywny)
    """

    def __init__(
        self,
        model=None,
        threshold=None,
        min_confirm_windows=2,
        max_gap_s=1.5,
        impact_min_rms=0.035,
        impact_crest_threshold=5.5,
        impact_jump_ratio=3.0,
        require_impact=False,
        event_type_alarm=EVENT_TYPE_THEFT,
        source_bit_mic=SOURCE_BIT_MIC,
        source_bit_vib=SOURCE_BIT_VIB,
    ):
        if model is None:
            model = _load_default_model()

        if getattr(model, 'MODEL_TYPE', None) == 'tiny_cnn_wide_v46':
            self._backend = _V46Backend(model)
        elif getattr(model, 'FEATURE_VERSION', None) == 1 and hasattr(model, 'BURST_SAMPLES'):
            self._backend = _BurstBackend(model)
        else:
            raise ValueError('Unsupported model object; expected v4.6 CNN or burst MLP')

        self.threshold = float(self._backend.threshold if threshold is None else threshold)
        if not (0.0 < self.threshold < 1.0):
            raise ValueError('threshold must be in (0, 1)')
        if int(min_confirm_windows) < 1:
            raise ValueError('min_confirm_windows must be >= 1')

        self.min_confirm_windows = int(min_confirm_windows)
        self.max_gap_s = float(max_gap_s)
        self.impact_min_rms = float(impact_min_rms)
        self.impact_crest_threshold = float(impact_crest_threshold)
        self.impact_jump_ratio = float(impact_jump_ratio)
        self.require_impact = bool(require_impact)
        self.event_type_alarm = int(event_type_alarm)
        self.source_bit_mic = int(source_bit_mic)
        self.source_bit_vib = int(source_bit_vib)
        self.reset()

    def reset(self):
        """Reset per-session state while keeping pre-allocated FFT/model buffers."""
        self._backend.reset()
        self.blocks_processed = 0
        self.model_scores = []
        self.positive_windows = 0
        self._current_streak = 0
        self.max_consecutive_hits = 0
        self._max_confirmed_score = 0.0
        self.impact_count = 0
        self.gap_resets = 0
        self.clipped_samples = 0
        self.max_audio_rms = 0.0
        self._rms_sum = 0.0
        self._prev_block_rms = None
        self._prev_timestamp_s = None
        self._vib_active = False

    def process(self, audio_chunk, gap_s=0.0, timestamp_s=None, vib_active=None):
        """Process one 1-second (8000-byte) uint16 LE 12-bit ADC audio block.

        Does NOT retain any reference to `audio_chunk`. Returns a lightweight
        per-block diagnostic dict (score is None on the first block after start
        or after a gap reset, since a 2-second window requires 2 blocks).
        """
        if not isinstance(audio_chunk, (bytes, bytearray, memoryview)):
            raise TypeError('audio_chunk must be bytes, bytearray, or memoryview')
        if len(audio_chunk) != BLOCK_BYTES:
            raise ValueError(
                'Expected %d bytes (%d samples), got %d bytes'
                % (BLOCK_BYTES, BLOCK_SAMPLES, len(audio_chunk))
            )

        if vib_active is not None and bool(vib_active):
            self._vib_active = True

        effective_gap = float(gap_s)
        if timestamp_s is not None:
            ts = float(timestamp_s)
            if self._prev_timestamp_s is not None:
                delta = ts - self._prev_timestamp_s
                if delta <= 0.0:
                    raise ValueError('timestamp_s must be strictly increasing')
                inferred_gap = delta - 1.0
                if inferred_gap > effective_gap:
                    effective_gap = inferred_gap
            self._prev_timestamp_s = ts

        gap_reset = False
        if self.blocks_processed > 0 and effective_gap > self.max_gap_s:
            self._backend.clear_window()
            self._current_streak = 0
            self.gap_resets += 1
            gap_reset = True

        score, stats = self._backend.process_block(audio_chunk)
        clipped, block_rms, max_frame_rms, min_frame_rms, max_crest = stats

        self.blocks_processed += 1
        self.clipped_samples += clipped
        self._rms_sum += block_rms
        if block_rms > self.max_audio_rms:
            self.max_audio_rms = block_rms

        impact_now = False
        if max_frame_rms >= self.impact_min_rms:
            baseline_rms = min_frame_rms if min_frame_rms > 1e-5 else 1e-5
            if self._prev_block_rms is not None and self._prev_block_rms < baseline_rms:
                baseline_rms = max(self._prev_block_rms, 1e-5)
            jump_ratio = max_frame_rms / baseline_rms
            if max_crest >= self.impact_crest_threshold or jump_ratio >= self.impact_jump_ratio:
                impact_now = True
                self.impact_count += 1
        self._prev_block_rms = block_rms

        hit = False
        if score is not None:
            score_f = round(float(score), 6)
            self.model_scores.append(score_f)
            if score >= self.threshold:
                hit = True
                self.positive_windows += 1
                self._current_streak += 1
                if self._current_streak > self.max_consecutive_hits:
                    self.max_consecutive_hits = self._current_streak
                if self._current_streak >= self.min_confirm_windows:
                    if score > self._max_confirmed_score:
                        self._max_confirmed_score = score
            else:
                self._current_streak = 0

        return {
            'block_index': self.blocks_processed - 1,
            'score': round(float(score), 6) if score is not None else None,
            'engine_hit': hit,
            'impact_detected': impact_now,
            'block_rms': round(block_rms, 6),
            'clipped_samples': clipped,
            'gap_reset': gap_reset,
        }

    def _calibrate_confidence(self, alarm, engine_detected, impact_detected, vib_flag, max_score):
        """Compute calibrated V2 confidence integer (0..100), distinct from raw score."""
        if self.blocks_processed == 0 or not self.model_scores:
            return 0

        n_scores = len(self.model_scores)
        if not engine_detected:
            ratio = min(1.0, max(0.0, max_score / self.threshold))
            return int(round(ratio * 40.0))

        ref_score = self._max_confirmed_score if self._max_confirmed_score > 0.0 else max_score
        denom = max(1e-6, 1.0 - self.threshold)
        margin = min(1.0, max(0.0, (ref_score - self.threshold) / denom))
        persistence = min(1.0, float(self.positive_windows) / float(n_scores))

        conf = 55.0 + 25.0 * margin + 10.0 * persistence
        if impact_detected:
            conf += 5.0
        if vib_flag:
            conf += 5.0
        if not alarm:
            conf = min(conf, 49.0)
        return max(0, min(100, int(round(conf))))

    def _quantize_energy(self):
        """Map peak normalized audio RMS to V2 uint8 energy (0..255)."""
        if self.blocks_processed == 0 or self.max_audio_rms <= 0.0:
            return 0
        db = 20.0 * math.log10(max(self.max_audio_rms, 1e-6))
        scaled = (db + 60.0) * (255.0 / 60.0)
        return max(0, min(255, int(round(scaled))))

    def finalize(self, vib_active=None, mic_active=None):
        """Finalize the recording session and return a V2-compatible result dict."""
        vib_flag = self._vib_active if vib_active is None else (self._vib_active or bool(vib_active))
        n_scores = len(self.model_scores)
        max_score = max(self.model_scores) if n_scores else 0.0
        mean_score = (sum(self.model_scores) / float(n_scores)) if n_scores else 0.0

        engine_detected = self.max_consecutive_hits >= self.min_confirm_windows
        impact_detected = self.impact_count > 0

        if self.require_impact:
            alarm = bool(engine_detected and impact_detected)
        else:
            alarm = bool(engine_detected)

        event_type = self.event_type_alarm if alarm else EVENT_TYPE_NONE

        source_bits = 0
        audio_active = bool(engine_detected or impact_detected or (mic_active and self.blocks_processed > 0 and alarm))
        if audio_active:
            source_bits |= self.source_bit_mic
        if vib_flag:
            source_bits |= self.source_bit_vib

        if engine_detected:
            duration_s = min(self.blocks_processed, self.positive_windows + 1)
        elif impact_detected:
            duration_s = min(self.blocks_processed, self.impact_count)
        else:
            duration_s = 0

        confidence = self._calibrate_confidence(
            alarm, engine_detected, impact_detected, vib_flag, max_score
        )
        energy = self._quantize_energy()

        return {
            'alarm': alarm,
            'event_type': event_type,
            'confidence': confidence,
            'source_bits': source_bits,
            'duration_s': int(max(0, min(65535, duration_s))),
            'energy': energy,
            'engine_detected': engine_detected,
            'impact_detected': impact_detected,
            'impact_count': self.impact_count,
            'vib_active': vib_flag,
            'model_type': self._backend.model_type,
            'model_threshold': self.threshold,
            'model_scores': list(self.model_scores),
            'max_model_score': round(max_score, 6),
            'mean_model_score': round(mean_score, 6),
            'positive_windows': self.positive_windows,
            'max_consecutive_hits': self.max_consecutive_hits,
            'blocks_processed': self.blocks_processed,
            'observed_duration_s': float(self.blocks_processed),
            'gap_resets': self.gap_resets,
            'clipped_samples': self.clipped_samples,
            'max_audio_rms': round(self.max_audio_rms, 6),
        }
