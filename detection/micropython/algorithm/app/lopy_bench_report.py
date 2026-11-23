"""Summarize a logged LoPy run against the proposed bench acceptance gates."""

import argparse
import json
from pathlib import Path

PROFILES = {'bench': 900, 'sd': 300, 'soak': 28800}
COUNTERS = ('slots', 'reads', 'late_reads', 'abandoned_starts', 'invalid_blocks',
            'overruns', 'decisions', 'i2c_reads', 'i2c_errors')


def original_lopy(metadata):
    machine = metadata.get('machine', '').lower()
    return (metadata.get('implementation') == 'micropython' and 'lopy' in machine
            and 'lopy4' not in machine.replace(' ', '') and 'esp32' in machine)


def analyze(lines, profile):
    events = [json.loads(line.split('LBD ', 1)[1]) for line in lines
              if line.lstrip().startswith('LBD ')]
    if len(events) < 2 or events[0]['kind'] != 'start' or events[-1]['kind'] != 'finish':
        raise ValueError('Expected one complete start/summary/finish run')
    if any(event['kind'] != 'summary' for event in events[1:-1]):
        raise ValueError('Concatenated runs or unexpected log event')
    start, final = events[0], events[-1]
    metadata, totals = start['metadata'], final['stats']
    snapshots = [event['stats'] for event in events[1:-1]]
    for a, b in zip(snapshots, [*snapshots[1:], totals]):
        if b['elapsed_us'] < a['elapsed_us'] or any(b[k] < a[k] for k in COUNTERS):
            raise ValueError('Nonmonotonic bench counters')
    reads = totals['reads']
    slots = totals['slots']
    rate = totals['timed_intervals'] * 1000000 / max(1, totals['timed_span_us'])
    drift = max(0, snapshots[0]['heap_post_gc_now'] - totals['heap_post_gc_low']) if snapshots else None
    late_fraction = totals['late_reads'] / max(1, reads)
    rail_fraction = totals['rail_reads'] / max(1, reads)
    elapsed_s = totals['elapsed_us'] / 1000000
    capture_intervals = metadata['burst_samples'] - 1
    nominal_span = capture_intervals * 250
    accel_checks = (totals['i2c_reads'] == slots and totals['i2c_errors'] == 0
                    if metadata['accel_enabled'] else totals['i2c_reads'] == 0)
    checks = {
        'complete_duration': final['completed'] and elapsed_s >= PROFILES[profile],
        'profile_matches_sd_state': bool(metadata['recording']) == (profile == 'sd'),
        'configured_adc_geometry': (metadata['rate'], metadata['sample_period_us'], metadata['slot_us'],
                                    metadata['adc_bits']) == (4000, 250, 250000, 12)
                                    and metadata['burst_samples'] in (256, 512),
        'trend_snapshots': len(snapshots) >= 3,
        'read_counts': slots > 0 and reads == slots * metadata['burst_samples'],
        'rate_within_one_percent': 3960 <= rate <= 4040,
        'burst_timing': (totals['timing_saturation_slots'] == 0
                         and totals['timed_intervals'] == slots * capture_intervals
                         and totals['min_burst_span_us'] is not None
                         and totals['min_burst_span_us'] >= .99 * nominal_span
                         and totals['max_burst_span_us'] <= 1.01 * nominal_span
                         and totals['max_adc_gap_us'] <= 500 and late_fraction <= .001),
        'rail_fraction': rail_fraction <= .001,
        'slot_deadlines': (totals['abandoned_starts'] == totals['overruns'] == totals['invalid_blocks'] == 0
                           and totals['min_slack_us'] >= 10000),
        'decision_count_and_latency': (totals['decisions'] == max(0, slots // 4 - 1)
                                        and 0 < totals['max_score_ready_us'] <= 240000),
        'accelerometer': accel_checks,
        'heap_headroom': (totals['heap_free_low'] >= 8192
                          and start['allocation']['request_bytes'] == final['allocation']['request_bytes'] == 4096
                          and start['allocation']['ok'] and final['allocation']['ok']),
        'heap_drift': drift is not None and drift <= 1024,
    }
    return dict(profile=profile, original_lopy_identity_reported=original_lopy(metadata),
                measurement_platform=metadata.get('platform'), board_id=metadata.get('board_id'),
                numerical_gates_pass=all(checks.values()), checks=checks, elapsed_s=elapsed_s,
                effective_in_burst_hz=rate, late_fraction=late_fraction, rail_fraction=rail_fraction,
                estimated_unread_samples_at_abandoned_starts=totals['abandoned_starts'] * metadata['burst_samples'],
                post_gc_drop_bytes=drift, metadata=metadata, totals=totals,
                allocation_start=start['allocation'], allocation_end=final['allocation'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('--profile', choices=PROFILES, required=True)
    args = parser.parse_args()
    with args.log.open(encoding='utf-8-sig', errors='replace') as stream:
        result = analyze(stream, args.profile)
    print(json.dumps(result, indent=2))
    if not result['numerical_gates_pass'] or not result['original_lopy_identity_reported']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
