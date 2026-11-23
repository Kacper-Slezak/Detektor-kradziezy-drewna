from array import array
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np

from algorithm.app.burst_evaluate import portable_predict
from algorithm.app.burst_prepare import HOP, all_windows, frame_features
from algorithm.app.burst_stage_lopy import DEFAULT_MODEL, read_export, stage
from algorithm.app.burst_train import predict
from firmware.lib import tg_burst_device as device
from firmware.lib.tg_burst import BANDS, Classifier, RATE, Spectrum, Votes
from firmware.lib.tg_hardware import ADXL345


def signal():
    t = np.arange(5 * RATE) / RATE
    rng = np.random.default_rng(2026)
    return np.rint(3000 * np.sin(2 * np.pi * 111 * t) + 1200 * np.sin(2 * np.pi * 347 * t)
                   + rng.normal(4000, 200, len(t))).astype('<i2')


class TestBurst(unittest.TestCase):
    def setUp(self):
        self.model = read_export(DEFAULT_MODEL)

    def test_fft_parity_for_both_sizes_with_dc_and_silence(self):
        pcm = signal()
        pcm[HOP:2 * HOP] = 784
        for size in (256, 512):
            fft = Spectrum(size)
            for start, expected in zip(range(0, len(pcm), HOP), frame_features(pcm, size)):
                fft.pcm[:] = array('h', map(int, pcm[start:start + size]))
                out = array('f', [0]) * (BANDS + 1)
                fft.extract(out, 0)
                np.testing.assert_allclose(out, expected, atol=0.0005, rtol=0)

    def test_stream_and_quantized_vector_scores_match(self):
        model = self.model
        pcm = signal()
        features = all_windows(pcm, model.BURST_SAMPLES)
        weights = np.frombuffer(model.WEIGHTS, dtype=np.int8)
        split = model.INPUTS * model.HIDDEN
        layers = [weights[:split].reshape(model.HIDDEN, model.INPUTS).T,
                  weights[split:].reshape(-1, 1)]
        reference = predict(features, (model.MEAN, model.INVERSE_STD, layers,
                                       model.SCALES, [model.BIASES[:-1], [model.BIASES[-1]]]))
        embedded = np.fromiter(portable_predict(pcm, model), dtype=float)
        np.testing.assert_allclose(embedded, reference, atol=0.0005, rtol=0)
        np.testing.assert_array_equal(embedded >= model.THRESHOLD, reference >= model.THRESHOLD)

    def test_votes_reset_and_require_consecutive_threshold_hits(self):
        votes = Votes(.84, 2, 2)
        self.assertEqual([votes.step(value) for value in (.84, .9, None, .9, .83, .84, .84)],
                         [False, True, False, False, False, False, True])

    def test_timing_loss_requires_a_fresh_window_and_buffers_are_reused(self):
        monitor = device.Monitor(self.model)
        def buffers_of(m):
            fft = m.spectrum
            return (fft.pcm, fft.real, fft.imag, fft.cos, fft.sin, fft.hann, fft.reverse,
                    m.frames, m.features, m.classifier.values)

        buffers = buffers_of(monitor)
        for _ in range(8):
            monitor.push(True)
        self.assertIsNotNone(monitor.score)
        monitor.votes.step(1)
        monitor.votes.step(1)
        monitor.push(False)
        for _ in range(7):
            monitor.push(True)
        self.assertIsNone(monitor.score)
        self.assertFalse(monitor.confirmed)
        for _ in range(4):
            monitor.push(True)
        self.assertIsNotNone(monitor.score)
        after = buffers_of(monitor)
        self.assertTrue(all(a is b for a, b in zip(buffers, after)))
        self.assertEqual(sum(a.itemsize * len(a) for a in buffers), 11008)

    def test_adc_capture_offset_clipping_and_wrap(self):
        class Clock:
            value = 3990

            def ticks_us(self):
                self.value = (self.value + 5) % 4000
                return self.value

            @staticmethod
            def ticks_diff(new, old):
                return (new - old) % 4000

        clock = Clock()
        pcm = array('h', [0, 0, 0])
        adc = iter((0, 2048, 4095))
        with patch.object(device, 'time', clock):
            late, clips = device.capture(lambda: next(adc), pcm, clock.value, 100)
        self.assertEqual(list(pcm), [-32768, 0, 32752])
        self.assertEqual((late, clips), (0, 2))

    def test_sensor_units_and_stage(self):
        self.assertEqual(ADXL345._axis(0x00, 0x01), 1.0)
        self.assertEqual(ADXL345._axis(0x00, 0xFF), -1.0)
        with TemporaryDirectory() as temp:
            output = Path(temp) / 'stage'
            stage(output, DEFAULT_MODEL, accel=True)
            config = (output / 'config.py').read_text(encoding='utf8')
            self.assertIn("MODEL_FLAVOR = 'burst'", config)
            self.assertIn('ACCEL_ENABLED = True', config)
            self.assertIn('ENABLE_PHYSICAL_ALARM = False', config)
            self.assertIn('ALARM_OUTPUT_PIN = None', config)
            self.assertEqual(Classifier(read_export(output / 'lib' / DEFAULT_MODEL.name)).inputs, 32)
            self.assertEqual(len(list(output.rglob('*.py'))), 7)


if __name__ == '__main__':
    unittest.main()
