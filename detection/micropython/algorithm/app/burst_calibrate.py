"""Prepare development-only forest negatives and forest/engine training mixes."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path

import numpy as np

from algorithm.app.burst_prepare import SIZES, all_windows, decode
from algorithm.app.burst_train import SEED, load_baseline_cache
from firmware.lib.tg_burst import RATE


def prepare(root, forest, output):
    rows, _, _, _, _ = load_baseline_cache(root)
    files = {r['source']: r['teacher_audio'] for r in rows
             if r['split'] == 'train' and r['label'] == '1' and r['augmented'] == '0'}
    noise = decode(forest).astype(np.float64)
    if len(noise) < 8 * RATE:
        raise ValueError('Supply at least eight seconds of background audio')
    samples = {size: [all_windows(noise, size)] for size in SIZES}
    count = len(samples[SIZES[0]][0])
    original_ids = ['development_forest'] * count
    labels = [0] * count
    rng = np.random.default_rng(SEED)
    with ThreadPoolExecutor(max_workers=4) as executor:
        files_pcm = executor.map(decode, (root / 'teacher_audio' / name for name in files.values()))
        for source, pcm in zip(files, files_pcm):
            engine = pcm.astype(np.float64)
            engine -= engine.mean()
            power = np.dot(engine, engine)
            if not power:
                continue
            for snr in (-8, -2, 4):
                shift = int(rng.integers(len(noise)))
                clip = noise[(np.arange(len(engine)) + shift) % len(noise)].copy()
                clip -= clip.mean()
                noise_power = np.dot(clip, clip)
                if not noise_power:
                    raise ValueError('Silent development background segment')
                mix = engine + clip * np.sqrt(power / (noise_power * 10 ** (snr / 10)))
                mix = np.rint(mix * min(1.0, 32000 / np.max(np.abs(mix)))).astype('<i2')
                for size in SIZES:
                    result = all_windows(mix, size)
                    samples[size].append(result)
                original_ids.extend([source] * len(result))
                labels.extend([1] * len(result))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        np.savez_compressed(stream, **{f'fft{size}': np.concatenate(samples[size]) for size in SIZES},
                            sources=np.asarray(original_ids), labels=np.asarray(labels),
                            forest_sha256=hashlib.sha256(forest.read_bytes()).hexdigest(),
                            windows_sha256=hashlib.sha256((root / 'windows.csv').read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=Path('algorithm/results/v4_2_fsc22'))
    parser.add_argument('--forest', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('algorithm/results/burst/calibration.npz'))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    prepare(args.results, args.forest, args.output)


if __name__ == '__main__':
    main()
