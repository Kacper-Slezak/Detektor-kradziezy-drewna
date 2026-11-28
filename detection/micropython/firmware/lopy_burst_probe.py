"""Run from the LoPy REPL with the normal monitor stopped."""

import gc
import time


def snapshot(label, collect=True):
    if collect:
        gc.collect()
    print(label, 'free_bytes', gc.mem_free(), 'allocated_bytes', gc.mem_alloc())


def main():
    snapshot('start')
    import tg_model_burst as model
    from tg_burst_device import Monitor
    from tg_burst import summarize, WINDOW_FRAMES
    snapshot('imports')
    monitor = Monitor(model)
    snapshot('buffers_allocated')
    pcm = monitor.spectrum.pcm
    for i in range(len(pcm)):
        pcm[i] = (i % 37 - 18) * 200
    max_fft_us = max_score_us = 0
    min_free = gc.mem_free()
    for n in range(40):
        gc.collect()
        start = time.ticks_us()
        monitor.spectrum.extract(monitor.frames, 0)
        max_fft_us = max(max_fft_us, time.ticks_diff(time.ticks_us(), start))
        if n == 0:
            snapshot('after_first_fft', collect=False)
        start = time.ticks_us()
        summarize(monitor.frames, monitor.features)
        score = monitor.classifier.score(monitor.features)
        max_score_us = max(max_score_us, time.ticks_diff(time.ticks_us(), start))
        min_free = min(min_free, gc.mem_free())
        if n == 0:
            snapshot('after_first_score', collect=False)
        monitor.push((n % (2 * WINDOW_FRAMES)) != 0)
    snapshot('after_40_iterations')
    print('max_fft_us', max_fft_us, 'max_summary_score_us', max_score_us,
          'minimum_sampled_free_bytes', min_free, 'synthetic_score', score)
    print('Use normal monitoring to measure ADC timing with microphone and peripherals')
