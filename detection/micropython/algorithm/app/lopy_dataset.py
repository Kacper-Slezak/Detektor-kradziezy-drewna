"""Validate field labels and freeze recording-session splits for LoPy native captures."""

import argparse
from datetime import date, datetime
import json
import math
from pathlib import Path
import re

from algorithm.app.lopy_bench_report import original_lopy
from algorithm.app.lopy_capture import scan_capture

LABELS = frozenset(('diesel', 'truck', 'tractor', 'other_vehicle', 'background',
                    'wind', 'rain', 'chainsaw', 'generator', 'aircraft', 'other_negative', 'uncertain'))
SPLITS = frozenset(('train', 'validation', 'test'))


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', value):
        raise ValueError(f'Invalid identifier: {value!r}')
    return value


def session_registry(values):
    sessions, groups, associations = {}, {}, {}
    for session in values:
        key = identifier(session['session_id'])
        group = identifier(session['group_id'])
        site = identifier(session['site_id'])
        day = date.fromisoformat(session['site_date']).isoformat()
        if day != session['site_date']:
            raise ValueError('Use YYYY-MM-DD for the local site date')
        split = session['split']
        exposure = session['exposure']
        vehicles = session['vehicle_ids']
        if (key in sessions or split not in SPLITS
                or exposure not in ('fresh', 'exposed') or (split == 'test' and exposure != 'fresh')
                or not isinstance(vehicles, list)):
            raise ValueError('Invalid or duplicate session: ' + key)
        if groups.setdefault(group, split) != split:
            raise ValueError('Grouping crosses splits: ' + group)
        tokens = [('site_date', site, day)] + [('vehicle', identifier(vehicle)) for vehicle in vehicles]
        for token in tokens:
            if associations.setdefault(token, group) != group:
                raise ValueError('Same known vehicle or site/date must share a group: ' + str(token))
        sessions[key] = dict(session, vehicle_ids=sorted(set(vehicles)))
    if not sessions:
        raise ValueError('Expected at least one field session')
    return sessions


def validate_labels(intervals, duration, file):
    ordered = sorted(intervals, key=lambda item: item['start_s'])
    prior = 0
    for event in ordered:
        start, end = event['start_s'], event['end_s']
        distance = event.get('distance_m')
        if (event['label'] not in LABELS or not math.isfinite(start) or not math.isfinite(end)
                or not prior <= start < end <= duration
                or (distance is not None and (not math.isfinite(distance) or distance <= 0))):
            raise ValueError('Invalid, overlapping or out-of-bounds label in ' + file)
        prior = end
    return ordered


def validate_utc(value):
    try:
        timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (AttributeError, ValueError) as exc:
        raise ValueError('Field capture needs an ISO 8601 UTC anchor') from exc
    if timestamp.utcoffset() is None or timestamp.utcoffset().total_seconds() != 0:
        raise ValueError('Use an explicit UTC offset or Z for the capture anchor')


def enforce_history(previous, current):
    original = {s['session_id']: s for s in previous['sessions']}
    updated = {s['session_id']: s for s in current['sessions']}
    committed_files = {row['file']: row for row in previous['recordings']}
    current_files = {row['file']: row for row in current['recordings']}
    for key, session in original.items():
        if updated.get(key) != session:
            raise ValueError('Prior session assignment changed: ' + key)
    protected = ('session_id', 'sha256', 'pcm_sha256')
    for file, record in committed_files.items():
        if file not in current_files or any(record[k] != current_files[file][k] for k in protected):
            raise ValueError('Prior recording identity changed: ' + file)
    final_files = {f for f, row in committed_files.items() if original[row['session_id']]['split'] == 'test'}
    if final_files:
        updated_final = {f for f, row in current_files.items() if updated[row['session_id']]['split'] == 'test'}
        if final_files != updated_final or any(committed_files[f] != current_files[f] for f in final_files):
            raise ValueError('The previously registered final test is locked')


def create_manifest(catalog_path, previous=None):
    catalog_root = catalog_path.parent.resolve()
    catalog = json.loads(catalog_path.read_text(encoding='utf-8-sig'))
    sessions = session_registry(catalog['sessions'])
    recordings, pcm_hashes, covered = {}, set(), set()
    for item in catalog['recordings']:
        file = item['file'].replace('\\', '/')
        session_id = item['session_id']
        path = (catalog_root / file).resolve()
        if (not path.is_relative_to(catalog_root) or Path(file).is_absolute() or file in recordings
                or path.suffix != '.lopy' or any(p in ('', '.', '..') for p in file.split('/'))):
            raise ValueError('Expected a unique relative .lopy file: ' + file)
        if (session_id not in sessions or not item['annotation_source'].strip()
                or not item['sync_method'].strip() or not math.isfinite(item['sync_uncertainty_s'])
                or item['sync_uncertainty_s'] < 0):
            raise ValueError('Missing session, annotation source or sync information: ' + file)
        trace = scan_capture(path)
        header = trace['header']
        if (header['session_id'] != session_id or header['capture_kind'] != 'field'
                or not original_lopy(header) or header['clock_kind'] != 'operator_utc_anchor'):
            raise ValueError('Expected field capture from the registered LoPy session: ' + file)
        validate_utc(header['start_utc'])
        if trace['pcm_sha256'] in pcm_hashes:
            raise ValueError('Duplicate PCM across registered captures: ' + file)
        pcm_hashes.add(trace['pcm_sha256'])
        covered.add(session_id)
        events = validate_labels(item['events'], trace['elapsed_us'] / 1000000, file)
        recordings[file] = dict(item, **trace, file=file, events=events)
    if covered != set(sessions):
        raise ValueError('Every session must have at least one valid capture')
    document = dict(format=1, sessions=[sessions[key] for key in sorted(sessions)],
                    recordings=[recordings[file] for file in sorted(recordings)])
    if previous is not None:
        enforce_history(previous, document)
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--previous', type=Path, help='Prior manifest to enforce frozen assignments')
    args = parser.parse_args()
    previous = json.loads(args.previous.read_text(encoding='utf-8-sig')) if args.previous else None
    manifest = create_manifest(args.catalog, previous)
    with args.output.open('x', encoding='utf8') as stream:
        json.dump(manifest, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
