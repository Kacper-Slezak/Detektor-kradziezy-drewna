"""Read-only feature probes on development audio and the exposed validation cache."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np

from algorithm.app._dataset_utils import locate_archive, manifest_rows
from algorithm.app.burst_evaluate import BACKGROUND, TIMED, UNTIMED, baseline_predict
from algorithm.app.burst_prepare import all_windows, decode
from algorithm.app.burst_stage_lopy import DEFAULT_MODEL, read_export
from algorithm.app.burst_train import baseline_scores, load_baseline_cache, metrics, stress_baseline
from algorithm.app.engine_event_audit import clip_comparison, replay_comparison
from algorithm.app.engine_provenance import component_audit
from algorithm.app.recall_audio import AUDIO, MANIFEST, recordings, verify
from algorithm.app.recall_evaluate import BASELINE, phase_diagnostic, predict_export
from algorithm.app.recall_train import CACHE, RESULTS, SAMPLES, file_hash, verify_cache
from algorithm.app.v4_6_infer import load_model
from firmware.lib.tg_burst import BAND_EDGES, RATE

SELECTION = Path('algorithm/results/recall/selection')
SOURCE_MANIFEST = Path('algorithm/data/dataset_manifest_fsc22.csv')
DATA = Path('algorithm/data')
DB_PER_NEPER = 20 / np.log(10)
NATIVE_BASELINE = (15, 9)
GEOMETRIES = ((4000, 128), (4000, 250), (8000, 128))
STRATA = ('Rain', 'Wind', 'Thunderstorm', 'Insect', 'helicopter', 'train')


def quantiles(values):
    return [round(float(x), 5) for x in np.quantile(values, (.1, .5, .9))] if len(values) else None


def auc(positive, negative):
    """Probability that a positive scores above a negative, with half credit for ties."""
    negative = np.sort(negative)
    if not len(negative) or not len(positive):
        return None
    lower = np.searchsorted(negative, positive, 'left')
    upper = np.searchsorted(negative, positive, 'right')
    return float(np.mean(lower + .5 * (upper - lower)) / len(negative))


def inspect_features(pcm, rate, size_ms):
    """Return per-window acoustic descriptors from matched 250 ms slots."""
    if (rate, size_ms) not in GEOMETRIES or len(pcm) < 2 * rate:
        raise ValueError('Expected at least two seconds and a supported capture geometry')
    hop = rate // 4
    size = rate * size_ms // 1000
    starts = np.arange(len(pcm) // rate * 4) * hop
    frames = pcm[starts[:, None] + np.arange(size)].astype(np.float64)
    frames -= frames.mean(axis=1, keepdims=True)
    power = np.abs(np.fft.rfft(frames * np.hanning(size))) ** 2
    hz = np.fft.rfftfreq(size, 1 / rate)

    def band(lo, hi):
        return power[:, (lo <= hz) & (hz < hi)].sum(axis=1) + 1e-6

    low_mid = 10 * np.log10(band(35, 130) / band(130, 800))
    low = power[:, (45 <= hz) & (hz < 350)]
    width = round(24 * size / rate)
    cumulative = np.pad(np.cumsum(low, axis=1), ((0, 0), (1, 0)))
    peak = cumulative[:, width:] - cumulative[:, :-width]
    peak_share = 10 * np.log10((peak.max(axis=1) + 1e-6) / band(45, 350))
    fundamentals = np.arange(45, 121, 5)[:, None]
    harmonics = np.arange(2, 5)
    frequencies = fundamentals * harmonics
    # Average log contrast of three harmonics against inter-harmonic power.
    log_power = np.log10(power + 1e-6)

    def interpolate(frequencies):
        bins = frequencies * size / rate
        floor = bins.astype(int)
        fraction = bins - floor
        return log_power[:, floor] * (1 - fraction) + log_power[:, floor + 1] * fraction

    harmonic = 10 * ((interpolate(frequencies) -
                      interpolate(fundamentals * (harmonics + .5))).mean(axis=2)).max(axis=1)
    columns = dict(rms_dbfs=20 * np.log10(np.maximum(frames.std(axis=1), 1) / 32768),
                   low_mid_db=low_mid, peak_share_db=peak_share, harmonic_db=harmonic,
                   inband_upper_pct=100 * band(1300, 1900) / band(35, 1900))
    if rate >= 8000:
        columns['upper_energy_pct'] = 100 * band(1900, 3800) / band(35, 3800)
    offsets = (np.arange(len(pcm) // rate - 1) * 4)[:, None] + np.arange(8)
    result = {name: np.median(value[offsets], axis=1) for name, value in columns.items()}
    windows = harmonic[offsets]
    result['harmonic_mean_db'] = windows.mean(axis=1)
    result['harmonic_p75_db'] = np.quantile(windows, .75, axis=1)
    result['harmonic_adjacent_db'] = np.minimum(windows[:, 1:], windows[:, :-1]).max(axis=1)
    result['rms_late_minus_early_db'] = (columns['rms_dbfs'][offsets[:, 4:]].mean(axis=1) -
                                        columns['rms_dbfs'][offsets[:, :4]].mean(axis=1))
    return result


def describe_geometry(audio):
    duration = min(len(pcm) // rate for rate, pcm in audio.items())
    return {f'{rate}_{size}ms': inspect_features(audio[rate][:duration * rate], rate, size)
            for rate, size in GEOMETRIES}


def summarize_geometry(details, mask=slice(None)):
    return {geometry: {name: quantiles(values[mask]) for name, values in features.items()}
            for geometry, features in details.items()}


def probe_validation(manifest, data_dir, validation_sources):
    _, chosen = manifest_rows(manifest)
    eligible = [r for r in chosen if r['split'] == 'val'
                and r['dataset'] + '/' + r['audio_member'] in validation_sources]
    negatives = [r for label in STRATA
                 for r in sorted((r for r in eligible if r['category'] == label),
                                 key=lambda r: r['audio_member'])[:6]]
    subset = [r for r in eligible if r['target_engine'] == '1'] + negatives
    with ExitStack() as stack:
        paths = {locate_archive(r, data_dir) for r in subset}
        archives = {path: stack.enter_context(ZipFile(path)) for path in paths}

        def examine(row):
            raw = archives[locate_archive(row, data_dir)].read(row['audio_member'])
            if hashlib.sha256(raw).hexdigest() != row['sha256'].lower():
                raise ValueError('Recording changed: ' + row['audio_member'])
            audio = {rate: decode('pipe:0', rate, raw)[:8 * rate] for rate in (4000, 8000)}
            return (row['dataset'] + '/' + row['audio_member'], row['category'],
                    row['target_engine'] == '1', summarize_geometry(describe_geometry(audio)))

        with ThreadPoolExecutor(max_workers=4) as executor:
            return list(executor.map(examine, subset))


def probe_separation(clips):
    result = {}
    for geometry, features in clips[0][3].items():
        stats = {}
        for key in features:
            engine = [x[3][geometry][key][1] for x in clips if x[2]]
            other = [x[3][geometry][key][1] for x in clips if not x[2]]
            weather = [x[3][geometry][key][1] for x in clips if x[1] in STRATA[:3]]
            stats[key] = dict(engine=quantiles(engine), negative=quantiles(other),
                              weather=quantiles(weather), auc=auc(engine, other),
                              weather_auc=auc(engine, weather))
        result[geometry] = stats
    return result


def score_validation(rows, labels, scores, stress, threshold, native, features):
    positive = labels == 1
    forest = np.array([r['source'].startswith('FSC22/') for r in rows])
    hit = scores >= threshold
    rms, modulation = features[:, -1] * DB_PER_NEPER, features[:, -2] * DB_PER_NEPER
    low_color = (features[:, :3].mean(axis=1) - features[:, 4:11].mean(axis=1)) * (DB_PER_NEPER / 2)
    by_record = {}
    for i, row in enumerate(rows):
        if positive[i]:
            by_record.setdefault(row['source'], []).append(i)
    groups = {name: [ids for ids in by_record.values() if bool(np.any(hit[ids])) == detected]
              for name, detected in (('detected', True), ('missed', False))}
    return dict(threshold=threshold, windows=metrics(labels, hit),
                clean_auc_vs_fsc22=auc(scores[positive], scores[forest]),
                stress_auc_vs_fsc22=auc(stress, scores[forest]),
                clean_score=quantiles(scores[positive]), stress_score=quantiles(stress),
                stress_positive=int((stress >= threshold).sum()), stress_count=len(stress),
                engine_window_features={name: dict(count=int(mask.sum()), rms_dbfs=quantiles(rms[mask]),
                                                   rms_modulation_db=quantiles(modulation[mask]),
                                                   low_band_color_db=quantiles(low_color[mask]))
                                        for name, mask in (('hit', positive & hit), ('miss', positive & ~hit))},
                engine_recordings={name: dict(count=len(ids), median_rms_dbfs=quantiles(
                    [np.median(rms[group]) for group in ids]),
                    median_low_band_color_db=quantiles([np.median(low_color[group]) for group in ids]))
                                   for name, ids in groups.items()},
                event_rules=clip_comparison(rows, scores, threshold, native))


def energy_intervention(model, values):
    """Counterfactual scalar interventions on a frozen model, with all other inputs fixed."""
    samples = values.copy()
    result = {}
    for change in ('unchanged', -12, 'training_mean', 12):
        samples[:, -1] = values[:, -1]
        if change == 'training_mean':
            samples[:, -1] = model.MEAN[-1]
        elif isinstance(change, int):
            samples[:, -1] += change / DB_PER_NEPER
        scores = predict_export(model, samples)
        result[str(change)] = dict(max=float(max(scores)), median=float(np.median(scores)),
                                   hits=int((scores >= model.THRESHOLD).sum()))
    return result


def replay_probes(samples, baseline, models):
    result = {}
    for name in (*BACKGROUND, *TIMED, *UNTIMED):
        audio = {rate: decode(samples / name, rate) for rate in (4000, 8000)}
        details = describe_geometry(audio)
        profile = summarize_geometry(details)
        if name in TIMED:
            start, end = TIMED[name]
            indexes = np.arange(min(len(pcm) // rate for rate, pcm in audio.items()) - 1)
            profile_in_event = summarize_geometry(details, (indexes >= start) & (indexes + 2 <= end))
        else:
            profile_in_event = None
        scores = baseline_predict(audio[RATE], baseline)
        entry = dict(seconds=len(audio[RATE]) / RATE, profile=profile, fully_in_event=profile_in_event,
                     original=dict(max_score=float(max(scores)), events=replay_comparison(
                         scores, baseline.THRESHOLD, NATIVE_BASELINE, TIMED.get(name))))
        for label, model in models.items():
            features = all_windows(audio[RATE], model.BURST_SAMPLES)
            scores = predict_export(model, features)
            row = dict(max_score=float(max(scores)), events=replay_comparison(
                scores, model.THRESHOLD, (model.SPAN, model.REQUIRED), TIMED.get(name)))
            if name in (*TIMED, *UNTIMED):
                row['phase'] = phase_diagnostic(audio[RATE], model)
                row['absolute_rms_sensitivity'] = energy_intervention(model, features)
            entry[label] = row
        result[name] = entry
    return result


def validation_diagnostics(root, cache_path, baseline, models):
    rows, mel, rms, labels, splits = load_baseline_cache(root)
    mask = splits == 'val'
    rows = [row for row in rows if row['split'] == 'val']
    with np.load(cache_path, allow_pickle=False) as cache:
        verify_cache(cache, root, labels, splits)
        features = cache['fft512'][mask]
        labels = labels[mask]
        result = {'original': score_validation(
            rows, labels, baseline_scores(baseline, mel[mask], rms[mask]),
            stress_baseline(baseline, cache, 'val'), baseline.THRESHOLD, NATIVE_BASELINE, features)}
        for name, model in models.items():
            stress = cache['val_fft512']
            result[name] = score_validation(rows, labels, predict_export(model, features),
                                            predict_export(model, stress), model.THRESHOLD,
                                            (model.SPAN, model.REQUIRED), features)
            result[name]['stress_absolute_rms_sensitivity'] = energy_intervention(model, stress)
        result['absolute_rms_dbfs'] = {
            'clean_engine': quantiles(features[labels == 1, -1] * DB_PER_NEPER),
            'clean_negative': quantiles(features[labels == 0, -1] * DB_PER_NEPER),
            'stress_engine': quantiles(cache['val_fft512'][:, -1] * DB_PER_NEPER),
        }
    return rows, result


def run(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    baseline = load_model(args.baseline)
    selection = json.loads((args.selection / 'selection.json').read_text(encoding='utf8'))
    paths = dict(previous_burst=DEFAULT_MODEL, local_512=args.selection / 'local_512.py',
                 expanded_512=args.selection / 'expanded_512.py')
    hashes = {name: file_hash(path) for name, path in paths.items()}
    for name in ('local_512', 'expanded_512'):
        if hashes[name] != selection['candidates'][name]['export_sha256']:
            raise ValueError('Frozen export has changed: ' + name)
    models = {name: read_export(path) for name, path in paths.items()}
    rows, validation = validation_diagnostics(args.results, args.cache, baseline, models)
    clips = probe_validation(args.source_manifest, args.data, {row['source'] for row in rows})
    assets = {}
    for row in recordings(MANIFEST):
        path = args.audio / row['file']
        verify(path.read_bytes(), row)
        pcm = decode(path)
        if row['role'] == 'train':
            pcm = pcm[int(row['start_s']) * RATE:int(row['end_s']) * RATE]
        assets[row['file']] = dict(role=row['role'], sha256=row['sha256'],
                                   rms_dbfs=quantiles(all_windows(pcm, 512)[:, -1] * DB_PER_NEPER))
    document = dict(model_hashes={'original': file_hash(args.baseline), **hashes},
                    inputs_sha256=dict(windows=file_hash(args.results / 'windows.csv'),
                                       cache=file_hash(args.cache), manifest=file_hash(args.source_manifest)),
                    validation=validation, validation_acoustic_sources=clips,
                    descriptor_separation=probe_separation(clips), acquired_rms=assets,
                    development_replays=replay_probes(args.samples, baseline, models),
                    wet_provenance=component_audit(args.samples, baseline, models),
                    band_edges_hz=BAND_EDGES)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf8') as stream:
        json.dump(document, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name, default in (('results', RESULTS), ('cache', CACHE), ('baseline', BASELINE),
                          ('selection', SELECTION), ('source-manifest', SOURCE_MANIFEST),
                          ('data', DATA), ('samples', SAMPLES), ('audio', AUDIO)):
        parser.add_argument('--' + name, type=Path, default=default)
    parser.add_argument('--output', required=True, type=Path)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
