"""Minimal original Pycom LoPy ADC poller for 4 kHz v4.6 diagnostic mode.

Does not import old 1kHz DSP/sensors/ML stacks. No audio DMA. Heavy FFT
runs between seconds, so timing violations invalidate subsequent windows.
"""
import time
from tg_temporal_v46 import RawChunk

class Sampler:
    def __init__(self,hub,cfg):
        self.hub=hub
        self.cfg=cfg
        self.rate=cfg.AUDIO_RATE_HZ
        if self.rate != 4000 or cfg.WINDOW_S != 2.0 or cfg.HOP_S != 1.0:
            raise ValueError('V46 requires 4 kHz, 2-second window, 1-second hop')
        if hub.audio is None:
            raise ValueError('Audio ADC required')
        self.period_us=250
        self.started_ms=time.ticks_ms()
        self.last_due_us=None

    def read_second(self):
        ch=RawChunk(time.ticks_diff(time.ticks_ms(),self.started_ms)/1000.0)
        start_us=time.ticks_us()
        if self.last_due_us is not None:
            expected=time.ticks_add(self.last_due_us,self.period_us)
            ch.start_gap_us=max(0,time.ticks_diff(start_us,expected))
            if ch.start_gap_us>self.cfg.MAX_PROCESSING_GAP_US:
                ch.late_samples+=self.rate
        for idx in range(self.rate):
            due=time.ticks_add(start_us,idx*self.period_us)
            while True:
                remain=time.ticks_diff(due,time.ticks_us())
                if remain<=0:break
                if remain>=250:time.sleep_us(remain-100)
            if time.ticks_diff(time.ticks_us(),due)>self.cfg.MAX_SAMPLE_GAP_US:
                ch.late_samples+=1
            ch.add_sample(self.hub.read_audio())
            ch.total_samples+=1
        self.last_due_us=time.ticks_add(start_us,(self.rate-1)*self.period_us)
        return ch
