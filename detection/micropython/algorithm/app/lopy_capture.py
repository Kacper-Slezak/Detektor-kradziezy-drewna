"""Validate and index native LoPy slot recordings without filling acquisition gaps."""

import argparse
from array import array
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
import sys

from algorithm.app.burst_stage_lopy import read_export
from firmware.lib.tg_burst_capture import END, MAGIC, MAX_HEADER_BYTES, RECORD, RECORD_BYTES
from firmware.lib.tg_burst_capture import SATURATED_TIMING, VALID
from firmware.lib.tg_burst_device import FRAME_US, RATE, SAMPLE_US, Monitor


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read_exact(stream, count):
    data = stream.read(count)
    if len(data) != count:
        raise ValueError('Truncated capture or missing final record')
    return data


def read_header(stream):
    if read_exact(stream, len(MAGIC)) != MAGIC:
        raise ValueError('Unknown LoPy capture magic')
    size = struct.unpack('<I', read_exact(stream, 4))[0]
    if not 1 <= size <= MAX_HEADER_BYTES:
        raise ValueError('Invalid header length')
    header = json.loads(read_exact(stream, size).decode('utf-8'))
    if (header['format'], header['rate'], header['sample_period_us'], header['slot_us'],
            header['adc_bits']) != (1, RATE, SAMPLE_US, FRAME_US, 12):
        raise ValueError('Unsupported acquisition geometry')
    if (header['burst_samples'] not in (256, 512)
            or not 0 <= header['max_late_ratio'] <= 1
            or not 0 <= header['max_sample_late_us'] < 65535
            or not 0 <= header['max_slot_late_us'] < FRAME_US):
        raise ValueError('Invalid capture limits')
    return header


@dataclass(frozen=True)
class Slot:
    index: int
    start_us: int
    slot_late_us: int
    abandoned_starts: int
    late_reads: int
    rail_reads: int
    valid: bool
    timing_saturated: bool
    capture_us: int
    payload_offset: int
    pcm: bytes
    timing: tuple
    adc_min: int
    adc_max: int
    adc_sum: int


def read_slots(stream, header):
    count = header['burst_samples']
    payload_bytes = count * 2
    index = elapsed = 0
    while True:
        record = struct.unpack(RECORD, read_exact(stream, RECORD_BYTES))
        seq, delta, delay, abandoned, late, rails, flags, duration = record
        if seq == END:
            if record[1:] != (index, 0, 0, 0, 0, 0, 0) or stream.read(1):
                raise ValueError('Invalid capture footer or trailing data')
            return
        if (seq != index or (delta == 0) != (index == 0)
                or flags & ~(VALID | SATURATED_TIMING) or late > count or rails > count):
            raise ValueError(f'Invalid block header at slot {index}')
        expected_abandoned = (1 + delay // FRAME_US if delay > header['max_slot_late_us'] else 0)
        if abandoned != expected_abandoned:
            raise ValueError(f'Inconsistent scheduling flags at slot {index}')
        elapsed += delta
        payload_offset = stream.tell()
        pcm = read_exact(stream, payload_bytes)
        samples = struct.unpack(f'<{count}h', pcm)
        timing = struct.unpack(f'<{count}H', read_exact(stream, payload_bytes))
        saturated = bool(flags & SATURATED_TIMING)
        valid = bool(flags & VALID)
        if (any(value & 15 for value in samples)
                or rails != sum(value in (-32768, 32752) for value in samples)
                or late != sum(delay > header['max_sample_late_us'] for delay in timing)
                or saturated != (65535 in timing)
                or valid != (late <= count * header['max_late_ratio'])
                or duration < (count - 1) * SAMPLE_US + timing[-1]
                or (not saturated and any(SAMPLE_US + b - a < 0 for a, b in zip(timing, timing[1:])))):
            raise ValueError(f'Inconsistent PCM or timing at slot {index}')
        yield Slot(index, elapsed, delay, abandoned, late, rails, valid, saturated,
                   duration, payload_offset, pcm, timing, (min(samples) + 32768) // 16,
                   (max(samples) + 32768) // 16, (sum(samples) + 32768 * count) // 16)
        index += 1


def scan_capture(path, visit=None):
    pcm_hash = hashlib.sha256()
    slots = invalid = abandoned = 0
    adc_sum = rails = 0
    adc_min, adc_max = 4095, 0
    end_us = 0
    with path.open('rb') as stream:
        header = read_header(stream)
        for slot in read_slots(stream, header):
            slots += 1
            invalid += int(not slot.valid)
            abandoned += slot.abandoned_starts
            adc_min, adc_max = min(adc_min, slot.adc_min), max(adc_max, slot.adc_max)
            adc_sum += slot.adc_sum
            rails += slot.rail_reads
            end_us = slot.start_us + slot.capture_us
            pcm_hash.update(slot.pcm)
            if visit is not None:
                visit(header, slot)
    if not slots:
        raise ValueError('Capture contains no complete slot')
    return dict(header=header, slots=slots, invalid_slots=invalid, abandoned_starts=abandoned,
                adc=dict(min=adc_min, max=adc_max, mean=adc_sum / (slots * header['burst_samples']),
                         rail_reads=rails),
                elapsed_us=end_us, pcm_sha256=pcm_hash.hexdigest(), sha256=sha256(path))


def import_capture(path, output, model_path=None):
    if output.exists():
        raise FileExistsError(output)
    model = read_export(model_path) if model_path is not None else None
    monitor = Monitor(model) if model is not None else None
    with path.open('rb') as raw:
        header = read_header(raw)
    if model is not None and (header['model_sha256'] != sha256(model_path)
                              or header['burst_samples'] != model.BURST_SAMPLES):
        raise ValueError('Replay model does not match the captured model')
    output.mkdir(parents=True)
    with (output / 'slots.csv').open('x', newline='', encoding='utf8') as slots:
        table = csv.writer(slots)
        table.writerow(('slot', 'relative_start_us', 'slot_late_us', 'abandoned_starts',
                        'late_reads', 'rail_reads', 'valid', 'timing_saturated',
                        'capture_us', 'pcm_file_offset', 'timing_file_offset', 'adc_min', 'adc_max'))

        def visit(header, slot):
            table.writerow((slot.index, slot.start_us, slot.slot_late_us, slot.abandoned_starts,
                            slot.late_reads, slot.rail_reads, int(slot.valid), int(slot.timing_saturated),
                            slot.capture_us, slot.payload_offset, slot.payload_offset + len(slot.pcm),
                            slot.adc_min, slot.adc_max))
            if monitor is not None:
                if slot.abandoned_starts:
                    monitor.invalidate()
                samples = array('h')
                samples.frombytes(slot.pcm)
                if sys.byteorder != 'little':
                    samples.byteswap()
                monitor.spectrum.pcm[:] = samples
                if monitor.push(slot.valid):
                    replay.writerow((slot.index, slot.start_us + slot.capture_us,
                                     monitor.score, int(monitor.confirmed)))

        if monitor is None:
            result = scan_capture(path, visit)
        else:
            with (output / 'replay.csv').open('x', newline='', encoding='utf8') as decoded:
                replay = csv.writer(decoded)
                replay.writerow(('last_slot', 'last_block_end_us', 'score', 'confirmed'))
                result = scan_capture(path, visit)
    result['capture_file'] = str(path.resolve())
    (output / 'capture.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--model', type=Path, help='Replay with the matching model export')
    args = parser.parse_args()
    import_capture(args.capture, args.output, args.model)


if __name__ == '__main__':
    main()
