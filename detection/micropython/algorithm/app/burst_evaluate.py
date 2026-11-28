"""Replay the supplied longer WAVs and benchmark the portable DSP on CPython."""

import argparse
from pathlib import Path
import json
from time import perf_counter

import numpy as np

from algorithm.app.burst_prepare import HOP, all_windows, decode
from algorithm.app.burst_stage_lopy import DEFAULT_MODEL, read_export
from algorithm.app.burst_train import baseline_scores
from algorithm.app.v4_6_infer import load_model
from algorithm.app.v4_6_prepare import features_per_second_pcm
from algorithm.core.tg_temporal_v46 import normalize_window
from firmware.lib.tg_burst import BANDS, FRAMES_PER_SECOND, WINDOW_FRAMES
from firmware.lib.tg_burst import Classifier, RATE, Votes, summarize
from firmware.lib.tg_burst_device import Monitor

BACKGROUND = ('forest-ambience.wav', 'rain-in-forest.wav', 'wind-blowing.wav', 'wind-lake.wav')
TIMED = {'forest-with-truck.wav': (19, 40)}
UNTIMED = ('rain-wind-truck.wav', 'catterpillar.wav')


def baseline_predict(pcm, baseline):
    mel, rms = features_per_second_pcm(pcm)
    values = [normalize_window(mel[i:i + 2].reshape(-1), rms[i:i + 2].reshape(-1))
              for i in range(len(mel) - 1)]
    return baseline_scores(baseline, np.asarray([x for x, _ in values]).reshape(-1, 8, 24),
                           np.asarray([r for _, r in values]))


def portable_predict(pcm, model):
    monitor = Monitor(model)
    pcm_buffer = monitor.spectrum.pcm
    for start in range(0, len(pcm) - HOP + 1, HOP):
        for i in range(len(pcm_buffer)):
            pcm_buffer[i] = int(pcm[start + i])
        if monitor.push(True) and monitor.score is not None:
            yield monitor.score


def episodes(scores, threshold, span, required):
    vote = Votes(threshold, span, required)
    confirmed = False
    starts = []
    for i, score in enumerate(scores):
        state = vote.step(score)
        if state and not confirmed:
            starts.append(i + 2)  # Availability at the nominal end of the 2 s window.
        confirmed = state
    return starts


def summary(scores, threshold, span, required, duration, background, interval):
    starts = episodes(scores, threshold, span, required)
    hits = scores >= threshold
    result = dict(windows=len(hits), hits=int(hits.sum()), episode_starts_s=starts)
    if background:
        result['episodes_per_hour_observed'] = len(starts) * 3600 / duration
    if interval:
        start, end = interval
        contained = (np.arange(len(scores)) >= start) & (np.arange(len(scores)) + 2 <= end)
        before = (np.arange(len(scores)) + 2 <= start)
        first = next((second for second in starts if start < second <= end), None)
        result.update(engine_window_hits=int(hits[contained].sum()),
                      engine_windows=int(contained.sum()), pre_engine_hits=int(hits[before].sum()),
                      nominal_confirmation_delay_s=None if first is None else first - start)
    return result


def replay(directory, baseline, model):
    classifier = Classifier(model)
    results = []
    for name in (*BACKGROUND, *TIMED, *UNTIMED):
        pcm = decode(directory / name)
        duration = len(pcm) / RATE
        if duration < 2:
            raise ValueError('At least two seconds of audio required: ' + name)
        original = baseline_predict(pcm, baseline)
        reference = [classifier.score(row) for row in all_windows(pcm, model.BURST_SAMPLES)]
        scores = np.fromiter(portable_predict(pcm, model), dtype=float)
        max_error = float(np.max(np.abs(scores - reference)))
        if max_error > 0.0005 or not np.array_equal(scores >= model.THRESHOLD,
                                                   np.asarray(reference) >= model.THRESHOLD):
            raise ValueError('Desktop/portable inference mismatch: ' + name)
        label = 'background' if name in BACKGROUND else 'engine example'
        results.append(dict(file=name, label=label, duration_s=duration, score_max_abs_error=max_error,
                            baseline=summary(original, baseline.THRESHOLD, 15, 9, duration,
                                             name in BACKGROUND, TIMED.get(name)),
                            burst=summary(scores, model.THRESHOLD, model.SPAN, model.REQUIRED,
                                          duration, name in BACKGROUND, TIMED.get(name))))
    return results


def benchmark(baseline, model):
    from algorithm.core.tg_cnn_v46 import score_features
    from algorithm.core.tg_temporal_v46 import MelFFT, RawChunk, make_row

    raw = tuple((i % 37 - 18) * 200 for i in range(4000))
    monitor = Monitor(model)
    fft = MelFFT()
    timing = {'v46_extract_ms': [], 'v46_score_ms': [], 'burst_extract_ms': [], 'burst_score_ms': []}
    previous = None
    for second in range(33):
        chunk = RawChunk(second)
        chunk.samples.extend(raw)
        chunk.total_samples = len(raw)
        t = perf_counter()
        fft.second(chunk)
        if previous is not None:
            row = make_row(previous, chunk, fft)
            timing['v46_extract_ms'].append(1000 * (perf_counter() - t))
            t = perf_counter()
            score_features(row['wide_patch'], row['energy_envelope'], baseline)
            timing['v46_score_ms'].append(1000 * (perf_counter() - t))
        previous = chunk

        extract = 0.0
        for i in range(FRAMES_PER_SECOND):
            for j in range(model.BURST_SAMPLES):
                monitor.spectrum.pcm[j] = raw[i * HOP + j]
            t = perf_counter()
            monitor.spectrum.extract(monitor.frames, monitor.cursor * (BANDS + 1))
            extract += 1000 * (perf_counter() - t)
            monitor.cursor = (monitor.cursor + 1) % WINDOW_FRAMES
        if second:
            timing['burst_extract_ms'].append(extract)
            t = perf_counter()
            summarize(monitor.frames, monitor.features)
            monitor.classifier.score(monitor.features)
            timing['burst_score_ms'].append(1000 * (perf_counter() - t))
    return {k: {'median': float(np.median(v[1:])), 'max': max(v[1:])} for k, v in timing.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio-dir', type=Path, default=Path('algorithm/sample_audio'))
    parser.add_argument('--baseline', type=Path,
                        default=Path('algorithm/results/v4_6_wideband/tg_model_v46.py'))
    parser.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    baseline, model = load_model(args.baseline), read_export(args.model)
    result = dict(recordings=replay(args.audio_dir, baseline, model),
                  cpython_benchmark=benchmark(baseline, model))
    with args.output.open('x', encoding='utf8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
