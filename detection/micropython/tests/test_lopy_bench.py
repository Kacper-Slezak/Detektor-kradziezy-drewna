from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch

from algorithm.app.burst_stage_lopy import DEFAULT_MODEL, read_export, stage
from algorithm.app.lopy_bench_report import analyze
from algorithm.app.lopy_capture import import_capture, scan_capture, sha256
from firmware import lopy_bench as bench
from firmware.lib import tg_burst_device as device
from firmware.lib.tg_burst_capture import CaptureWriter


class SimClock:
    period = 1 << 22

    def __init__(self):
        self.current = self.period - 500000

    def ticks_us(self):
        self.current += 5
        return self.current % self.period

    def sleep_ms(self, ms):
        self.current += ms * 1000

    def ticks_diff(self, newer, older):
        return (newer - older + self.period // 2) % self.period - self.period // 2


class DesktopADC:
    def __init__(self):
        self.count = 0

    def audio(self):
        self.count += 1
        return 2048 + (self.count % 32) - 16


def metadata(**extra):
    fields = dict(format=1, rate=4000, burst_samples=512, sample_period_us=250, slot_us=250000,
                  adc_bits=12, max_late_ratio=.08, max_sample_late_us=100, max_slot_late_us=2500,
                  model_sha256=sha256(DEFAULT_MODEL), machine='Desktop clock simulation',
                  implementation='cpython', accel_enabled=True, recording=True, capture_kind='bench')
    fields.update(extra)
    return fields


class TestLoPyBench(unittest.TestCase):
    def test_scheduler_wrap_and_overrun_resync(self):
        tick = SimClock()
        with patch.object(device, 'time', tick):
            clock = device.BurstClock(2500)
            first, _, skipped = clock.next()
            self.assertEqual(skipped, 0)
            second, _, skipped = clock.next()
            self.assertAlmostEqual(tick.ticks_diff(second, first), 250000, delta=10)
            tick.current += 510000
            rebased, _, skipped = clock.next()
            self.assertEqual(skipped, 2)
            next_start, _, skipped = clock.next()
            self.assertEqual(skipped, 0)
            self.assertAlmostEqual(tick.ticks_diff(next_start, rebased), 250000, delta=10)
            self.assertLess(rebased, first)

    def test_desktop_end_to_end_capture_timing_replay_and_log(self):
        tick = SimClock()
        memory = SimpleNamespace(mem_free=lambda: 25000, mem_alloc=lambda: 16000, collect=lambda: None)
        cfg = SimpleNamespace(BURST_MAX_SLOT_LATE_US=2500, BURST_MAX_SAMPLE_LATE_US=100,
                              MAX_LATE_SAMPLES_RATIO=.08)
        adc = DesktopADC()
        hub = SimpleNamespace(audio=adc.audio, accel=SimpleNamespace(read_g=lambda: (0, 0, 1)))
        report = StringIO()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            record = root / 'simulated.lopy'
            with patch.object(device, 'time', tick), patch.object(bench, 'time', tick), \
                    patch.object(bench, 'gc', memory), redirect_stdout(report), record.open('wb') as stream:
                model = read_export(DEFAULT_MODEL)
                monitor = device.Monitor(model)
                stats = bench.Stats()
                monitor.spectrum = bench.MeasuredSpectrum(monitor.spectrum, stats)
                monitor.classifier = bench.MeasuredClassifier(monitor.classifier, stats)
                header = metadata()
                bench.emit('start', metadata=header, allocation=bench.fragmentation_probe(4096))
                complete, elapsed = bench.run_slots(cfg, monitor, hub, 3, CaptureWriter(stream, header), 4, stats)
                bench.emit('finish', completed=complete, stats=stats.report(elapsed),
                           allocation=bench.fragmentation_probe(4096))
            self.assertTrue(complete)
            self.assertGreaterEqual(elapsed, 3000000)
            result = import_capture(record, root / 'indexed', DEFAULT_MODEL)
            self.assertEqual(result['slots'] * 512, adc.count)
            self.assertEqual(result['invalid_slots'], 0)
            self.assertEqual(result['abandoned_starts'], 0)
            self.assertEqual(result['adc'], {'min': 2032, 'max': 2063, 'mean': 2047.5, 'rail_reads': 0})
            self.assertTrue((root / 'indexed' / 'replay.csv').is_file())
            self.assertEqual(stats.totals['decisions'], result['slots'] // 4 - 1)
            parsed = analyze(report.getvalue().splitlines(), 'sd')
            self.assertFalse(parsed['original_lopy_identity_reported'])
            self.assertFalse(parsed['numerical_gates_pass'])  # Only a 3 second fixture.
            self.assertTrue(parsed['checks']['decision_count_and_latency'])
            self.assertTrue(parsed['checks']['rate_within_one_percent'])
            self.assertTrue(parsed['checks']['accelerometer'])
            truncated = root / 'truncated.lopy'
            truncated.write_bytes(record.read_bytes()[:-10])
            with self.assertRaisesRegex(ValueError, 'Truncated'):
                scan_capture(truncated)

    def test_opt_in_stage_pins_model_and_does_not_change_default_stage(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            stage(root / 'normal', DEFAULT_MODEL)
            stage(root / 'bench', DEFAULT_MODEL, accel=True, bench=True)
            normal, diagnostic = root / 'normal', root / 'bench'
            self.assertFalse((normal / 'lopy_bench.py').exists())
            self.assertTrue((diagnostic / 'lopy_bench.py').is_file())
            identity = (diagnostic / 'lopy_bench_build.py').read_text(encoding='ascii').strip()
            self.assertEqual(identity, 'MODEL_SHA256 = ' + repr(sha256(DEFAULT_MODEL)))
            self.assertEqual((normal / 'main.py').read_bytes(), (diagnostic / 'main.py').read_bytes())
            self.assertEqual(sha256(diagnostic / 'lib' / 'tg_model_burst.py'), sha256(DEFAULT_MODEL))
            self.assertEqual(bench.model_digest(diagnostic / 'lib' / 'tg_model_burst.py'), sha256(DEFAULT_MODEL))

    def test_log_requires_a_complete_nonconcatenated_run(self):
        start = 'LBD ' + json.dumps({'kind': 'start'})
        with self.assertRaisesRegex(ValueError, 'Expected one complete'):
            analyze([start], 'bench')
        with self.assertRaisesRegex(ValueError, 'Concatenated'):
            analyze([start, start, 'LBD {"kind":"finish"}'], 'bench')


if __name__ == '__main__':
    unittest.main()
