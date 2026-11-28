"""Compare small burst models on validation data and export the chosen int8 model."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from algorithm.app._v46_training import sigmoid, weights_for_sources
from algorithm.app.v4_6_infer import load_model
from algorithm.app.v4_6_train import patches, quant_forward
from algorithm.core.tg_temporal_v46 import normalize_window
from firmware.lib.tg_burst import RATE, Votes

SEED = 2026
BUDGET = ((256, 0, False, 0), (256, 16, False, 0), (512, 0, False, 0),
          (512, 16, False, 0), (512, 16, True, 0))
CALIBRATED = ((256, 16, True, 9), (512, 16, False, 9), (512, 16, True, 9))


def load_baseline_cache(root):
    report = json.loads((root / 'wide_v46_report.json').read_text(encoding='utf8'))
    for key, name in (('base_windows_sha256', 'windows.csv'),
                      ('wide_features_sha256', 'wide_v46.npz')):
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != report[key]:
            raise ValueError('v4.6 cache fingerprint mismatch: ' + name)
    with (root / 'windows.csv').open(newline='', encoding='utf8') as stream:
        rows = list(csv.DictReader(stream))
    with np.load(root / 'wide_v46.npz', allow_pickle=False) as data:
        mel, rms, labels, splits = (data[name] for name in ('X', 'R', 'y', 'splits'))
    if (mel.shape != (len(rows), 8, 24) or rms.shape != (len(rows), 9)
            or len(labels) != len(rows) or len(splits) != len(rows)):
        raise ValueError('v4.6 cache shape mismatch')
    seen = {}
    for i, row in enumerate(rows):
        split = row['split']
        source = row['source'].split(':aug:', 1)[0]
        if (int(row['index']) != i or split not in ('train', 'val', 'test')
                or split != splits[i] or int(row['label']) != labels[i]
                or (row['augmented'] == '1' and split != 'train')
                or seen.setdefault(source, split) != split):
            raise ValueError('Recording, label or split mismatch: ' + row['source'])
    return rows, mel, rms, labels, splits


def metrics(labels, hits):
    tp = int(np.sum((labels == 1) & hits))
    fp = int(np.sum((labels == 0) & hits))
    fn = int(np.sum((labels == 1) & ~hits))
    tn = int(np.sum((labels == 0) & ~hits))
    return dict(TP=tp, FP=fp, FN=fn, TN=tn, precision=tp / max(1, tp + fp),
                recall=tp / max(1, tp + fn), specificity=tn / max(1, tn + fp),
                f1=2 * tp / max(1, 2 * tp + fp + fn))


def baseline_scores(model, mel, rms):
    import base64

    c, h = model.CONV_CHANNELS, model.HIDDEN
    weights = [np.frombuffer(base64.b64decode(b64), dtype=np.int8).reshape(shape)
               for b64, shape in zip(model.WEIGHT_B64, ((9, c), (12 * c + 9, h), (h, 1)))]
    mel = np.clip((mel - model.MEAN) * model.INV_STD, -6, 6).astype(np.float32)
    rms = np.clip((rms - model.E_MEAN) * model.E_INV_STD, -6, 6).astype(np.float32)
    biases = [np.asarray(b, dtype=np.float32) for b in model.BIASES]
    return quant_forward(patches(mel), rms, (weights, model.SCALES, biases))


def stress_baseline(model, cache, split):
    values = [normalize_window(x.reshape(-1), r) for x, r in
              zip(cache[f'{split}_mel'], cache[f'{split}_rms'])]
    mel = np.asarray([x for x, _ in values]).reshape(-1, 8, 24)
    return baseline_scores(model, mel, np.asarray([r for _, r in values]))


def train(x, labels, weights, hidden, gain_db=0):
    rng = np.random.default_rng(SEED)
    n_inputs = x.shape[1]
    mean = x.mean(axis=0)
    inv = 1.0 / np.maximum(x.std(axis=0), 0.05)
    x = (x - mean) * inv
    params = [rng.normal(0, np.sqrt(2.0 / n_inputs), (n_inputs, hidden or 1)),
              np.zeros(hidden or 1)]
    if hidden:
        params += [rng.normal(0, np.sqrt(1.0 / hidden), (hidden, 1)), np.zeros(1)]
    average = [np.zeros_like(p) for p in params]
    variance = [np.zeros_like(p) for p in params]
    step = 0
    for _ in range(30):
        order = rng.permutation(len(labels))
        for start in range(0, len(order), 128):
            ids = order[start:start + 128]
            inputs = x[ids]
            if gain_db and n_inputs == 32:
                inputs[:, -1] += (rng.uniform(-gain_db, gain_db, len(ids)) *
                                  np.log(10) / 20 * inv[-1])
            inputs = np.clip(inputs, -6, 6)
            z = inputs @ params[0] + params[1]
            activation = np.maximum(z, 0) if hidden else inputs
            logits = activation @ params[2] + params[3] if hidden else z
            error = ((sigmoid(logits[:, 0]) - labels[ids]) * weights[ids] /
                     np.sum(weights[ids]))[:, None]
            gradients = []
            if hidden:
                gradients = [activation.T @ error + 1e-3 * params[2], error.sum(axis=0)]
                error = (error @ params[2].T) * (z > 0)
            gradients = [inputs.T @ error + 1e-3 * params[0], error.sum(axis=0)] + gradients
            step += 1
            for i, grad in enumerate(gradients):
                average[i] = 0.9 * average[i] + 0.1 * grad
                variance[i] = 0.999 * variance[i] + 0.001 * grad ** 2
                params[i] -= (0.003 * average[i] / (1 - 0.9 ** step) /
                              (np.sqrt(variance[i] / (1 - 0.999 ** step)) + 1e-8))
    quantized, scales = [], []
    for weights in params[::2]:
        scale = max(np.abs(weights).max() / 127.0, 1e-9)
        scales.append(float(scale))
        quantized.append(np.rint(weights / scale).astype(np.int8))
    return mean, inv, quantized, scales, params[1::2]


def predict(x, model):
    mean, inv, weights, scales, biases = model
    z = np.clip((x - mean) * inv, -6, 6) @ (weights[0] * scales[0]) + biases[0]
    if len(weights) == 2:
        z = np.maximum(z, 0) @ (weights[1] * scales[1]) + biases[1]
    return sigmoid(z[:, 0])


def evaluation(labels, scores, source_rows, stress, threshold):
    hits = scores >= threshold
    result = metrics(labels, hits)
    forest = np.asarray([r['source'].startswith('FSC22/') for r in source_rows])
    result['fsc22_fp'] = int(hits[forest].sum())
    result['fsc22_windows'] = int(forest.sum())
    recordings = {}
    for i, row in enumerate(source_rows):
        recordings.setdefault(row['source'], []).append(i)
    result['engine_recordings'] = sum(labels[ids[0]] == 1 for ids in recordings.values()).item()
    result['missed_engine_recordings'] = sum(labels[ids[0]] == 1 and not hits[ids].any()
                                             for ids in recordings.values()).item()
    result['stress_hit'] = int(np.sum(stress >= threshold))
    result['stress_windows'] = len(stress)
    return result


def choose(labels, scores, rows, stress, development=None):
    forest = np.asarray([r['source'].startswith('FSC22/') for r in rows])
    best = None
    for point in range(5, 100):
        threshold = point / 100
        hits = scores >= threshold
        stats = metrics(labels, hits)
        mix_recall = float(np.mean(stress >= threshold))
        forest_fpr = float(hits[forest].mean())
        dev_fpr = float(np.mean(development >= threshold)) if development is not None else 0.0
        # Explicit minimums, then prefer forest specificity. In fallback balance
        # clean and noisy recall against forest false positives.
        viable = stats['recall'] >= .80 and mix_recall >= .60 and dev_fpr <= .02
        quality = min(stats['recall'], mix_recall) - forest_fpr - dev_fpr
        key = (viable, -forest_fpr if viable else quality, quality, stats['f1'])
        if best is None or key > best[0]:
            best = key, threshold
    return best


def clip_events(rows, scores, threshold, span, required):
    by_clip = {}
    for row, score in zip(rows, scores):
        by_clip.setdefault(row['source'], []).append((float(row['time_s']), score, int(row['label'])))
    labels, detections = [], []
    for windows in by_clip.values():
        votes = Votes(threshold, span, required)
        confirmed = False
        previous = None
        for second, score, label in sorted(windows):
            if previous is not None and second != previous + 1:
                votes.reset()
            confirmed = votes.step(score) or confirmed
            previous = second
        labels.append(label)
        detections.append(confirmed)
    return metrics(np.asarray(labels), np.asarray(detections, dtype=bool))


def choose_votes(rows, scores, threshold):
    choices = []
    for span, required in ((2, 2), (3, 2), (4, 3)):
        results = clip_events(rows, scores, threshold, span, required)
        choices.append(dict(span=span, required=required, validation=results))
    def rank(choice):
        result = choice['validation']
        # Count a missed clip at five times the cost of a percentage point
        # of clean-background clip false positives, on class-normalized rates.
        return result['recall'] + .2 * result['specificity'], result['specificity']
    return max(choices, key=rank), choices


def development_event(scores, threshold, span, required, interval):
    start, end = interval
    votes = Votes(threshold, span, required)
    early = 0
    first = None
    for second, score in enumerate(scores, 2):
        if votes.step(score):
            early += second <= start
            if start + 2 <= second <= end and first is None:
                first = second
    return dict(passed=not early and first is not None, early_confirmed_windows=early,
                first_engine_confirmation_s=first)


def export(path, model, size, hidden, threshold, span, required):
    mean, inv, weights, scales, biases = model
    packed = b''.join(w.T.tobytes() for w in weights)
    constants = dict(FEATURE_VERSION=1, RATE=RATE, BURST_SAMPLES=size, INPUTS=len(mean),
                     HIDDEN=hidden, THRESHOLD=threshold, SPAN=span, REQUIRED=required,
                     MEAN=tuple(map(float, mean)), INVERSE_STD=tuple(map(float, inv)),
                     SCALES=tuple(scales), BIASES=tuple(float(b) for layer in biases for b in layer))
    with path.open('x', encoding='ascii', newline='\n') as stream:
        stream.write('"""Generated by algorithm.app.burst_train. Original LoPy diagnostic model."""\n')
        for key, value in constants.items():
            stream.write(f'{key} = {value!r}\n')
        stream.write('WEIGHTS = (\n')
        for i in range(0, len(packed), 32):
            stream.write(f'    {packed[i:i + 32]!r}\n')
        stream.write(')\n')
    return len(packed)


def run(root, cache_path, baseline_path, output, calibration_path=None, truck=None, interval=None):
    rows, mel, rms, labels, splits = load_baseline_cache(root)
    baseline = load_model(baseline_path)
    tr = splits == 'train'
    val = splits == 'val'
    test = splits == 'test'
    for mask in (tr, val, test):
        if set(labels[mask]) != {0, 1}:
            raise ValueError('Both classes required in each split')
    sources = [r['source'] for r in rows]
    train_sources = np.asarray(sources)[tr]
    weights = weights_for_sources(labels[tr], train_sources)
    val_rows = [r for r in rows if r['split'] == 'val']
    test_rows = [r for r in rows if r['split'] == 'test']
    with np.load(cache_path, allow_pickle=False) as cache:
        if (cache['windows_sha256'].item() != hashlib.sha256((root / 'windows.csv').read_bytes()).hexdigest()
                or not np.array_equal(cache['labels'], labels) or not np.array_equal(cache['splits'], splits)):
            raise ValueError('Burst cache does not match recording split')
        report = {'seed': SEED, 'candidates': [], 'baseline_threshold': baseline.THRESHOLD}
        truck_features = {}
        if truck is not None:
            from algorithm.app.burst_prepare import all_windows, decode
            pcm = decode(truck)
            if not (0 <= interval[0] < interval[1] <= len(pcm) / RATE
                    and interval[1] - interval[0] >= 2):
                raise ValueError('Invalid development truck interval')
            truck_features = {size: all_windows(pcm, size) for size in (256, 512)}
            report['development_truck'] = dict(sha256=hashlib.sha256(truck.read_bytes()).hexdigest(),
                                               engine_interval_s=interval)
        calibration = {}
        if calibration_path is not None:
            with np.load(calibration_path, allow_pickle=False) as data:
                calibration = {name: data[name] for name in data.files}
            if (calibration['windows_sha256'].item() != cache['windows_sha256'].item()
                    or not set(calibration['sources'][calibration['labels'] == 1]) <= set(train_sources)):
                raise ValueError('Calibration must reference training engines only')
            report['development_forest_sha256'] = calibration['forest_sha256'].item()
        report['baseline_validation'] = evaluation(
            labels[val], baseline_scores(baseline, mel[val], rms[val]), val_rows,
            stress_baseline(baseline, cache, 'val'), baseline.THRESHOLD)
        best = None
        for size, hidden, absolute_rms, gain_db in BUDGET + (CALIBRATED if calibration else ()):
            key = f'fft{size}'
            count = cache[key].shape[1] - int(not absolute_rms)
            x = cache[key][:, :count]
            stress = cache['val_' + key][:, :count]
            train_x, train_y, train_w = x[tr], labels[tr], weights
            dev_x = None
            if calibration:
                extra_y = calibration['labels']
                extra_x = calibration[key][:, :count]
                dev_x = extra_x[extra_y == 0]
            if gain_db:
                train_x = np.concatenate((train_x, extra_x))
                train_y = np.concatenate((train_y, extra_y))
                train_w = weights_for_sources(train_y, np.concatenate((train_sources, calibration['sources'])))
                # One domain-specific background recording supplies 15% of negative loss.
                dev = np.concatenate((np.zeros(len(train_sources), dtype=bool), extra_y == 0))
                train_w[dev] = train_w[(train_y == 0) & ~dev].sum() * .15 / .85 / dev.sum()
            fitted = train(train_x, train_y, train_w, hidden, gain_db=gain_db)
            scores, noise_scores = predict(x[val], fitted), predict(stress, fitted)
            dev_scores = predict(dev_x, fitted) if dev_x is not None else None
            rank, threshold = choose(labels[val], scores, val_rows, noise_scores, dev_scores)
            stats = evaluation(labels[val], scores, val_rows, noise_scores, threshold)
            if dev_scores is not None:
                stats['development_forest_hits'] = int(np.sum(dev_scores >= threshold))
                stats['development_forest_windows'] = len(dev_scores)
            config = dict(size=size, hidden=hidden, absolute_rms=absolute_rms,
                          calibration=bool(gain_db), gain_db=gain_db if absolute_rms else 0,
                          threshold=threshold)
            votes, choices = choose_votes(val_rows, scores, threshold)
            candidate = dict(config=config, validation=stats)
            if truck_features:
                event = development_event(predict(truck_features[size][:, :count], fitted),
                                          threshold, votes['span'], votes['required'], interval)
                candidate['development_truck'] = event
                rank = (bool(rank[0] and event['passed']), *rank)
            report['candidates'].append(candidate)
            if best is None or rank > best[0]:
                best = rank, config, fitted, votes, choices

        _, config, fitted, votes, choices = best
        size, hidden, threshold = config['size'], config['hidden'], config['threshold']
        count = len(fitted[0])
        key = f'fft{size}'
        report['vote_candidates'] = choices
        span, required = votes['span'], votes['required']
        report['votes'] = {'span': span, 'required': required}
        report['selected'] = config
        test_scores = predict(cache[key][test, :count], fitted)
        base_test = baseline_scores(baseline, mel[test], rms[test])
        report['test'] = evaluation(labels[test], test_scores, test_rows,
                                    predict(cache['test_' + key][:, :count], fitted), threshold)
        report['baseline_test'] = evaluation(
            labels[test], base_test, test_rows,
            stress_baseline(baseline, cache, 'test'), baseline.THRESHOLD)
        report['test_clip_confirmations'] = clip_events(test_rows, test_scores, threshold, span, required)
        report['baseline_test_clip_confirmations'] = clip_events(
            test_rows, base_test, baseline.THRESHOLD, 15, 9)
    output.mkdir(parents=True, exist_ok=False)
    path = output / 'tg_model_burst.py'
    report['weight_bytes'] = export(path, fitted, size, hidden, threshold, span, required)
    report['export_bytes'] = path.stat().st_size
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=Path('algorithm/results/v4_2_fsc22'))
    parser.add_argument('--cache', type=Path, default=Path('algorithm/results/burst/features.npz'))
    parser.add_argument('--baseline', type=Path,
                        default=Path('algorithm/results/v4_6_wideband/tg_model_v46.py'))
    parser.add_argument('--output', type=Path, default=Path('algorithm/results/burst/fit'))
    parser.add_argument('--calibration', type=Path)
    parser.add_argument('--development-truck', type=Path)
    parser.add_argument('--truck-interval', type=float, nargs=2, metavar=('START', 'END'))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if (args.development_truck is None) != (args.truck_interval is None):
        parser.error('Supply both --development-truck and --truck-interval')
    run(args.results, args.cache, args.baseline, args.output, args.calibration,
        args.development_truck, args.truck_interval)


if __name__ == '__main__':
    main()
