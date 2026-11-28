"""Compare three small logistic probes on the original development split."""

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from algorithm.app._dataset_utils import locate_archive, manifest_rows
from algorithm.app.burst_prepare import read_original
from algorithm.app.burst_train import load_baseline_cache, metrics, predict, train, weights_for_sources
from algorithm.app.engine_diagnose import DATA, SOURCE_MANIFEST, auc
from algorithm.app.engine_event_audit import clip_comparison
from algorithm.app.recall_train import RESULTS, file_hash, fit_mask
from algorithm.app.spectral_features import extract

CONFIGS = {'bands_rms': 32, 'spectral': 36, 'spectral_ordered': 40}


def choose_sources(records, allowed_sources):
    # Deterministic source sample. Keep all windows from any selected recording.
    groups = defaultdict(list)
    for key, record in records.items():
        if record['split'] == 'train' and key in allowed_sources:
            groups[(record['dataset'], record['category'], record['target_engine'])].append(key)
    sizes = {'0': 8, '1': 64}
    return {key for group, names in groups.items() for key in
            sorted(names, key=lambda name: hashlib.sha256(name.encode()).digest())[:sizes[group[2]]]}


def load_features(root, manifest, data_dir):
    rows, _, _, _, _ = load_baseline_cache(root)
    _, chosen = manifest_rows(manifest)
    records = {r['dataset'] + '/' + r['audio_member']: r for r in chosen if r['split'] in ('train', 'val')}
    allowed = {row['source'] for row, good in zip(rows, fit_mask(rows)) if good}
    training = choose_sources(records, allowed)
    by_source = defaultdict(list)
    for row in rows:
        if row['split'] == 'val' or row['source'] in training:
            by_source[row['source']].append(row)

    with ExitStack() as stack:
        paths = {locate_archive(records[key], data_dir) for key in by_source}
        archives = {path: stack.enter_context(ZipFile(path)) for path in paths}

        def examine(item):
            key, windows = item
            record = records[key]
            raw = archives[locate_archive(record, data_dir)].read(record['audio_member'])
            if hashlib.sha256(raw).hexdigest() != record['sha256'].lower():
                raise ValueError('Recording changed: ' + key)
            seconds = [float(row['time_s']) for row in windows]
            if any(not s.is_integer() or s < 0 for s in seconds):
                raise ValueError('Unexpected window time: ' + key)
            values = extract(read_original(raw))[np.asarray(seconds, dtype=int)]
            return record['split'], windows, values

        with ThreadPoolExecutor(max_workers=4) as executor:
            parts = list(executor.map(examine, by_source.items()))
    return {split: ([row for part in parts if part[0] == split for row in part[1]],
                    np.concatenate([part[2] for part in parts if part[0] == split]))
            for split in ('train', 'val')}


def export(path, fitted, threshold):
    mean, inverse, weights, scale, biases = fitted
    constants = dict(FEATURE_VERSION=2, INPUTS=len(mean), THRESHOLD=threshold,
                     MEAN=tuple(map(float, mean)), INVERSE_STD=tuple(map(float, inverse)),
                     WEIGHTS=weights[0].ravel().tobytes(), SCALE=scale[0], BIAS=float(biases[0][0]))
    with path.open('x', encoding='ascii', newline='\n') as stream:
        stream.write('"""Fixed development logistic probe. For bench diagnostics."""\n')
        for key, value in constants.items():
            stream.write(f'{key} = {value!r}\n')


def choose_threshold(rows, labels, scores):
    best = None
    for i in range(20, 96):
        threshold = i / 100
        by_clip = clip_comparison(rows, scores, threshold, (2, 2))['native']
        recall = by_clip['engine']['confirmed'] / by_clip['engine']['eligible']
        false_rate = by_clip['negative']['confirmed'] / by_clip['negative']['eligible']
        stats = metrics(labels, scores >= threshold)
        rank = (false_rate <= .05 and stats['recall'] >= .80,
                recall - 2 * false_rate, stats['f1'], -false_rate)
        if best is None or rank > best[0]:
            best = rank, dict(threshold=threshold, window_metrics=stats, event_metrics=by_clip)
    return best


def fit_probes(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    data = load_features(args.results, args.manifest, args.data)
    train_rows, x = data['train']
    val_rows, y = data['val']
    train_labels = np.array([int(row['label']) for row in train_rows], dtype=np.int8)
    val_labels = np.array([int(row['label']) for row in val_rows], dtype=np.int8)
    groups = [row['source'] for row in train_rows]
    weights = weights_for_sources(train_labels, groups)
    summary = {'train_windows': len(x), 'train_sources': len(set(groups)), 'val_windows': len(y),
               'train_sources_by_class': {str(label): len({group for group, value in
                    zip(groups, train_labels) if value == label}) for label in (0, 1)},
               'input_manifest_sha256': file_hash(args.manifest), 'probes': {}}
    args.output.mkdir(parents=True)
    for name, count in CONFIGS.items():
        fitted = train(x[:, :count], train_labels, weights, hidden=0)
        scores = predict(y[:, :count], fitted)
        _, point = choose_threshold(val_rows, val_labels, scores)
        path = args.output / f'{name}.py'
        export(path, fitted, point['threshold'])
        point.update(inputs=count, auc=auc(scores[val_labels == 1], scores[val_labels == 0]),
                     export_sha256=file_hash(path), source_bytes=path.stat().st_size)
        summary['probes'][name] = point
    (args.output / 'frozen.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf8')
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=RESULTS)
    parser.add_argument('--manifest', type=Path, default=SOURCE_MANIFEST)
    parser.add_argument('--data', type=Path, default=DATA)
    parser.add_argument('--output', type=Path, required=True)
    fit_probes(parser.parse_args())


if __name__ == '__main__':
    main()
