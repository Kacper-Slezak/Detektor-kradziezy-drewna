"""Microphone and optional acceleration diagnostics on the original LoPy."""

from array import array
import gc
import time

try:
    import ujson as json
except ImportError:
    import json

try:
    from tg_burst import BANDS, FEATURES, FRAMES_PER_SECOND, RATE, WINDOW_FRAMES
    from tg_burst import Classifier, Spectrum, Votes, summarize
except ImportError:
    from .tg_burst import BANDS, FEATURES, FRAMES_PER_SECOND, RATE, WINDOW_FRAMES
    from .tg_burst import Classifier, Spectrum, Votes, summarize

SAMPLE_US = 1000000 // RATE
FRAME_US = 1000000 // FRAMES_PER_SECOND


class Monitor:
    def __init__(self, model):
        self.spectrum = Spectrum(model.BURST_SAMPLES)
        self.classifier = Classifier(model)
        self.votes = Votes(model.THRESHOLD, model.SPAN, model.REQUIRED)
        self.frames = array('f', [0]) * (WINDOW_FRAMES * (BANDS + 1))
        self.features = array('f', [0]) * FEATURES
        self.cursor = 0
        self.phase = 0
        self.valid_frames = 0
        self.score = None
        self.confirmed = False

    def invalidate(self):
        self.valid_frames = 0
        self.votes.reset()
        self.score = None
        self.confirmed = False

    def push(self, valid):
        """Consume one quarter-second slot and return true at each one-second hop."""
        if valid:
            self.spectrum.extract(self.frames, self.cursor * (BANDS + 1))
            self.valid_frames = min(self.valid_frames + 1, WINDOW_FRAMES)
        else:
            self.invalidate()
        self.cursor = (self.cursor + 1) % WINDOW_FRAMES
        self.phase = (self.phase + 1) % FRAMES_PER_SECOND
        if self.phase:
            return False
        if self.valid_frames == WINDOW_FRAMES:
            summarize(self.frames, self.features)
            self.score = self.classifier.score(self.features)
            self.confirmed = self.votes.step(self.score)
        return True


def elapsed_us(start):
    return time.ticks_diff(time.ticks_us(), start)


def wait_offset(start, offset):
    elapsed = elapsed_us(start)
    if offset - elapsed > 2000:
        time.sleep_ms((offset - elapsed - 1000) // 1000)
    while elapsed < offset:
        elapsed = elapsed_us(start)
    return elapsed - offset


class BurstClock:
    """The same quarter-second schedule for monitoring and bench capture."""

    def __init__(self, max_slot_late):
        self.max_slot_late = max_slot_late
        self.start = time.ticks_us()
        self.offset = self.slots = 0

    def next(self):
        delay = wait_offset(self.start, self.offset)
        now = time.ticks_us()
        skipped = 0
        if delay > self.max_slot_late:
            skipped = 1 + delay // FRAME_US
            self.start, self.offset, self.slots = now, 0, 0
        self.slots += 1
        if self.slots == FRAMES_PER_SECOND:
            self.start, self.offset, self.slots = now, FRAME_US, 0
        else:
            self.offset += FRAME_US
        return now, delay, skipped

    def slack_us(self):
        return self.offset - elapsed_us(self.start)


def capture(adc, pcm, start, max_late, wait=wait_offset):
    """Read a fixed-size ADC block. Count late samples and clipped endpoints."""
    late, clipped = 0, 0
    for i in range(len(pcm)):
        if wait(start, i * SAMPLE_US) > max_late:
            late += 1
        raw = adc()
        if raw == 0 or raw == 4095:
            clipped += 1
        pcm[i] = (raw << 4) - 32768
    return late, clipped


def emit(fields):
    print('TG ' + json.dumps(fields))


def main():
    import config
    import tg_model_burst as model
    from tg_hardware import SensorHub

    if (config.ENABLE_PHYSICAL_ALARM or config.ALARM_OUTPUT_PIN
            or config.AUDIO_RATE_HZ != RATE or config.WINDOW_S != 2 or config.HOP_S != 1):
        raise ValueError('Burst mode requires diagnostic-only 4 kHz, 2 s windows and 1 s hops')
    hub = SensorHub(config)
    monitor = Monitor(model)
    pcm = monitor.spectrum.pcm
    gc.collect()
    emit(dict(type='status', state='READY_DIAGNOSTIC_ONLY', heap_free=gc.mem_free()))
    clock = BurstClock(config.BURST_MAX_SLOT_LATE_US)
    late_sum = clipped_sum = missed = compute_peak = 0
    accel = None
    while True:
        now, _, skipped = clock.next()
        if skipped:
            missed += skipped
            monitor.invalidate()
        late, clipped = capture(hub.audio, pcm, now, config.BURST_MAX_SAMPLE_LATE_US)
        late_sum += late
        clipped_sum += clipped
        compute_start = time.ticks_us()
        ready = monitor.push(late <= len(pcm) * config.MAX_LATE_SAMPLES_RATIO)
        if hub.accel is not None:
            try:
                accel = hub.accel.read_g()
            except OSError:
                accel = None
        gc.collect()
        compute_peak = max(compute_peak, elapsed_us(compute_start))
        if ready:
            hit = monitor.score is not None and monitor.score >= model.THRESHOLD
            emit(dict(type='window', valid=monitor.score is not None, score=monitor.score,
                      detected=hit, confirmed=monitor.confirmed, votes=monitor.votes.count,
                      accel_g=accel, heap_free=gc.mem_free(), late_samples=late_sum,
                      missed_slots=missed, clipped_samples=clipped_sum, compute_us=compute_peak))
            late_sum = clipped_sum = missed = compute_peak = 0
