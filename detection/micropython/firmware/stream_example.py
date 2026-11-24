"""Minimal integration example for external firmware (`firmware/main4.py`).

Demonstrates how to connect `nagraj_audio()` to `tg_stream_detector.Detector`
and map the finalized result dictionary to `przygotuj_ramke_alarm()` (V2).

This file lives inside `detection/micropython/firmware/` as a reference
example; external `firmware/main4.py` is NOT modified by this package.
"""

import gc
import struct
import sys

try:
    import time
except ImportError:
    time = None

# Ensure local lib/ is importable on both LoPy (/flash/lib) and desktop PC
if '/flash/lib' not in sys.path:
    sys.path.append('/flash/lib')
try:
    import os
    _local_lib = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib')
    if _local_lib not in sys.path:
        sys.path.insert(0, _local_lib)
except (ImportError, AttributeError, NameError):
    pass

from tg_stream_detector import Detector


def run_detection_session(audio_stream, detector, vib_active=False, mic_active=True):
    """Consume blocks from `nagraj_audio()` without retaining buffer references.

    Parameters:
        audio_stream: iterable yielding 8000-byte uint16 LE 12-bit ADC blocks
            (the same bytearray may be reused on every iteration).
        detector: initialized `Detector` instance.
        vib_active: optional binary wake-up metadata from vibration pin.
        mic_active: optional binary wake-up metadata from microphone DO pin.

    Returns:
        Result dictionary with V2 protocol fields and internal diagnostics.
    """
    detector.reset()
    for audio_chunk in audio_stream:
        detector.process(audio_chunk)
        # Never store `audio_chunk`: nagraj_audio() overwrites it on next yield.
    gc.collect()
    return detector.finalize(vib_active=vib_active, mic_active=mic_active)


def format_v2_alarm_kwargs(result, battery_pct=100):
    """Extract keyword arguments for `firmware/main4.py::przygotuj_ramke_alarm()`."""
    return {
        'event_type': result['event_type'],
        'confidence': result['confidence'],
        'battery_pct': battery_pct,
        'source_bits': result['source_bits'],
        'duration_s': result['duration_s'],
        'energy': result['energy'],
    }


def _demo_stream(num_blocks=10):
    """Desktop smoke-test generator mimicking `nagraj_audio()` buffer reuse."""
    buf = bytearray(8000)
    mid_lo = 2048 & 0xFF
    mid_hi = (2048 >> 8) & 0xFF
    for _ in range(num_blocks):
        for i in range(0, 8000, 2):
            buf[i] = mid_lo
            buf[i + 1] = mid_hi
        yield buf


if __name__ == '__main__':
    import tg_model_burst as default_model
    det = Detector(model=default_model)
    result = run_detection_session(_demo_stream(10), det, vib_active=False, mic_active=True)
    print('Result:', result)
    kwargs = format_v2_alarm_kwargs(result, battery_pct=100)
    body = struct.pack(
        '>BBBHBB',
        kwargs['event_type'],
        kwargs['source_bits'],
        kwargs['confidence'],
        kwargs['duration_s'],
        kwargs['energy'],
        kwargs['battery_pct'],
    )
    print('V2 alarm body hex:', body.hex())
