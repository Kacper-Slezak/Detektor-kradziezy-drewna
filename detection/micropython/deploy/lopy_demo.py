"""Standalone on-device deployment smoke test for Pycom LoPy 1.0.

Compatible with Pycom MicroPython 1.20.2.r6 (MicroPython v1.11) and CPython.
Does NOT require a microphone, vibration sensor, Wi-Fi, or backend.
Does NOT modify main.py or boot.py.

Usage on LoPy REPL:
    import sys
    sys.path.insert(0, '/flash/tg_demo')
    import lopy_demo
    lopy_demo.run('burst')    # or lopy_demo.run('cnn_v46')
"""

import gc
import math
import time


def _mem_free():
    gc.collect()
    if hasattr(gc, 'mem_free'):
        return gc.mem_free()
    return -1


def _ticks_ms():
    if hasattr(time, 'ticks_ms'):
        return time.ticks_ms()
    return int(time.perf_counter() * 1000)


def _ticks_diff(end, start):
    if hasattr(time, 'ticks_diff'):
        return time.ticks_diff(end, start)
    return end - start


def _fill_synthetic_adc_block(buf, block_idx, lut):
    """Fill reusable 8000-byte bytearray in-place with synthetic 12-bit LE ADC.

    Generates a 4000 Hz mono signal (4000 uint16 LE samples, 0..4095) with
    harmonic engine-like tones using a compact 64-entry LUT (zero allocations).
    """
    lut_len = len(lut)
    idx = 0
    phase = (block_idx * 4000) % lut_len
    for i in range(4000):
        # Fundamental ~62.5 Hz (period 64 samples) + 2nd harmonic ~125 Hz
        s1 = lut[phase]
        s2 = lut[(phase * 2) & 63]
        raw = 2048 + ((s1 * 3 + s2) >> 2)
        if raw < 0:
            raw = 0
        elif raw > 4095:
            raw = 4095
        buf[idx] = raw & 0xFF
        buf[idx + 1] = (raw >> 8) & 0xFF
        idx += 2
        phase = (phase + 1) & 63


def run(variant='auto', num_blocks=10):
    """Execute full streaming detection lifecycle and report heap & timing."""
    print('=== LoPy Deployment Smoke Test (variant=%s) ===' % variant)

    heap_before_import = _mem_free()
    print('HEAP_BEFORE_IMPORT:', heap_before_import)

    from tg_stream_detector import Detector
    heap_after_import = _mem_free()
    print('HEAP_AFTER_IMPORT:', heap_after_import)

    if variant == 'burst':
        import tg_model_burst as model
    elif variant == 'cnn_v46':
        try:
            import tg_model_v46_bin as model
        except ImportError:
            import tg_model_v46 as model
    elif variant == 'auto':
        model = None
        for mod_name in ('tg_model_v46_bin', 'tg_model_burst', 'tg_model_v46'):
            try:
                model = __import__(mod_name)
                break
            except ImportError:
                pass
        if model is None:
            raise ImportError('No model module found in sys.path')
    else:
        raise ValueError('Unknown variant: %s' % variant)

    heap_after_model = _mem_free()
    print('HEAP_AFTER_MODEL:', heap_after_model)

    detector = Detector(model=model)
    heap_after_detector = _mem_free()
    print('HEAP_AFTER_DETECTOR_INIT:', heap_after_detector)

    # Allocate reusable 8000-byte firmware audio buffer + tiny 64-entry LUT
    audio_buf = bytearray(8000)
    lut = [int(900.0 * math.sin(2.0 * math.pi * k / 64.0)) for k in range(64)]
    heap_after_buffers = _mem_free()
    print('HEAP_AFTER_BUFFERS:', heap_after_buffers)

    min_heap = heap_after_buffers
    block_times_ms = []
    total_ms = 0

    for blk in range(num_blocks):
        _fill_synthetic_adc_block(audio_buf, blk, lut)
        t0 = _ticks_ms()
        step = detector.process(audio_buf)
        dt = _ticks_diff(_ticks_ms(), t0)
        block_times_ms.append(dt)
        total_ms += dt
        h_now = _mem_free()
        if min_heap < 0 or (h_now >= 0 and h_now < min_heap):
            min_heap = h_now
        print(
            'BLOCK %02d: time_ms=%d score=%s rms=%s heap_free=%d'
            % (blk, dt, str(step['score']), str(step['block_rms']), h_now)
        )

    t_fin = _ticks_ms()
    result = detector.finalize(vib_active=False, mic_active=True)
    fin_ms = _ticks_diff(_ticks_ms(), t_fin)
    heap_after_finalize = _mem_free()

    print('FINALIZE_MS:', fin_ms)
    print('TOTAL_INFERENCE_MS:', total_ms)
    print('MIN_HEAP_DURING_INFERENCE:', min_heap)
    print('HEAP_AFTER_FINALIZE:', heap_after_finalize)
    print('RESULT:', result)

    # Demonstrate reset and detector reuse (check for persistent memory growth)
    detector.reset()
    heap_after_reset = _mem_free()
    for blk in range(2):
        _fill_synthetic_adc_block(audio_buf, blk, lut)
        detector.process(audio_buf)
    result2 = detector.finalize(vib_active=False, mic_active=True)
    heap_after_reuse = _mem_free()

    print('HEAP_AFTER_RESET:', heap_after_reset)
    print('HEAP_AFTER_REUSE_2BLK:', heap_after_reuse)
    print('REUSE_BLOCKS_PROCESSED:', result2['blocks_processed'])
    print('=== SMOKE TEST COMPLETE ===')
    return result


if __name__ == '__main__':
    run('auto', num_blocks=10)
