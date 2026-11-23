"""Score frozen real-only exports against the unchanged historical benchmarks."""

import argparse
import json
from pathlib import Path

import numpy as np

from algorithm.app.burst_evaluate import (
    BACKGROUND, TIMED, UNTIMED, baseline_predict, episodes, portable_predict, summary,
)
from algorithm.app.burst_prepare import HOP, all_windows, decode
from algorithm.app.burst_stage_lopy import DEFAULT_MODEL, read_export
from algorithm.app.burst_train import (
    baseline_scores, clip_events, evaluation, load_baseline_cache, metrics, stress_baseline,
)
from algorithm.app.recall_audio import AUDIO, MANIFEST, recordings, verify
from algorithm.app.recall_train import CACHE, RESULTS, SAMPLES, file_hash, verify_cache
from algorithm.app.v4_6_infer import load_model
from firmware.lib.tg_burst import Classifier, RATE

BASELINE = Path('algorithm/results/v4_6_wideband/tg_model_v46.py')


def predict_export(model, features):
    scorer = Classifier(model)
    return np.fromiter((scorer.score(x) for x in features), dtype=float, count=len(features))


def by_group(rows, scores, threshold):
    target = {}
    labels = np.array([int(r['label']) for r in rows])
    for group in sorted({r['group'] for r in rows}):
        mask = np.array([r['group'] == group for r in rows])
        target[group] = metrics(labels[mask], scores[mask] >= threshold)
    return target


def scored_holdout(labels, rows, scores, stress, threshold, span, required):
    return dict(windows=evaluation(labels, scores, rows, stress, threshold),
                clip_confirmations=clip_events(rows, scores, threshold, span, required),
                windows_by_label_group=by_group(rows, scores, threshold))


def phase_diagnostic(pcm, model):
    """Vary the capture start within its slot, on a fixed set of window times."""
    last = HOP - model.BURST_SAMPLES
    offsets = np.linspace(0, last, 5, dtype=int)
    count = len(pcm) // RATE - 1
    if count <= 0:
        raise ValueError('Two seconds of audio required for the phase diagnostic')
    # A trailing complete slot can contain fewer than HOP samples after a shift.
    # Appended samples are outside all sampled slices because phase + size <= HOP.
    scores = [predict_export(model, all_windows(np.pad(pcm[offset:], (0, offset)),
                                               model.BURST_SAMPLES)) for offset in offsets]
    hits = np.stack(scores) >= model.THRESHOLD
    return dict(offset_samples=offsets.tolist(), windows=count,
                min_max_score=min(float(max(p)) for p in scores),
                max_score=float(np.max(scores)), hits_per_offset=hits.sum(axis=1).tolist(),
                qualifying_at_any_offset=int(hits.any(axis=0).sum()),
                episodes_per_offset=[len(episodes(p, model.THRESHOLD, model.SPAN, model.REQUIRED))
                                     for p in scores])


def sound_profile(pcm):
    seconds = len(pcm) // RATE
    x = pcm[:seconds * RATE].astype(np.float64).reshape(-1, RATE)
    x -= x.mean(axis=1, keepdims=True)
    power = np.abs(np.fft.rfft(x * np.hanning(RATE), axis=1)) ** 2
    ratio = (power[:, 35:130].sum(axis=1) + 1e-9) / (power[:, 130:800].sum(axis=1) + 1e-9)
    return dict(median_rms_dbfs=float(np.median(20 * np.log10(np.maximum(1, x.std(axis=1)) / 32768))),
                median_35_130_vs_130_800_db=float(np.median(10 * np.log10(ratio))),
                clipped_fraction=float(np.mean(np.abs(pcm.astype(np.float32)) >= 32760)))


def replay(name, pcm, baseline, models):
    duration = len(pcm) / RATE
    baseline_p = baseline_predict(pcm, baseline)
    results = dict(profile=sound_profile(pcm), duration_s=duration,
                   original=summary(baseline_p, baseline.THRESHOLD, 15, 9, duration,
                                    name in BACKGROUND, TIMED.get(name)))
    results['original']['max_score'] = float(max(baseline_p))
    for model_name, model in models.items():
        reference = predict_export(model, all_windows(pcm, model.BURST_SAMPLES))
        scores = np.fromiter(portable_predict(pcm, model), dtype=float)
        delta = float(np.max(np.abs(scores - reference)))
        if delta > .0005 or not np.array_equal(scores >= model.THRESHOLD, reference >= model.THRESHOLD):
            raise ValueError('Portable replay disagreement: ' + name)
        results[model_name] = summary(scores, model.THRESHOLD, model.SPAN, model.REQUIRED,
                                      duration, name in BACKGROUND, TIMED.get(name))
        results[model_name].update(max_score=float(max(scores)), score_max_abs_error=delta)
        if name in TIMED or name in UNTIMED:
            results[model_name]['phase_check'] = phase_diagnostic(pcm, model)
    return results


def evaluate(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    selection = json.loads((args.selection / 'selection.json').read_text(encoding='utf8'))
    # Lock the cache and exports to the preceding validation-only run.
    if selection['frame_cache_sha256'] != file_hash(args.cache):
        raise ValueError('Feature cache changed after model selection')
    if selection['recording_manifest_sha256'] != file_hash(args.manifest):
        raise ValueError('Recording manifest changed after model selection')
    baseline = load_model(args.baseline)
    models = {'previous_burst': read_export(args.previous)}
    for name in dict.fromkeys(('local_512', 'expanded_512', selection['selected'])):
        export = args.selection / f'{name}.py'
        if selection['candidates'][name]['export_sha256'] != file_hash(export):
            raise ValueError('Export changed after model selection: ' + name)
        models[name] = read_export(export)

    rows, mel, rms, labels, splits = load_baseline_cache(args.results)
    test = splits == 'test'
    test_rows = [r for r in rows if r['split'] == 'test']
    heldout = {}
    with np.load(args.cache, allow_pickle=False) as cache:
        verify_cache(cache, args.results, labels, splits)
        heldout['original'] = scored_holdout(
            labels[test], test_rows, baseline_scores(baseline, mel[test], rms[test]),
            stress_baseline(baseline, cache, 'test'), baseline.THRESHOLD, 15, 9)
        for name, model in models.items():
            key = f'fft{model.BURST_SAMPLES}'
            # Historical stress features are read only after models are frozen.
            heldout[name] = scored_holdout(
                labels[test], test_rows, predict_export(model, cache[key][test]),
                predict_export(model, cache['test_' + key]), model.THRESHOLD, model.SPAN, model.REQUIRED)
    local = {name: replay(name, decode(args.samples / name), baseline, models)
             for name in (*BACKGROUND, *TIMED, *UNTIMED)}
    acquired = {}
    for row in recordings(args.manifest):
        if row['role'] == 'validation':
            path = args.audio / row['file']
            verify(path.read_bytes(), row)
            acquired[row['file']] = replay(row['file'], decode(path), baseline, models)
    result = dict(selected=selection['selected'], heldout=heldout,
                  local_development=local, acquired_weak_label_validation=acquired)
    with args.output.open('x', encoding='utf8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=RESULTS)
    parser.add_argument('--cache', type=Path, default=CACHE)
    parser.add_argument('--manifest', type=Path, default=MANIFEST)
    parser.add_argument('--audio', type=Path, default=AUDIO)
    parser.add_argument('--samples', type=Path, default=SAMPLES)
    parser.add_argument('--previous', type=Path, default=DEFAULT_MODEL)
    parser.add_argument('--baseline', type=Path, default=BASELINE)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    evaluate(parser.parse_args())


if __name__ == '__main__':
    main()
