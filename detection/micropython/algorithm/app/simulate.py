"""Offline, deterministic test harness for the REAL firmware feature pipeline.

Run from the project directory:
    python -m algorithm.app.simulate --scenario loading --mode fusion
    python -m algorithm.app.simulate --scenario engine_only --mode audio
    python -m algorithm.app.simulate --audio-wav recording.wav --mode audio

WAV input is read in small blocks until EOF. The same 2-second / 1-second
sliding windows and stateful detector are used for offline and live monitoring.

Uses the same IIRAudio -> Chunk -> build_window -> Detector as the LoPy.
This does NOT emulate ADC timing, ADC electrical behavior, I2C or Pycom firmware.
"""
import argparse
import csv
import itertools
import math
from pathlib import Path
import sys
import wave

PROJECT = Path(__file__).resolve().parents[2]
# Compatibility shim: the live firmware uses bare MicroPython imports from /flash/lib.
sys.path.insert(0, str(PROJECT / 'algorithm' / 'legacy_firmware'))
sys.path.insert(0, str(PROJECT / 'algorithm' / 'legacy_firmware' / 'lib'))

import config
from algorithm.core.tg_features import Chunk, IIRAudio, build_window
from algorithm.core.tg_fusion import Detector
from tg_device import floors, settings

SCENARIOS = ('background', 'engine_only', 'motion_only', 'loading',
             'audio_impacts', 'wind_like', 'whistle_only')
EVENTS = (5.0, 9.0, 13.0)


def _clamp_adc(value):
    return max(0.0, min(1.0, value))


def _pulse(t):
    """0..1 shaped motion event, lasting 250 ms, at each event time."""
    for start in EVENTS:
        dt = t - start
        if 0.0 <= dt < 0.25:
            return math.sin(math.pi * dt / 0.25) ** 2
    return 0.0


def _synthetic_audio(t, scenario):
    background = 0.0025 * math.sin(2 * math.pi * 171.0 * t)
    if scenario == 'wind_like':
        # Colored pseudo-random gusts (deterministic negative example).
        # These numbers are independent, not sine harmonics.
        i = int(round(t * 1000.0))
        colored = 0.0
        for delay in range(12):
            sample_i = i - delay
            q = ((sample_i + 65537) * 1103515245 + 12345) & 0xffffffff
            q ^= q >> 13
            q = (q * 1274126177) & 0xffffffff
            colored += (q / 2147483648.0 - 1.0)
        gust = 0.3 + 0.7 * math.sin(0.7 * t) ** 2
        return _clamp_adc(0.5 + background + 0.65 * gust * colored / 12.0)
    if scenario == 'whistle_only':
        return _clamp_adc(0.5 + 0.22 * math.sin(2 * math.pi * 143 * t))
    engine = 0.0
    if scenario in ('engine_only', 'loading'):
        engine = (0.16 * math.sin(2 * math.pi * 83.0 * t)
                  + 0.022 * math.sin(2 * math.pi * 127.0 * t))
    impact = 0.0
    if scenario == 'audio_impacts':
        p = _pulse(t)
        impact = 0.4 * p * math.sin(2 * math.pi * 210.0 * t)
    return _clamp_adc(0.5 + background + engine + impact)


def _synthetic_vibration(t, scenario):
    if scenario not in ('motion_only', 'loading'):
        return 0.5 + 0.001 * math.sin(2 * math.pi * 9.0 * t)
    p = _pulse(t)
    return _clamp_adc(0.5 + 0.28 * p * math.sin(2 * math.pi * 18.0 * t))


def _synthetic_acceleration(t, scenario):
    if scenario not in ('motion_only', 'loading'):
        return (0.0, 0.0, 1.0)
    p = _pulse(t)
    return (0.30 * p * math.sin(2 * math.pi * 12.0 * t),
            0.12 * p * math.sin(2 * math.pi * 11.0 * t), 1.0)


def _pcm_mono_frames(wav, channels, sample_width, block_frames=4096):
    """Incrementally decode PCM to mono float samples; never load the whole WAV."""
    import struct
    frame_size = channels * sample_width
    scale = float(1 << (8 * sample_width - 1))
    while True:
        block = wav.readframes(block_frames)
        if not block:
            break
        if len(block) % frame_size:
            raise ValueError('Truncated WAV audio frame')
        for offset in range(0, len(block), frame_size):
            total = 0.0
            for channel in range(channels):
                start = offset + channel * sample_width
                part = block[start:start + sample_width]
                if sample_width == 1:
                    value = (part[0] - 128) / 128.0
                elif sample_width == 2:
                    value = struct.unpack('<h', part)[0] / scale
                elif sample_width == 3:
                    value = int.from_bytes(part, 'little', signed=True) / scale
                else:
                    value = struct.unpack('<i', part)[0] / scale
                total += value
            yield total / channels


def iter_pcm_wav_samples(path, target_rate, gain=1.0):
    """Yield ADC-like samples sequentially until WAV EOF (constant RAM).

    The input is real audio, but the ADC mapping is hypothetical. Linear
    Resampling uses box averaging when downsampling; for better anti-aliasing
    preconvert with ffmpeg. Device ADC analog anti-aliasing is separate.
    """
    if target_rate <= 0:
        raise ValueError('Target sample rate must be positive')
    if not math.isfinite(gain) or gain <= 0:
        raise ValueError('WAV gain must be positive and finite')
    with wave.open(str(path), 'rb') as fh:
        channels = fh.getnchannels()
        sample_width = fh.getsampwidth()
        source_rate = fh.getframerate()
        source_frames = fh.getnframes()
        if (fh.getcomptype() != 'NONE' or sample_width not in (1, 2, 3, 4)
                or source_rate <= 0 or channels <= 0):
            raise ValueError('Use uncompressed PCM WAV with 8/16/24/32-bit samples')
        output_count = source_frames * target_rate // source_rate
        if output_count < 2 * target_rate:
            raise ValueError('At least two seconds of WAV audio are required')
        decoded = _pcm_mono_frames(fh, channels, sample_width)
        if source_rate >= target_rate:
            # Streaming box-integrator resampling (anti-alias averaging).
            # Better than sampling one point per output, which aliases birds,
            # rain and other high-frequency sounds into the engine band.
            # For higher-quality FIR resampling, pre-convert with ffmpeg.
            source_index = 0
            sample = next(decoded, None)
            if sample is None:
                raise ValueError('WAV contains no audio samples')
            cursor_units = 0
            for output_index in range(output_count):
                stop_units = (output_index + 1) * source_rate
                total = 0.0
                while cursor_units < stop_units:
                    end_sample_units = (source_index + 1) * target_rate
                    consumed = min(stop_units, end_sample_units) - cursor_units
                    total += sample * consumed
                    cursor_units += consumed
                    if cursor_units >= end_sample_units:
                        source_index += 1
                        if source_index < source_frames:
                            sample = next(decoded, None)
                            if sample is None:
                                raise ValueError('WAV ended unexpectedly')
                yield _clamp_adc(0.5 + 0.4 * gain * total / source_rate)
        else:
            # Linear interpolation if an input has lower rate than device.
            left = next(decoded, None)
            right = next(decoded, None)
            if left is None:
                raise ValueError('WAV contains no audio samples')
            if right is None:
                right = left
            source_index = 0
            for output_index in range(output_count):
                numerator = output_index * source_rate
                index, frac = divmod(numerator, target_rate)
                while source_index < index:
                    source_index += 1
                    left = right
                    right = next(decoded, None)
                    if right is None:
                        right = left
                weight = frac / target_rate
                yield _clamp_adc(0.5 + 0.4 * gain *
                                 (left * (1 - weight) + right * weight))


def read_pcm_wav(path, target_rate, gain=1.0):
    """Compatibility helper for tests; loads the whole resampled WAV in RAM.

    For long recordings use iter_pcm_wav_samples or run_simulation/CLI instead.
    """
    return list(iter_pcm_wav_samples(path, target_rate, gain))


def _full_audio_seconds(samples, rate):
    """Yield complete 1-second blocks; never invent/pad missing end samples."""
    iterator = iter(samples)
    while True:
        block = list(itertools.islice(iterator, rate))
        if len(block) < rate:
            return
        yield block


def read_vibration_csv(path):
    """Parse timestamps (seconds) and normalized analog readings (0..1)."""
    result = []
    with open(path, newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or not {'time_s', 'value'} <= set(reader.fieldnames):
            raise ValueError('Vibration CSV must have columns: time_s,value')
        for row in reader:
            timestamp, value = float(row['time_s']), float(row['value'])
            if not math.isfinite(timestamp) or not math.isfinite(value):
                raise ValueError('Vibration CSV contains nonfinite numbers')
            if not 0 <= value <= 1:
                raise ValueError('Vibration values must be normalized to 0..1')
            if result and timestamp <= result[-1][0]:
                raise ValueError('Vibration timestamps must strictly increase')
            result.append((timestamp, value))
    if len(result) < 2 or result[0][0] > 0:
        raise ValueError('CSV needs >=2 readings, starting at time_s=0')
    return result


def make_vibration_reader(points):
    """Simple linear interpolation with no fictitious extrapolation."""
    index = 0

    def sample(t):
        nonlocal index
        if t < points[0][0] or t > points[-1][0]:
            raise ValueError('Vibration CSV must cover the full simulation duration')
        while index + 1 < len(points) - 1 and points[index + 1][0] < t:
            index += 1
        t0, v0 = points[index]
        t1, v1 = points[index + 1]
        return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return sample


def iter_simulation(scenario='loading', mode='fusion', seconds=None,
                    wav_path=None, vibration_path=None, wav_gain=1.0,
                    use_accel=True, audio_rate=4000):
    """Process one second at a time, yielding completed detector windows.

    WAV: no time cap by default; read blocks until end-of-file.
    Generated signal: default is 18 seconds; --seconds can override either.
    Only complete seconds are processed, because firmware uses 2-s windows.
    """
    if scenario not in SCENARIOS:
        raise ValueError('Unknown scenario: ' + scenario)
    if mode not in ('audio', 'vibration', 'fusion'):
        raise ValueError('Unknown mode: ' + mode)
    rate = audio_rate
    if rate not in (1000, 4000):
        raise ValueError('Supported audio rate is 1000 or 4000 Hz')
    if rate % config.VIBRATION_RATE_HZ or rate % config.ACCEL_RATE_HZ:
        raise ValueError('Configured sample rates must divide audio sample rate')
    if config.WINDOW_S != 2.0 or config.HOP_S != 1.0:
        raise ValueError('Test harness requires window=2s and hop=1s')
    if seconds is not None and seconds < 2:
        raise ValueError('At least two seconds are required')
    if wav_path is not None:
        source = _full_audio_seconds(
            iter_pcm_wav_samples(wav_path, rate, wav_gain), rate)
        timeline = enumerate(source)
        if seconds is not None:
            timeline = itertools.islice(timeline, seconds)
    else:
        duration = 18 if seconds is None else seconds
        timeline = ((t, None) for t in range(duration))

    vib_reader = (make_vibration_reader(read_vibration_csv(vibration_path))
                  if vibration_path else None)
    audio_filter = IIRAudio(rate, config.AUDIO_FRAME_MS)
    detector = Detector(floors(), settings(), mode)
    previous = None
    for whole_second, audio_block in timeline:
        chunk = Chunk(whole_second, has_audio=mode != 'vibration',
                      has_vibration=mode != 'audio',
                      has_accel=mode != 'audio' and use_accel and vib_reader is None)
        for i in range(rate):
            t = whole_second + i / rate
            chunk.total_samples += 1
            if chunk.has_audio:
                audio_value = (audio_block[i] if audio_block is not None
                               else _synthetic_audio(t, scenario))
                hp, bass = audio_filter.update(audio_value)
                chunk.add_audio(hp, bass, audio_filter.frame_samples, audio_filter.spectral,
                                audio_filter.wide_spectral if rate == 4000 else None,
                                rate)
            if chunk.has_vibration and i % (rate // config.VIBRATION_RATE_HZ) == 0:
                chunk.vibration.append(vib_reader(t) if vib_reader else
                                       _synthetic_vibration(t, scenario))
            if chunk.has_accel and i % (rate // config.ACCEL_RATE_HZ) == 0:
                chunk.acceleration.append(_synthetic_acceleration(t, scenario))
        if previous is not None:
            row = build_window(previous, chunk,
                               config.MAX_LATE_SAMPLES_RATIO, rate)
            yield detector.step(row)
        previous = chunk


def run_simulation(scenario='loading', mode='fusion', seconds=None,
                   wav_path=None, vibration_path=None, wav_gain=1.0,
                   use_accel=True, audio_rate=4000):
    """Convenience API returning all rows; for big WAVs use iter_simulation."""
    return list(iter_simulation(scenario, mode, seconds, wav_path,
                                vibration_path, wav_gain, use_accel, audio_rate))


def write_csv(rows, path, on_row=None):
    """Write streamed or in-memory rows without retaining them in memory."""
    iterator = iter(rows)
    first = next(iterator, None)
    if first is None:
        raise ValueError('No full 2-second analysis windows in the recording')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = list(first.keys())
    pending = path.with_name(path.name + '.partial')
    try:
        with pending.open('w', newline='', encoding='utf-8') as fh:
            writer = csv.DictWriter(fh, fieldnames=keys)
            writer.writeheader()
            for row in itertools.chain((first,), iterator):
                writer.writerow(row)
                if on_row is not None:
                    on_row(row)
        # Only publish a complete result (and preserve earlier runs on errors).
        pending.replace(path)
    except BaseException:
        if pending.exists():
            pending.unlink()
        raise
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', choices=SCENARIOS, default=None,
                        help='Default: loading for generated signals, background for your files')
    parser.add_argument('--mode', choices=('audio', 'vibration', 'fusion'),
                        default='fusion')
    parser.add_argument('--seconds', type=int, default=None,
                        help='Optional time limit; default is full WAV or 14 s synthetic')
    parser.add_argument('--audio-wav', type=Path,
                        help='Use your own uncompressed PCM WAV instead of generated audio')
    parser.add_argument('--vibration-csv', type=Path,
                        help='Use CSV time_s,value (0..1), instead of generated vibration')
    parser.add_argument('--wav-gain', type=float, default=1.0)
    parser.add_argument('--audio-rate', type=int, choices=(1000, 4000), default=4000,
                        help='4000 Hz wideband v3 (offline); 1000 Hz LoPy fallback')
    parser.add_argument('--summary-only', action='store_true',
                        help='Suppress per-window console lines; still save CSV')
    parser.add_argument('--no-accel', action='store_true',
                        help='Disable synthetic accelerometer')
    parser.add_argument('--output', type=Path, default=None,
                        help='Output CSV path (default algorithm/results/simulation_*.csv)')
    args = parser.parse_args()
    if not math.isfinite(args.wav_gain) or args.wav_gain <= 0:
        parser.error('--wav-gain must be a positive finite number')
    scenario = args.scenario or ('background' if (args.audio_wav or args.vibration_csv)
                                 else 'loading')
    path = args.output or (PROJECT / 'algorithm' / 'results' /
                           ('simulation_%s_%s.csv' % (scenario, args.mode)))
    stats = {'windows': 0, 'alarms': 0, 'engine_windows': 0}
    print('SCENARIO=%s MODE=%s SOURCE=%s' % (
        scenario, args.mode, 'WAV until EOF' if args.audio_wav else 'synthetic'))
    if not args.summary_only:
        print('%-6s %-23s %-6s %-6s %-6s %-7s %-5s %-5s' %
              ('time', 'state', 'engine', 'impact', 'motion', 'events', 'alarm', 'score'))

    def print_row(row):
        stats['windows'] += 1
        stats['alarms'] += row['alarm']
        stats['engine_windows'] += row['engine_confirmed']
        if not args.summary_only:
            print('%-6.1f %-23s %-6d %-6d %-6d %-7d %-5d %-5.2f' %
                  (row['time_s'], row['state'], row['engine_confirmed'],
                   row['audio_impact'], row['motion_detected'],
                   row['recent_motion_events'], row['alarm'], row['engine_score']), flush=True)

    try:
        write_csv(iter_simulation(scenario, args.mode, args.seconds,
                                  args.audio_wav, args.vibration_csv,
                                  args.wav_gain, not args.no_accel, args.audio_rate),
                  path, on_row=print_row)
    except (OSError, ValueError, EOFError, wave.Error) as error:
        parser.exit(2, 'Simulation error: %s\n' % error)
    print('Windows: %d' % stats['windows'])
    print('Engine confirmed windows: %d' % stats['engine_windows'])
    print('Alarms: %d' % stats['alarms'])
    print('CSV: %s' % path.resolve())
    print('NOTE: ENGINE_SCORE is a heuristic evidence score, NOT a probability.')
    print('NOTE: sample_rate=%d, wideband=%s' % (args.audio_rate, args.audio_rate == 4000))
    print('NOTE: Offline uses minimum config floors, NOT real sensor calibration.')
    if args.audio_wav:
        print('NOTE: The final partial second is not classified (no padding).')
        print('NOTE: WAV amplitude is mapped to a hypothetical ADC input.')
        print('NOTE: WAV downsampling uses box averaging; ffmpeg FIR is preferable.')
    if args.vibration_csv:
        print('NOTE: CSV must contain normalized values from an appropriate sensor.')


if __name__ == '__main__':
    main()
