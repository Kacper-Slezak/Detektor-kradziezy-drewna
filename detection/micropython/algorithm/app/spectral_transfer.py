"""Score frozen probes on source-screened archive clips and benchmark the portable path."""

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import csv
import hashlib
import json
from pathlib import Path
import re
from time import perf_counter
from zipfile import ZipFile

import numpy as np

from algorithm.app._dataset_utils import locate_archive, manifest_rows
from algorithm.app.burst_evaluate import BACKGROUND, TIMED, UNTIMED, baseline_predict, episodes
from algorithm.app.burst_prepare import HOP, decode, read_original
from algorithm.app.burst_stage_lopy import DEFAULT_MODEL, read_export
from algorithm.app.burst_train import sigmoid
from algorithm.app.engine_diagnose import DATA, SELECTION, SOURCE_MANIFEST, STRATA, auc, quantiles
from algorithm.app.engine_event_audit import COMMON_RULES, replay_comparison
from algorithm.app.recall_audio import MANIFEST, recordings
from algorithm.app.recall_evaluate import BASELINE, predict_export
from algorithm.app.recall_train import SAMPLES, file_hash
from algorithm.app.spectral_features import extract
from algorithm.app.v4_6_infer import load_model
from firmware.lib.tg_burst import RATE
from firmware.lib.tg_burst_device import Monitor
from firmware.lib.tg_spectral_probe import LinearProbe, SpectralProbe

META = 'FSC22-main/Metadata/Metadata V1.0 FSC22.csv'
CLASSES = ('VehicleEngine', 'Generator', 'Chainsaw', 'Helicopter', 'Handsaw')
EXCLUDE_DESCRIPTION = re.compile(r'synth|cyborg|frequency.sweep|engine.loop|simulation', re.I)
WEATHER_DESCRIPTION = re.compile(r'\b(?:rain|wet|wind|windy)\b', re.I)
SOURCE_ID = re.compile(r'^(\d{4,})_(?!\d)')
FEATURE_NAMES = ('low_peak_share', 'low_local_contrast', 'upper_peak_share', 'upper_local_contrast',
                 'low_peak_stability', 'low_ordered_contrast', 'upper_peak_stability', 'upper_ordered_contrast')


def cohort(archive, manifests):
    """Select by publisher metadata and historical exposure, before reading scores."""
    exposed_ids, seen_hashes = set(), {row['sha256'] for row in recordings(MANIFEST)}
    for path in manifests:
        _, used = manifest_rows(path)
        exposed_ids.update(row['source_id'] for row in used if row['source_id'].isdigit())
        seen_hashes.update(row['sha256'].lower() for row in used)
    metadata = csv.DictReader(archive.read(META).decode('utf-8-sig').splitlines())
    candidates, class_by_id = defaultdict(list), defaultdict(set)
    for row in metadata:
        description = row['Source File Name']
        match = SOURCE_ID.match(description)
        if match:
            source = match[1]
            category = row['Class Name']
            class_by_id[source].add(category)
            if source not in exposed_ids and category in CLASSES and not EXCLUDE_DESCRIPTION.search(description):
                candidates[category].append((source, row['Dataset File Name'], description))

    result, selected_ids = [], set()
    for category in CLASSES:
        count = 0
        # Fixed digest order avoids selecting a contiguous publishing session.
        for source, filename, description in sorted(candidates[category], key=lambda entry: (
                hashlib.sha256(entry[0].encode()).digest(), entry[1])):
            if len(class_by_id[source]) != 1 or source in selected_ids:
                continue
            raw = archive.read('FSC22-main/Audios/' + filename)
            digest = hashlib.sha256(raw).hexdigest()
            if digest in seen_hashes:
                continue
            selected_ids.add(source)
            seen_hashes.add(digest)
            entry = dict(id=source, file=filename, description=description, category=category,
                         label=int(category == 'VehicleEngine'), sha256=digest,
                         weather_named=bool(WEATHER_DESCRIPTION.search(description)))
            result.append((entry, raw))
            count += 1
            if category != 'VehicleEngine' and count == 24:
                break
    return result


def exec_export(path):
    from importlib.util import module_from_spec, spec_from_file_location
    spec = spec_from_file_location(path.stem, path)
    model = module_from_spec(spec)
    spec.loader.exec_module(model)
    LinearProbe(model)
    return model


def portable_score(pcm, model):
    probe = SpectralProbe()
    classifier = LinearProbe(model)
    output = []
    for start in range(0, len(pcm) // RATE * RATE, HOP):
        for i in range(512):
            probe.spectrum.pcm[i] = int(pcm[start + i])
        if probe.push():
            output.append(classifier.score(probe.features))
    return np.asarray(output)


def vector_score(model, features):
    weights = np.frombuffer(model.WEIGHTS, dtype=np.int8) * model.SCALE
    normalized = (features[:, :model.INPUTS] - model.MEAN) * model.INVERSE_STD
    return sigmoid(np.clip(normalized, -6, 6) @ weights + model.BIAS)


def score_pcm(pcm, baseline, bursts, probes):
    features = extract(pcm)
    values = {'original': baseline_predict(pcm, baseline)}
    for name, model in bursts.items():
        values[name] = predict_export(model, features[:, :32])
    for name, model in probes.items():
        values[name] = vector_score(model, features)
    return features, values


def confirm_table(clips, scorers):
    result = {}
    for name, (threshold, native) in scorers.items():
        table = {}
        for key, (span, required) in {'native': native, **COMMON_RULES}.items():
            counts = Counter()
            categories = defaultdict(Counter)
            weather = Counter()
            ids = []
            for clip, scores in clips:
                score = scores[name]
                label = clip['label']
                if len(score) < span:
                    counts['ineligible_engine' if label else 'ineligible_negative'] += 1
                    continue
                detected = bool(episodes(score, threshold, span, required))
                key_label = ('TP' if detected else 'FN') if label else ('FP' if detected else 'TN')
                counts[key_label] += 1
                categories[clip['category']][key_label] += 1
                if label and clip['weather_named']:
                    weather[key_label] += 1
                if detected:
                    ids.append(clip['id'])
            metrics = {key: counts[key] for key in ('TP', 'FP', 'FN', 'TN',
                                                    'ineligible_engine', 'ineligible_negative')}
            eligible = counts['TP'] + counts['FN']
            metrics['recall'] = counts['TP'] / eligible if eligible else None
            called = counts['TP'] + counts['FP']
            metrics['precision'] = counts['TP'] / called if called else None
            table[key] = dict(metrics=metrics, categories=categories, weather_named=weather, confirmed_ids=ids)
        result[name] = table
    return result


def strata(data):
    """Describe the extra features on the existing 83-clip acoustic probe."""
    _, selected = manifest_rows(data / 'dataset_manifest_fsc22.csv')
    val = [r for r in selected if r['split'] == 'val']
    subset = [r for r in val if r['target_engine'] == '1']
    for label in STRATA:
        subset.extend(sorted((r for r in val if r['category'] == label),
                             key=lambda r: r['audio_member'])[:6])
    grouped = defaultdict(list)
    with ExitStack() as stack:
        paths = {locate_archive(r, data) for r in subset}
        archives = {path: stack.enter_context(ZipFile(path)) for path in paths}
        for row in subset:
            raw = archives[locate_archive(row, data)].read(row['audio_member'])
            if hashlib.sha256(raw).hexdigest() != row['sha256'].lower():
                raise ValueError('Development source changed: ' + row['audio_member'])
            group = 'engine' if row['target_engine'] == '1' else row['category']
            grouped[group].append(np.median(extract(decode('pipe:0', raw=raw)[:8 * RATE])[:, 32:], axis=0))
    matrices = {name: np.asarray(values) for name, values in grouped.items()}
    return {feature: {label: dict(quantiles=quantiles(values[:, i]),
                                  engine_auc=auc(matrices['engine'][:, i], values[:, i]))
                      for label, values in matrices.items()}
            for i, feature in enumerate(FEATURE_NAMES)}


def benchmark(pcm, previous, candidate):
    results = {}
    for name, monitor in (('previous_burst', Monitor(previous)), ('spectral_ordered', SpectralProbe())):
        spectral = name == 'spectral_ordered'
        classifier = LinearProbe(candidate) if spectral else None
        spectrum = monitor.spectrum
        for _ in range(2):
            durations, extraction, decision = [], [], []
            for slot in range(128):
                offset = slot * HOP % ((len(pcm) // RATE) * RATE)
                for i in range(len(spectrum.pcm)):
                    spectrum.pcm[i] = int(pcm[offset + i])
                start = perf_counter()
                ready = monitor.push(True)
                if ready and classifier:
                    classifier.score(monitor.features)
                elapsed = (perf_counter() - start) * 1000
                durations.append(elapsed)
                (decision if ready else extraction).append(elapsed)
        arrays = (spectrum.pcm, spectrum.real, spectrum.imag, spectrum.cos, spectrum.sin,
                  spectrum.hann, spectrum.reverse, monitor.features)
        if spectral:
            arrays += (monitor.bands, monitor.peaks)
            vote_bytes = 2  # Common 2-of-2 history, outside the portable probe.
        else:
            arrays += (monitor.frames, monitor.classifier.values)
            vote_bytes = len(monitor.votes.history)
        results[name] = dict(median_slot_ms=float(np.median(durations)), p95_slot_ms=float(np.quantile(durations, .95)),
                             max_slot_ms=max(durations), typed_buffers_bytes=(
                                 sum(len(a) * a.itemsize for a in arrays) + vote_bytes),
                             median_extract_slot_ms=float(np.median(extraction)),
                             median_decision_slot_ms=float(np.median(decision)))
    return results


def run(args):
    if args.output.exists():
        raise FileExistsError(args.output)
    frozen = json.loads((args.frozen / 'frozen.json').read_text(encoding='utf8'))
    selection = json.loads((args.selection / 'selection.json').read_text(encoding='utf8'))
    hashes = {'original': file_hash(args.baseline), 'previous_burst': file_hash(DEFAULT_MODEL)}
    baseline = load_model(args.baseline)
    bursts = {'previous_burst': read_export(DEFAULT_MODEL)}
    for name in ('local_512', 'expanded_512'):
        path = args.selection / (name + '.py')
        hashes[name] = file_hash(path)
        if hashes[name] != selection['candidates'][name]['export_sha256']:
            raise ValueError('Existing export changed: ' + name)
        bursts[name] = read_export(path)
    probes = {}
    for name, point in frozen['probes'].items():
        path = args.frozen / (name + '.py')
        hashes[name] = file_hash(path)
        if hashes[name] != point['export_sha256']:
            raise ValueError('Probe changed after validation: ' + name)
        probes[name] = exec_export(path)
    scorers = {'original': (baseline.THRESHOLD, (15, 9))}
    scorers.update({name: (m.THRESHOLD, (m.SPAN, m.REQUIRED)) for name, m in bursts.items()})
    scorers.update({name: (m.THRESHOLD, (2, 2)) for name, m in probes.items()})

    with ZipFile(args.data / 'FSC22-main.zip') as archive:
        clips = cohort(archive, [args.data / name for name in ('dataset_manifest.csv', 'dataset_manifest_fsc22.csv')])
    scores = []
    for entry, raw in clips:
        _, values = score_pcm(read_original(raw), baseline, bursts, probes)
        scores.append((entry, values))

    development, parity = {}, {}
    for filename in (*BACKGROUND, *TIMED, *UNTIMED):
        pcm = decode(args.samples / filename)
        _, values = score_pcm(pcm, baseline, bursts, probes)
        development[filename] = {name: dict(max=float(max(value)), rules=replay_comparison(
            value, *scorers[name], interval=TIMED.get(filename))) for name, value in values.items()}
        for name, model in probes.items():
            portable = portable_score(pcm, model)
            error = float(np.max(np.abs(portable - values[name])))
            if error > .0005 or not np.array_equal(portable >= model.THRESHOLD, values[name] >= model.THRESHOLD):
                raise ValueError('Portable mismatch: ' + filename + ' / ' + name)
            parity.setdefault(name, {})[filename] = error

    feature_strata = strata(args.data)
    pcm = decode(args.samples / 'catterpillar.wav')
    timings = [benchmark(pcm, bursts['previous_burst'], probes['spectral_ordered']) for _ in range(7)]
    report = dict(cohort=[entry for entry, _ in scores], model_sha256=hashes, operating_points=scorers,
                  transfer=confirm_table(scores, scorers), development=development,
                  feature_by_stratum=feature_strata, replay_parity=parity,
                  benchmark_cpython_runs=timings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=DATA)
    parser.add_argument('--samples', type=Path, default=SAMPLES)
    parser.add_argument('--selection', type=Path, default=SELECTION)
    parser.add_argument('--baseline', type=Path, default=BASELINE)
    parser.add_argument('--frozen', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args())


if __name__ == '__main__':
    main()
