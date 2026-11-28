"""Build burst features for the existing recording-level FSC22 split."""

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import numpy as np

from algorithm.app._dataset_utils import locate_archive, manifest_rows
from firmware.lib.tg_burst import BANDS, FRAMES_PER_SECOND, RATE, WINDOW_FRAMES, band_bins

SIZES = (256, 512)
HOP = RATE // FRAMES_PER_SECOND


def decode(source, rate=RATE, raw=None):
    """Decode a filename or WAV bytes to mono PCM16 with FFmpeg resampling."""
    cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-i', str(source),
           '-ac', '1', '-ar', str(rate), '-f', 's16le', 'pipe:1']
    result = subprocess.run(cmd, input=raw, capture_output=True, check=False)
    if result.returncode:
        raise ValueError('FFmpeg failed for %s: %s' % (source, result.stderr.decode(errors='replace')))
    return np.frombuffer(result.stdout, dtype='<i2')


def read_original(raw):
    # Match v4.6 preparation: first 16 kHz mono, then 4 kHz, cut to eight seconds.
    pcm16k = decode('pipe:0', rate=16000, raw=raw)[:8 * 16000]
    cmd = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
           '-f', 's16le', '-ar', '16000', '-ac', '1', '-i', 'pipe:0',
           '-ar', str(RATE), '-f', 's16le', 'pipe:1']
    return np.frombuffer(subprocess.run(cmd, input=pcm16k.tobytes(), capture_output=True,
                                       check=True).stdout, dtype='<i2')


def frame_features(pcm, size):
    starts = np.arange(0, len(pcm) - HOP + 1, HOP)
    frames = pcm[starts[:, None] + np.arange(size)].astype(np.float64)
    frames -= frames.mean(axis=1, keepdims=True)
    rms = np.sqrt(np.mean(frames ** 2, axis=1)) / 32768.0
    power = np.abs(np.fft.rfft(frames * np.hanning(size), axis=1)) ** 2
    bins = band_bins(size)
    bands = np.stack([power[:, start:end].mean(axis=1)
                      for start, end in zip(bins, bins[1:])], axis=1)
    bands = np.log(bands + 1e-6)
    bands = np.clip(bands - bands.mean(axis=1, keepdims=True), -10, 10)
    return np.column_stack((bands, np.log(rms + 1e-7)))


def features_at(frames, seconds):
    offsets = np.asarray(seconds, dtype=np.int64) * FRAMES_PER_SECOND
    windows = frames[offsets[:, None] + np.arange(WINDOW_FRAMES)]
    return np.column_stack((windows[:, :, :BANDS].mean(axis=1),
                            windows.std(axis=1), windows[:, :, BANDS].mean(axis=1)))


def all_windows(pcm, size):
    return features_at(frame_features(pcm, size), np.arange(max(0, len(pcm) // RATE - 1)))


def prepare(root, manifest, data_dir, output, workers):
    from algorithm.app.burst_train import load_baseline_cache

    rows, _, _, labels, splits = load_baseline_cache(root)
    _, records = manifest_rows(manifest)
    originals = {r['dataset'] + '/' + r['audio_member']: r for r in records}
    groups = defaultdict(list)
    for i, row in enumerate(rows):
        source = row['source'].split(':aug:', 1)[0]
        record = originals[source]
        if record['split'] != row['split'] or int(record['target_engine']) != int(labels[i]):
            raise ValueError('Manifest does not match existing split: ' + source)
        groups[row['source']].append(i)

    with ExitStack() as stack:
        archives = {}
        for r in records:
            path = locate_archive(r, data_dir)
            if path not in archives:
                archives[path] = stack.enter_context(zipfile.ZipFile(path))

        def extract(item):
            source, indices = item
            row = rows[indices[0]]
            if row['split'] == 'train':
                pcm = decode(root / 'teacher_audio' / row['teacher_audio'])
            else:
                record = originals[source]
                archive = archives[locate_archive(record, data_dir)]
                raw = archive.read(record['audio_member'])
                if hashlib.sha256(raw).hexdigest() != record['sha256'].lower():
                    raise ValueError('Recording hash mismatch: ' + source)
                pcm = read_original(raw)
            seconds = [float(rows[i]['time_s']) for i in indices]
            if any(not second.is_integer() or second < 0 for second in seconds):
                raise ValueError('Unexpected window timestamp: ' + source)
            data = [features_at(frame_features(pcm, size), seconds) for size in SIZES]
            return indices, data, pcm if row['split'] != 'train' else None

        features = {f'fft{size}': np.empty((len(rows), 2 * BANDS + 2), dtype=np.float32)
                    for size in SIZES}
        heldout_audio = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for n, (indices, data, pcm) in enumerate(executor.map(extract, groups.items()), 1):
                for size, values in zip(SIZES, data):
                    features[f'fft{size}'][indices] = values
                if pcm is not None:
                    heldout_audio[rows[indices[0]]['source']] = pcm
                if n % 200 == 0 or n == len(groups):
                    print(f'Extracted {n}/{len(groups)} files', flush=True)
    add_stress(features, heldout_audio, originals)
    features['windows_sha256'] = hashlib.sha256((root / 'windows.csv').read_bytes()).hexdigest()
    features['labels'] = labels
    features['splits'] = splits
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        np.savez_compressed(stream, **features)


def add_stress(features, audio, records):
    """Mix held-out engines with forest background from their own split, at 0 dB."""
    from algorithm.app.v4_6_prepare import features_per_second_pcm

    rng = np.random.default_rng(2026)
    for split in ('val', 'test'):
        engines = sorted(key for key in audio if records[key]['split'] == split
                         and records[key]['target_engine'] == '1')
        backgrounds = sorted(key for key in audio if records[key]['split'] == split
                             and records[key]['dataset'] == 'FSC22'
                             and records[key]['target_engine'] == '0')
        tables = defaultdict(list)
        for key in engines:
            noise = audio[backgrounds[int(rng.integers(len(backgrounds)))]]
            engine = audio[key].astype(np.float64)
            shift = int(rng.integers(len(noise)))
            bg = noise[(np.arange(len(engine)) + shift) % len(noise)].astype(np.float64)
            engine -= engine.mean()
            bg -= bg.mean()
            power = np.dot(bg, bg)
            if not power or not np.any(engine):
                raise ValueError('Silent held-out stress-test input')
            mix = engine + bg * np.sqrt(np.dot(engine, engine) / power)
            mix = np.rint(mix * min(1.0, 32000 / np.max(np.abs(mix)))).astype('<i2')
            for size in SIZES:
                tables[f'fft{size}'].append(all_windows(mix, size))
            mel, rms = features_per_second_pcm(mix)
            tables['mel'].extend(np.stack((mel[:-1], mel[1:]), axis=1).reshape(-1, 8, 24))
            tables['rms'].extend(np.concatenate((rms[:-1], rms[1:]), axis=1))
        for name, values in tables.items():
            features[f'{split}_{name}'] = (np.concatenate(values) if name.startswith('fft')
                                          else np.asarray(values))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=Path('algorithm/results/v4_2_fsc22'))
    parser.add_argument('--manifest', type=Path, default=Path('algorithm/data/dataset_manifest_fsc22.csv'))
    parser.add_argument('--data-dir', type=Path, default=Path('algorithm/data'))
    parser.add_argument('--output', type=Path, default=Path('algorithm/results/burst/features.npz'))
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    prepare(args.results, args.manifest, args.data_dir, args.output, args.workers)


if __name__ == '__main__':
    main()
