"""Polling implementation for analog mic, vibration and I2C accelerometer.

Software-timed ADC is experimental on ORIGINAL LoPy. Each analysis window
includes timing diagnostics and invalid data cannot create alarms.
"""
import time
from tg_features import Chunk, IIRAudio
from tg_temporal import TemporalChunk, TemporalFilter


class Sampler:
    def __init__(self, hub, cfg, temporal=False):
        self.temporal = bool(temporal)
        self.hub = hub
        self.cfg = cfg
        self.rate = cfg.AUDIO_RATE_HZ
        if self.rate % cfg.VIBRATION_RATE_HZ or self.rate % cfg.ACCEL_RATE_HZ:
            raise ValueError('Rates must divide AUDIO_RATE_HZ')
        if cfg.WINDOW_S != 2.0 or cfg.HOP_S != 1.0:
            raise ValueError('This streaming implementation requires window=2, hop=1')
        self.vib_every = self.rate // cfg.VIBRATION_RATE_HZ
        self.accel_every = self.rate // cfg.ACCEL_RATE_HZ
        self.period_us = 1000000 // self.rate
        self.audio_filter = (TemporalFilter() if self.temporal else
                             IIRAudio(self.rate, cfg.AUDIO_FRAME_MS))
        self.started_ms = time.ticks_ms()
        self.frame_size = 0 if self.temporal else self.audio_filter.frame_samples
        self.last_due_us = None

    def read_second(self):
        cfg = self.cfg
        hub = self.hub
        begin_ms = time.ticks_ms()
        start_s = time.ticks_diff(begin_ms, self.started_ms) / 1000.0
        ch = (TemporalChunk(start_s) if self.temporal else
              Chunk(start_s, hub.audio is not None,
                    cfg.VIBRATION_INPUT != 'off', hub.accel is not None))
        start_us = time.ticks_us()
        if self.last_due_us is not None:
            expected = time.ticks_add(self.last_due_us, self.period_us)
            ch.start_gap_us = max(0, time.ticks_diff(start_us, expected))
            if ch.start_gap_us > cfg.MAX_PROCESSING_GAP_US:
                # FFT/serial processing interrupted sampling: do not pretend
                # to have acquired a continuous waveform. Fail closed.
                ch.late_samples += self.rate
        for index in range(self.rate):
            due = time.ticks_add(start_us, index * self.period_us)
            while True:
                remaining = time.ticks_diff(due, time.ticks_us())
                if remaining <= 0:
                    break
                if remaining >= 250:
                    time.sleep_us(remaining - 100)
            delay_us = time.ticks_diff(time.ticks_us(), due)
            ch.total_samples += 1
            if index % (self.rate // 25) == 0:
                hub.service_alarm()
            if delay_us > cfg.MAX_SAMPLE_GAP_US:
                ch.late_samples += 1
            if hub.audio is not None:
                if self.temporal:
                    ch.add_sample(self.audio_filter.update(hub.read_audio()))
                else:
                    e, bass = self.audio_filter.update(hub.read_audio())
                    ch.add_audio(e, bass, self.frame_size, self.audio_filter.spectral,
                                 self.audio_filter.wide_spectral if self.rate == 4000 else None,
                                 self.rate)
            if not self.temporal:
                if ch.vibration is not None and index % self.vib_every == 0:
                    ch.vibration.append(hub.read_vibration())
                if ch.acceleration is not None and index % self.accel_every == 0:
                    ch.acceleration.append(hub.accel.read_g())
        self.last_due_us = time.ticks_add(start_us,
                                           (self.rate - 1) * self.period_us)
        # Original LoPy analog ADC has no DMA buffering in this implementation.
        # Processing gaps are detected; real gap-free capture needs DMA/I2S.
        return ch
