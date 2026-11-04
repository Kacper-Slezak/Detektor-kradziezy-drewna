"""Polling implementation for analog mic, vibration and I2C accelerometer.

Software-timed ADC is experimental on ORIGINAL LoPy. Each analysis window
includes timing diagnostics and invalid data cannot create alarms.
"""
import time
from tg_features import Chunk, IIRAudio


class Sampler:
    def __init__(self, hub, cfg):
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
        self.audio_filter = IIRAudio(self.rate, cfg.AUDIO_FRAME_MS)
        self.started_ms = time.ticks_ms()
        self.frame_size = self.audio_filter.frame_samples

    def read_second(self):
        cfg = self.cfg
        hub = self.hub
        begin_ms = time.ticks_ms()
        start_s = time.ticks_diff(begin_ms, self.started_ms) / 1000.0
        ch = Chunk(start_s, hub.audio is not None,
                   cfg.VIBRATION_INPUT != 'off', hub.accel is not None)
        start_us = time.ticks_us()
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
            if delay_us > cfg.MAX_SAMPLE_GAP_US:
                ch.late_samples += 1
            if hub.audio is not None:
                e, bass = self.audio_filter.update(hub.read_audio())
                ch.add_audio(e, bass, self.frame_size)
            if ch.vibration is not None and index % self.vib_every == 0:
                ch.vibration.append(hub.read_vibration())
            if ch.acceleration is not None and index % self.accel_every == 0:
                ch.acceleration.append(hub.accel.read_g())
        # Do not sample overlapping chunks simultaneously; processing takes time.
        return ch
