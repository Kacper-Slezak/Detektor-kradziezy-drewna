"""Opt-in live LoPy diagnostics and SD capture. Run from the stopped REPL."""

from array import array
import gc
import os
import sys
import time

try:
    import ujson as json
except ImportError:
    import json

if __name__ == 'lopy_bench':
    from tg_burst_device import BurstClock, Monitor, capture, elapsed_us, wait_offset
    from tg_burst_device import FRAME_US, RATE, SAMPLE_US
    from tg_burst_capture import CaptureWriter, SATURATED_TIMING, VALID
else:
    from .lib.tg_burst_device import BurstClock, Monitor, capture, elapsed_us, wait_offset
    from .lib.tg_burst_device import FRAME_US, RATE, SAMPLE_US
    from .lib.tg_burst_capture import CaptureWriter, SATURATED_TIMING, VALID


def emit(kind, **fields):
    fields['kind'] = kind
    print('LBD ' + json.dumps(fields))


class TimedWait:
    """Store unsigned lateness from the existing ADC wait, with no per-read logging."""

    def __init__(self, samples):
        self.lateness = array('H', [0]) * samples
        self.saturated = False

    def wait(self, start, target):
        delay = wait_offset(start, target)
        if delay >= 65535:
            self.saturated = True
        self.lateness[target // SAMPLE_US] = min(delay, 65535)
        return delay


class Stats:
    def __init__(self):
        self.totals = dict(slots=0, reads=0, late_reads=0, rail_reads=0, invalid_blocks=0,
                           abandoned_starts=0, timing_saturation_slots=0, overruns=0,
                           decisions=0, i2c_reads=0, i2c_errors=0, timed_intervals=0,
                           timed_span_us=0, max_adc_gap_us=0, max_adc_late_us=0,
                           max_slot_late_us=0, max_fft_us=0, max_score_us=0,
                           max_score_ready_us=0, max_accel_us=0, max_sd_us=0, max_gc_us=0,
                           max_capture_us=0, heap_alloc_peak=0)
        self.min_slack_us = FRAME_US
        self.min_free = self.post_gc_min = self.post_gc_now = gc.mem_free()
        self.max_span = 0
        self.min_span = None

    def heap(self, post=False):
        free = gc.mem_free()
        self.min_free = min(self.min_free, free)
        self.maximum('heap_alloc_peak', gc.mem_alloc())
        if post:
            self.post_gc_min = min(self.post_gc_min, free)
            self.post_gc_now = free

    def maximum(self, key, value):
        self.totals[key] = max(self.totals[key], value)

    def acquisition(self, delay, skipped, late, rails, valid, waiter):
        t = self.totals
        lags = waiter.lateness
        t['slots'] += 1
        t['reads'] += len(lags)
        t['late_reads'] += late
        t['rail_reads'] += rails
        t['invalid_blocks'] += int(not valid)
        t['abandoned_starts'] += skipped
        t['timing_saturation_slots'] += int(waiter.saturated)
        self.maximum('max_slot_late_us', delay)
        self.maximum('max_adc_late_us', max(lags))
        if not waiter.saturated:
            intervals = len(lags) - 1
            span = intervals * SAMPLE_US + lags[-1] - lags[0]
            t['timed_intervals'] += intervals
            t['timed_span_us'] += span
            self.max_span = max(self.max_span, span)
            self.min_span = span if self.min_span is None else min(self.min_span, span)
            gap = 0
            for i in range(1, len(lags)):
                gap = max(gap, SAMPLE_US + lags[i] - lags[i - 1])
            self.maximum('max_adc_gap_us', gap)

    def after_slot(self, slack):
        self.min_slack_us = min(self.min_slack_us, slack)
        self.totals['overruns'] += int(slack < 0)

    def report(self, elapsed):
        return dict(self.totals, elapsed_us=elapsed, min_slack_us=self.min_slack_us,
                    min_burst_span_us=self.min_span, max_burst_span_us=self.max_span,
                    heap_free_low=self.min_free, heap_post_gc_low=self.post_gc_min,
                    heap_post_gc_now=self.post_gc_now)


class MeasuredSpectrum:
    def __init__(self, spectrum, stats):
        self.inner, self.stats = spectrum, stats
        self.pcm = spectrum.pcm

    def extract(self, frames, offset):
        start = time.ticks_us()
        self.inner.extract(frames, offset)
        self.stats.maximum('max_fft_us', elapsed_us(start))
        self.stats.heap()


class MeasuredClassifier:
    def __init__(self, classifier, stats):
        self.inner, self.stats = classifier, stats

    def score(self, features):
        start = time.ticks_us()
        result = self.inner.score(features)
        self.stats.maximum('max_score_us', elapsed_us(start))
        self.stats.totals['decisions'] += 1
        self.stats.heap()
        return result


def fragmentation_probe(size):
    """One fixed contiguous allocation after GC; indicative of headroom only."""
    gc.collect()
    before = gc.mem_free()
    ok = False
    try:
        block = bytearray(size)
        block[0] = 1
        ok = True
        del block
    except MemoryError:
        pass
    gc.collect()
    return dict(request_bytes=size, free_before=before, free_after=gc.mem_free(), ok=ok)


def model_digest(path):
    try:
        import uhashlib as hashlib
        import ubinascii as binascii
    except ImportError:
        import hashlib
        import binascii
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        chunk = stream.read(512)
        while chunk:
            digest.update(chunk)
            chunk = stream.read(512)
    return binascii.hexlify(digest.digest()).decode('ascii')


def run_slots(cfg, monitor, hub, seconds, writer, report_every, stats):
    """Common live loop. The injected objects also permit deterministic desktop tests."""
    pcm = monitor.spectrum.pcm
    waiter = TimedWait(len(pcm))
    wait = waiter.wait
    clock = BurstClock(cfg.BURST_MAX_SLOT_LATE_US)
    previous, elapsed = None, 0
    last_report_elapsed = 0
    index = 0
    accel = None
    completed = False
    try:
        while not seconds or last_report_elapsed < seconds * 1000000:
            start, delay, skipped = clock.next()
            delta = time.ticks_diff(start, previous) if previous is not None else 0
            elapsed += delta
            previous = start
            if skipped:
                monitor.invalidate()
            waiter.saturated = False
            late, rails = capture(hub.audio, pcm, start, cfg.BURST_MAX_SAMPLE_LATE_US, wait)
            capture_us = elapsed_us(start)
            stats.maximum('max_capture_us', capture_us)
            valid = late <= len(pcm) * cfg.MAX_LATE_SAMPLES_RATIO
            stats.acquisition(delay, skipped, late, rails, valid, waiter)
            if monitor.push(valid) and monitor.score is not None:
                stats.maximum('max_score_ready_us', elapsed_us(start))
            if hub.accel is not None:
                before = time.ticks_us()
                stats.totals['i2c_reads'] += 1
                try:
                    accel = hub.accel.read_g()
                except OSError:
                    stats.totals['i2c_errors'] += 1
                    accel = None
                stats.maximum('max_accel_us', elapsed_us(before))
            if writer is not None:
                before = time.ticks_us()
                flags = (VALID if valid else 0) | (SATURATED_TIMING if waiter.saturated else 0)
                writer.slot(index, delta, delay, skipped, late, rails, flags, capture_us, pcm, waiter.lateness)
                if (index + 1) % 32 == 0:
                    writer.stream.flush()
                stats.maximum('max_sd_us', elapsed_us(before))
            index += 1
            stats.heap()
            before = time.ticks_us()
            gc.collect()
            stats.maximum('max_gc_us', elapsed_us(before))
            stats.heap(post=True)
            if report_every and index % report_every == 0:
                emit('summary', stats=stats.report(elapsed), accel_g=accel,
                     score=monitor.score, confirmed=monitor.confirmed)
            stats.after_slot(clock.slack_us())
            last_report_elapsed = elapsed + elapsed_us(start)
        completed = True
    except KeyboardInterrupt:
        pass
    if writer is not None and completed:
        writer.finish(index)
    return completed, last_report_elapsed


def run(seconds=60, record_path=None, session_id='', start_utc='', capture_kind='bench',
        report_every=16, probe_bytes=4096, board_id=''):
    """Run from REPL after Ctrl+C. Capture requires a pre-mounted, writable /sd."""
    import config as cfg
    from tg_hardware import SensorHub
    from lopy_bench_build import MODEL_SHA256
    if model_digest('/flash/lib/tg_model_burst.py') != MODEL_SHA256:
        raise ValueError('Flash model differs from the staged model digest')
    import tg_model_burst as model

    if (cfg.MODEL_FLAVOR != 'burst' or cfg.ENABLE_PHYSICAL_ALARM or cfg.ALARM_OUTPUT_PIN
            or cfg.AUDIO_RATE_HZ != RATE or cfg.WINDOW_S != 2 or cfg.HOP_S != 1):
        raise ValueError('Stage the diagnostic burst build for this bench run')
    if (not isinstance(seconds, int) or seconds < 0 or not isinstance(report_every, int)
            or report_every < 0 or not isinstance(probe_bytes, int) or not 1 <= probe_bytes <= 32768):
        raise ValueError('Invalid run duration, report interval or heap probe size')
    if capture_kind not in ('bench', 'field'):
        raise ValueError('Capture kind must be bench or field')
    if record_path is not None:
        parts = record_path.split('/')
        if (parts[:2] != ['', 'sd'] or len(parts) < 3
                or any(p in ('', '.', '..') for p in parts[2:])
                or not record_path.endswith('.lopy') or not 0 < seconds <= 3600 or not session_id):
            raise ValueError('Recording requires a new /sd/*.lopy file, session ID and duration of 1-3600 s')
        try:
            os.stat(record_path)
        except OSError as exc:
            if exc.args[0] != 2:  # ENOENT on Pycom.
                raise
        else:
            raise ValueError('Recording already exists')
    uname = os.uname()
    metadata = dict(format=1, session_id=session_id, capture_kind=capture_kind,
                    board_id=board_id, implementation=getattr(getattr(sys, 'implementation', None), 'name', 'unknown'),
                    start_utc=start_utc, clock_kind='operator_utc_anchor' if start_utc else 'relative_only',
                    platform=sys.platform, machine=uname.machine, release=uname.release,
                    firmware_version=uname.version, model_sha256=MODEL_SHA256, rate=RATE,
                    burst_samples=model.BURST_SAMPLES, sample_period_us=SAMPLE_US, slot_us=FRAME_US,
                    adc_pin=cfg.AUDIO_PIN, adc_attenuation=cfg.ADC_ATTENUATION, adc_bits=12,
                    accel_enabled=cfg.ACCEL_ENABLED, max_sample_late_us=cfg.BURST_MAX_SAMPLE_LATE_US,
                    accel_pins=[cfg.ACCEL_SDA_PIN, cfg.ACCEL_SCL_PIN],
                    accel_address=cfg.ACCEL_I2C_ADDRESS,
                    max_slot_late_us=cfg.BURST_MAX_SLOT_LATE_US,
                    max_late_ratio=cfg.MAX_LATE_SAMPLES_RATIO, requested_seconds=seconds,
                    recording=record_path is not None, threshold=model.THRESHOLD,
                    span=model.SPAN, required=model.REQUIRED)
    hub = SensorHub(cfg)
    monitor = Monitor(model)
    stats = Stats()
    monitor.spectrum = MeasuredSpectrum(monitor.spectrum, stats)
    monitor.classifier = MeasuredClassifier(monitor.classifier, stats)
    stream = None
    try:
        if record_path is not None:
            stream = open(record_path, 'wb')
        writer = CaptureWriter(stream, metadata) if stream is not None else None
        initial = fragmentation_probe(probe_bytes)
        emit('start', metadata=metadata, allocation=initial)
        done, elapsed = run_slots(cfg, monitor, hub, seconds, writer, report_every, stats)
        final = fragmentation_probe(probe_bytes)
        emit('finish', completed=done, stats=stats.report(elapsed), allocation=final)
    finally:
        if stream is not None:
            stream.close()
