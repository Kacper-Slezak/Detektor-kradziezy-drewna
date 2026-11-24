"""Unit and regression tests for the streaming ADC detector (`tg_stream_detector`).

Covers ADC decoding, normalization, fused v4.6 CNN and burst MLP parity,
reusable bytearray mutation, 10-block sessions, background/engine/impact audio,
sampling gaps, reset isolation, vibration metadata safety, and V2 frame packing.
"""

import importlib.util
import math
from pathlib import Path
import random
import struct
import sys
import unittest
import wave

ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = ROOT / 'firmware' / 'lib'
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import tg_burst
import tg_cnn_v46
import tg_model_burst
import tg_stream_detector as sd
import tg_temporal_v46

V46_MODEL_PATH = ROOT / 'algorithm' / 'results' / 'v4_6_wideband' / 'tg_model_v46.py'
FOREST_4K_WAV = ROOT / 'algorithm' / 'sample_audio' / 'forest-ambience-4k.wav'
TRUCK_4K_WAV = ROOT / 'algorithm' / 'sample_audio' / 'forest-with-truck-4k.wav'


def _load_v46_model():
    if not V46_MODEL_PATH.is_file():
        return None
    spec = importlib.util.spec_from_file_location('tg_model_v46_real', V46_MODEL_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pcm16_to_adc_block(pcm_samples, out_buf=None):
    """Encode 4000 signed PCM16 samples into 8000-byte uint16 LE 12-bit ADC buffer."""
    if len(pcm_samples) != sd.BLOCK_SAMPLES:
        raise ValueError('Expected 4000 samples')
    buf = bytearray(sd.BLOCK_BYTES) if out_buf is None else out_buf
    idx = 0
    for s in pcm_samples:
        adc = (int(s) + 32768) >> 4
        if adc < 0:
            adc = 0
        elif adc > 4095:
            adc = 4095
        buf[idx] = adc & 0xFF
        buf[idx + 1] = (adc >> 8) & 0xFF
        idx += 2
    return buf


def _read_wav_blocks(wav_path, start_s=0, num_blocks=10):
    """Read `num_blocks` 1-second 4 kHz PCM16 blocks from a mono WAV file."""
    with wave.open(str(wav_path), 'rb') as wf:
        if wf.getframerate() != 4000 or wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise ValueError('Expected 4 kHz mono PCM16 WAV: %s' % wav_path)
        wf.setpos(start_s * 4000)
        blocks = []
        for _ in range(num_blocks):
            raw = wf.readframes(4000)
            if len(raw) < 8000:
                break
            samples = struct.unpack('<4000h', raw)
            blocks.append(_pcm16_to_adc_block(samples))
        return blocks


def _make_background_block(seed=1, amplitude=250):
    rng = random.Random(seed)
    samples = [rng.randint(-amplitude, amplitude) for _ in range(sd.BLOCK_SAMPLES)]
    return _pcm16_to_adc_block(samples)


def _make_impact_block(seed=2, bg_amp=120, peak_amp=22000):
    rng = random.Random(seed)
    samples = [rng.randint(-bg_amp, bg_amp) for _ in range(sd.BLOCK_SAMPLES)]
    # Short 12-sample damped impact transient inside frame 1
    start = 1350
    for k in range(12):
        decay = math.exp(-k * 0.35)
        sign = 1 if (k % 2 == 0) else -1
        samples[start + k] = int(sign * peak_amp * decay)
    return _pcm16_to_adc_block(samples)


def _make_synthetic_engine_block(block_idx=0):
    samples = []
    phase0 = block_idx * sd.BLOCK_SAMPLES
    for i in range(sd.BLOCK_SAMPLES):
        t = (phase0 + i) / float(sd.SAMPLE_RATE)
        val = (
            6500.0 * math.sin(2.0 * math.pi * 62.0 * t)
            + 4800.0 * math.sin(2.0 * math.pi * 124.0 * t)
            + 3000.0 * math.sin(2.0 * math.pi * 186.0 * t)
            + 1800.0 * math.sin(2.0 * math.pi * 248.0 * t)
        )
        samples.append(int(val))
    return _pcm16_to_adc_block(samples)


class TestAdcDecoding(unittest.TestCase):
    def test_little_endian_decoding_boundaries_and_clamping(self):
        raw = bytearray()
        values = [0, 1, 2048, 4095, 5000]  # 5000 exceeds 12-bit -> clamped to 4095
        for v in values:
            raw.append(v & 0xFF)
            raw.append((v >> 8) & 0xFF)
        pcm = sd.decode_adc_u16_le(raw)
        self.assertEqual(list(pcm), [-32768, -32752, 0, 32752, 32752])

    def test_decode_adc_odd_length_raises(self):
        with self.assertRaises(ValueError):
            sd.decode_adc_u16_le(bytearray(5))

    def test_clipping_counter(self):
        raw = bytearray(struct.pack('<4H', 0, 2048, 4095, 1024))
        out = sd.array('h', [0]) * 4
        clipped = sd.decode_adc_frame_into(raw, 0, 4, out)
        self.assertEqual(clipped, 2)


class TestStreamingDetectorCore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v46_model = _load_v46_model()

    def test_invalid_block_sizes_and_types(self):
        det = sd.Detector(model=tg_model_burst)
        for bad_len in (0, 2, 7998, 7999, 8001, 16000):
            with self.subTest(bad_len=bad_len):
                with self.assertRaises(ValueError):
                    det.process(bytearray(bad_len))
        with self.assertRaises(TypeError):
            det.process([0] * 8000)

    def test_empty_session(self):
        det = sd.Detector(model=tg_model_burst)
        res = det.finalize()
        self.assertFalse(res['alarm'])
        self.assertEqual(res['event_type'], sd.EVENT_TYPE_NONE)
        self.assertEqual(res['confidence'], 0)
        self.assertEqual(res['source_bits'], 0)
        self.assertEqual(res['duration_s'], 0)
        self.assertEqual(res['energy'], 0)
        self.assertEqual(res['blocks_processed'], 0)
        self.assertEqual(res['observed_duration_s'], 0.0)
        self.assertEqual(res['model_scores'], [])

    def test_vibration_wakeup_alone_never_triggers_alarm(self):
        det = sd.Detector(model=tg_model_burst)
        res_empty = det.finalize(vib_active=True)
        self.assertFalse(res_empty['alarm'])
        self.assertTrue(res_empty['vib_active'])
        self.assertEqual(res_empty['source_bits'], sd.SOURCE_BIT_VIB)

        det.reset()
        for i in range(5):
            det.process(_make_background_block(seed=10 + i), vib_active=True)
        res_bg = det.finalize(vib_active=True)
        self.assertFalse(res_bg['alarm'])
        self.assertFalse(res_bg['engine_detected'])
        self.assertTrue(res_bg['vib_active'])
        self.assertEqual(res_bg['event_type'], sd.EVENT_TYPE_NONE)

    def test_reusable_bytearray_mutation_isolation(self):
        model = self.v46_model if self.v46_model is not None else tg_model_burst
        blocks = [_make_synthetic_engine_block(i) for i in range(4)]

        # Reference run with independent buffers
        det_ref = sd.Detector(model=model)
        for blk in blocks:
            det_ref.process(blk)
        ref_res = det_ref.finalize()

        # Simulated firmware nagraj_audio() reusing one bytearray and mutating after process
        det_reuse = sd.Detector(model=model)
        shared = bytearray(sd.BLOCK_BYTES)
        for blk in blocks:
            shared[:] = blk
            det_reuse.process(shared)
            # Immediately overwrite shared buffer with garbage
            for k in range(0, sd.BLOCK_BYTES, 2):
                shared[k] = 0xFF
                shared[k + 1] = 0x0F
        reuse_res = det_reuse.finalize()

        self.assertEqual(ref_res['model_scores'], reuse_res['model_scores'])
        self.assertEqual(ref_res['alarm'], reuse_res['alarm'])
        self.assertEqual(ref_res['confidence'], reuse_res['confidence'])
        self.assertEqual(ref_res['energy'], reuse_res['energy'])

    def test_audio_impact_detection(self):
        det = sd.Detector(model=tg_model_burst)
        bg = _make_background_block(seed=3)
        imp = _make_impact_block(seed=4)
        step0 = det.process(bg)
        step1 = det.process(imp)
        self.assertFalse(step0['impact_detected'])
        self.assertTrue(step1['impact_detected'])
        res = det.finalize()
        self.assertTrue(res['impact_detected'])
        self.assertEqual(res['impact_count'], 1)
        self.assertFalse(res['engine_detected'])
        self.assertFalse(res['alarm'])

    def test_sampling_gap_resets_window_and_streak(self):
        model = self.v46_model if self.v46_model is not None else tg_model_burst
        det = sd.Detector(model=model, max_gap_s=1.0)
        b0 = _make_background_block(seed=20)
        b1 = _make_background_block(seed=21)
        b2 = _make_background_block(seed=22)

        s0 = det.process(b0, timestamp_s=0.0)
        s1 = det.process(b1, timestamp_s=1.0)
        # 3.5 s later -> inferred gap = 2.5 s > max_gap_s (1.0 s)
        s2 = det.process(b2, timestamp_s=4.5)

        self.assertIsNone(s0['score'])
        self.assertIsNotNone(s1['score'])
        self.assertTrue(s2['gap_reset'])
        self.assertIsNone(s2['score'])
        res = det.finalize()
        self.assertEqual(res['gap_resets'], 1)
        self.assertEqual(len(res['model_scores']), 1)

    def test_reset_between_independent_sessions(self):
        model = self.v46_model if self.v46_model is not None else tg_model_burst
        det = sd.Detector(model=model, threshold=1e-9)  # force hits in session 1
        for i in range(4):
            det.process(_make_synthetic_engine_block(i), vib_active=True)
        res1 = det.finalize(vib_active=True)
        self.assertTrue(res1['alarm'])
        self.assertEqual(res1['blocks_processed'], 4)

        det.reset()
        det.threshold = float(model.THRESHOLD)
        for i in range(3):
            det.process(_make_background_block(seed=50 + i))
        res2 = det.finalize()

        det_fresh = sd.Detector(model=model)
        for i in range(3):
            det_fresh.process(_make_background_block(seed=50 + i))
        res_fresh = det_fresh.finalize()

        self.assertEqual(res2, res_fresh)
        self.assertFalse(res2['alarm'])
        self.assertFalse(res2['vib_active'])

    def test_v2_protocol_struct_packing_compatibility(self):
        det = sd.Detector(model=tg_model_burst)
        for i in range(10):
            det.process(_make_background_block(seed=100 + i))
        res = det.finalize(vib_active=False)

        # Verify all required V2 keys exist and pack cleanly with firmware/main4.py format
        for key in ('alarm', 'event_type', 'confidence', 'source_bits', 'duration_s', 'energy'):
            self.assertIn(key, res)
        self.assertGreaterEqual(res['confidence'], 0)
        self.assertLessEqual(res['confidence'], 100)
        self.assertGreaterEqual(res['energy'], 0)
        self.assertLessEqual(res['energy'], 255)
        self.assertGreaterEqual(res['duration_s'], 0)
        self.assertLessEqual(res['duration_s'], 65535)
        self.assertEqual(res['blocks_processed'], 10)
        self.assertEqual(res['observed_duration_s'], 10.0)
        self.assertEqual(len(res['model_scores']), 9)

        # Exact binary layout from firmware/main4.py::przygotuj_ramke_alarm()
        body = struct.pack(
            '>BBBHBB',
            res['event_type'],
            res['source_bits'],
            res['confidence'],
            res['duration_s'],
            res['energy'],
            100,  # battery_pct
        )
        self.assertEqual(len(body), 7)


class TestModelParityAndRealRecordings(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v46_model = _load_v46_model()

    def test_v46_fused_cnn_matches_reference_tg_cnn_v46(self):
        if self.v46_model is None:
            self.skipTest('Local trained tg_model_v46.py not present')

        b0 = _make_synthetic_engine_block(0)
        b1 = _make_synthetic_engine_block(1)

        # Streaming fused detector
        det = sd.Detector(model=self.v46_model)
        det.process(b0)
        step = det.process(b1)
        stream_score = step['score']

        # Reference tg_temporal_v46.MelFFT + tg_cnn_v46.score_features on identical decoded PCM
        ref_fft = tg_temporal_v46.MelFFT()
        c0 = tg_temporal_v46.RawChunk(0.0)
        c0.samples = sd.decode_adc_u16_le(b0)
        c1 = tg_temporal_v46.RawChunk(1.0)
        c1.samples = sd.decode_adc_u16_le(b1)
        m0, r0 = ref_fft.second(c0)
        m1, r1 = ref_fft.second(c1)
        patch, energy = tg_temporal_v46.normalize_window(m0 + m1, r0 + r1)
        ref_score = tg_cnn_v46.score_features(patch, energy, self.v46_model)

        self.assertAlmostEqual(stream_score, ref_score, delta=1e-5)

    def test_burst_backend_matches_reference_tg_burst(self):
        b0 = _make_synthetic_engine_block(0)
        b1 = _make_synthetic_engine_block(1)

        det = sd.Detector(model=tg_model_burst)
        det.process(b0)
        step = det.process(b1)
        stream_score = step['score']

        # Reference tg_burst.Spectrum + summarize + Classifier
        spec = tg_burst.Spectrum(tg_model_burst.BURST_SAMPLES)
        clf = tg_burst.Classifier(tg_model_burst)
        frames = sd.array('f', [0.0]) * (tg_burst.WINDOW_FRAMES * (tg_burst.BANDS + 1))
        feats = sd.array('f', [0.0]) * tg_burst.FEATURES
        cursor = 0
        for blk in (b0, b1):
            for f in range(4):
                sd.decode_adc_frame_into(blk, f * 1000, tg_model_burst.BURST_SAMPLES, spec.pcm)
                spec.extract(frames, cursor * (tg_burst.BANDS + 1))
                cursor += 1
        tg_burst.summarize(frames, feats)
        ref_score = clf.score(feats)

        self.assertAlmostEqual(stream_score, ref_score, delta=1e-6)

    def test_10_block_real_forest_background_no_alarm(self):
        if not FOREST_4K_WAV.is_file():
            self.skipTest('Local forest-ambience-4k.wav not present')

        blocks = _read_wav_blocks(FOREST_4K_WAV, start_s=0, num_blocks=10)
        self.assertEqual(len(blocks), 10)

        # Test both burst MLP (always tracked) and v4.6 CNN (when present)
        models = [tg_model_burst]
        if self.v46_model is not None:
            models.append(self.v46_model)

        for model in models:
            with self.subTest(model=getattr(model, 'MODEL_TYPE', 'burst_mlp')):
                det = sd.Detector(model=model)
                shared = bytearray(sd.BLOCK_BYTES)
                for blk in blocks:
                    shared[:] = blk
                    det.process(shared)
                res = det.finalize(vib_active=False)
                self.assertEqual(res['blocks_processed'], 10)
                self.assertEqual(len(res['model_scores']), 9)
                self.assertFalse(res['alarm'])
                self.assertFalse(res['engine_detected'])

    def test_10_block_real_truck_engine_detected(self):
        if not TRUCK_4K_WAV.is_file():
            self.skipTest('Local forest-with-truck-4k.wav not present')

        # Annotated truck onset is 19 s (burst confirms at window-end 20 s & 21 s,
        # which start at 18 s and 19 s per BURST_TECHNICAL_REPORT.md).
        blocks = _read_wav_blocks(TRUCK_4K_WAV, start_s=18, num_blocks=10)
        self.assertEqual(len(blocks), 10)

        models = [tg_model_burst]
        if self.v46_model is not None:
            models.append(self.v46_model)

        for model in models:
            with self.subTest(model=getattr(model, 'MODEL_TYPE', 'burst_mlp')):
                det = sd.Detector(model=model)
                shared = bytearray(sd.BLOCK_BYTES)
                for blk in blocks:
                    shared[:] = blk
                    det.process(shared)
                res = det.finalize(vib_active=True)
                self.assertEqual(res['blocks_processed'], 10)
                self.assertEqual(len(res['model_scores']), 9)
                self.assertTrue(res['engine_detected'], 'Expected engine detection: %s' % res)
                self.assertTrue(res['alarm'])
                self.assertEqual(res['event_type'], sd.EVENT_TYPE_THEFT)
                self.assertGreaterEqual(res['confidence'], 55)
                self.assertGreater(res['duration_s'], 0)
                self.assertTrue(res['source_bits'] & sd.SOURCE_BIT_MIC)
                self.assertTrue(res['source_bits'] & sd.SOURCE_BIT_VIB)


if __name__ == '__main__':
    unittest.main()
