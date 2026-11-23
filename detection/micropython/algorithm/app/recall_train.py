"""Fit burst MLPs using real recordings, with model selection on validation only."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from algorithm.app.burst_evaluate import episodes
from algorithm.app.burst_prepare import all_windows, decode
from algorithm.app.burst_train import (
    clip_events, export, load_baseline_cache, metrics, predict, train, weights_for_sources,
)
from algorithm.app.recall_audio import AUDIO, MANIFEST, recordings, verify
from firmware.lib.tg_burst import FEATURES, RATE

CACHE = Path('algorithm/results/burst/features.npz')
RESULTS = Path('algorithm/results/v4_2_fsc22')
SAMPLES = Path('algorithm/sample_audio')
HIDDEN = 16
FOREST = 'forest-ambience.wav'
FOREST_SHA256 = 'f861cd7b63ee9ad956a57260bf585f191a6efd6de00c6e204ce796dfd704965a'
BACKGROUND_VALIDATION = ('rain-in-forest.wav', 'wind-blowing.wav', 'wind-lake.wav')
# The first two configurations isolate the effect of the added recordings.
CONFIGS = (
    ('local_512', 512, FEATURES, False),
    ('expanded_512', 512, FEATURES, True),
    ('expanded_relative', 512, FEATURES - 1, True),
    ('expanded_256', 256, FEATURES, True),
)
VOTES = ((2, 2), (3, 2), (2, 1))


def fit_mask(rows):
    """Hard exclusion of historical synthetic rows, regardless of cache contents."""
    return np.array([r['split'] == 'train' and r['augmented'] == '0'
                     and ':aug:' not in r['source'] for r in rows], dtype=bool)


def verify_cache(cache, root, labels, splits):
    digest = hashlib.sha256((root / 'windows.csv').read_bytes()).hexdigest()
    if (cache['windows_sha256'].item() != digest or not np.array_equal(cache['labels'], labels)
            or not np.array_equal(cache['splits'], splits)):
        raise ValueError('Burst cache belongs to a different recording split')


def load_additional(manifest, directory, forbidden_hashes):
    """Read only checksum-pinned and time-bounded training excerpts."""
    assets = []
    for row in recordings(manifest):
        if row['sha256'] in forbidden_hashes:
            raise ValueError('Recording already exists in the local corpus: ' + row['file'])
        if row['role'] != 'train':
            continue
        path = directory / row['file']
        verify(path.read_bytes(), row)
        pcm = decode(path)
        start, end = int(row['start_s']) * RATE, int(row['end_s']) * RATE
        if end > len(pcm):
            raise ValueError('Training interval exceeds recording: ' + row['file'])
        assets.append((row, pcm[start:end]))
    if not assets:
        raise ValueError('Manifest has no additional training recordings')
    return assets


def weighted_group(base_weights, extra_groups, fraction):
    # Cap the influence of additional sessions regardless of window count.
    weights = weights_for_sources(np.ones(len(extra_groups), np.int8), extra_groups)
    return weights * (base_weights.sum() * fraction / (1 - fraction) / weights.sum())


def assemble(x, y, groups, forest, extra):
    weights = weights_for_sources(y, groups)
    labels = [y, np.zeros(len(forest), np.int8)]
    inputs = [x, forest]
    sample_weights = [weights, weighted_group(weights[y == 0], ['development_forest'] * len(forest), .15)]
    if extra:
        extra_x = np.concatenate([values for _, values in extra])
        extra_groups = [group for group, values in extra for _ in values]
        inputs.append(extra_x)
        labels.append(np.ones(len(extra_x), np.int8))
        sample_weights.append(weighted_group(weights[y == 1], extra_groups, .15))
    return np.concatenate(inputs), np.concatenate(labels), np.concatenate(sample_weights)


def select_operating_point(labels, rows, scores, backgrounds):
    """Choose recall-first operating points while controlling forest confirmations."""
    fsc22 = np.array([r['source'].startswith('FSC22/') for r in rows])
    best = None
    for step in range(30, 100):
        threshold = step / 100
        hits = scores >= threshold
        stat = metrics(labels, hits)
        forest_rate = float(hits[fsc22].mean())
        for span, required in VOTES:
            event = clip_events(rows, scores, threshold, span, required)
            bg_episodes = sum(len(episodes(raw, threshold, span, required)) for raw in backgrounds)
            viable = stat['recall'] >= .82 and forest_rate <= .06 and bg_episodes == 0
            # Preserve clip recall while penalizing false windows and false clips.
            quality = event['recall'] - 2 * (1 - event['specificity']) - forest_rate
            rank = (viable, quality, stat['recall'], -forest_rate, -bg_episodes)
            if best is None or rank > best[0]:
                best = rank, dict(threshold=threshold, span=span, required=required,
                                  meets_validation_constraints=viable,
                                  windows=stat, clip_events=event,
                                  fsc22_fp=int(hits[fsc22].sum()),
                                  background_confirmations=bg_episodes)
    return best


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    rows, _, _, labels, splits = load_baseline_cache(args.results)
    tr = fit_mask(rows)
    va = splits == 'val'
    groups = np.array([r['source'] for r in rows])
    val_rows = [r for r in rows if r['split'] == 'val']
    manifest_rows = recordings(args.manifest)
    # Original manifest hashes preserve byte-level identity across existing splits.
    with args.original_manifest.open(newline='', encoding='utf-8-sig') as stream:
        original_hashes = {r['sha256'].lower() for r in csv.DictReader(stream)}
    forest_path = args.samples / FOREST
    forest_digest = file_hash(forest_path)
    if forest_digest != FOREST_SHA256 or forest_digest in original_hashes:
        raise ValueError('Expected the pinned development forest recording')
    forest = decode(forest_path)
    negatives = [decode(args.samples / name) for name in BACKGROUND_VALIDATION]
    additional = load_additional(args.manifest, args.audio, original_hashes)
    result = dict(original_train_windows=int(tr.sum()), synthetic_training_windows=0,
                  validation_windows=int(va.sum()), calibration_forest_sha256=forest_digest,
                  frame_cache_sha256=file_hash(args.cache), recording_manifest_sha256=file_hash(args.manifest),
                  training_files=[r['file'] for r in manifest_rows if r['role'] == 'train'],
                  candidates={})
    spectra = {size: ([all_windows(pcm, size) for pcm in negatives], all_windows(forest, size),
                      [(r['group'], all_windows(pcm, size)) for r, pcm in additional])
               for size in {config[1] for config in CONFIGS}}
    fitted_models = {}
    with np.load(args.cache, allow_pickle=False) as cache:
        verify_cache(cache, args.results, labels, splits)
        for name, size, count, expanded in CONFIGS:
            features = cache[f'fft{size}'][:, :count]
            background, calibration, added = spectra[size]
            x, y, w = assemble(features[tr], labels[tr], groups[tr], calibration[:, :count],
                               [(group, all_features[:, :count]) for group, all_features in added] if expanded else [])
            fitted = train(x, y, w, HIDDEN)
            rank, point = select_operating_point(labels[va], val_rows, predict(features[va], fitted),
                                                 [predict(b[:, :count], fitted) for b in background])
            result['candidates'][name] = dict(size=size, inputs=count, added_recordings=expanded,
                                             fit_windows=len(y), **point)
            fitted_models[name] = rank, fitted
    chosen = max(fitted_models, key=lambda name: fitted_models[name][0])
    result['selected'] = chosen
    args.output.mkdir(parents=True)
    for name in dict.fromkeys(('local_512', 'expanded_512', chosen)):
        config = result['candidates'][name]
        path = args.output / f'{name}.py'
        export(path, fitted_models[name][1], config['size'], HIDDEN,
               config['threshold'], config['span'], config['required'])
        config['export_sha256'] = file_hash(path)
    (args.output / 'selection.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=RESULTS)
    parser.add_argument('--cache', type=Path, default=CACHE)
    parser.add_argument('--manifest', type=Path, default=MANIFEST)
    parser.add_argument('--audio', type=Path, default=AUDIO)
    parser.add_argument('--samples', type=Path, default=SAMPLES)
    parser.add_argument('--original-manifest', type=Path,
                        default=Path('algorithm/data/dataset_manifest_fsc22.csv'))
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
