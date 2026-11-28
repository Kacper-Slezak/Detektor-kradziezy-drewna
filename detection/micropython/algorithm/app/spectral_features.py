"""NumPy reference for the fixed 4 kHz spectral probe."""

import numpy as np

from algorithm.app.burst_prepare import HOP, features_at
from firmware.lib.tg_burst import RATE, band_bins
from firmware.lib.tg_spectral_probe import REGIONS


def extract(pcm):
    """Return aligned two-second features, using one FFT per captured frame."""
    starts = np.arange(len(pcm) // RATE * 4) * HOP
    frames = pcm[starts[:, None] + np.arange(512)].astype(np.float64)
    frames -= frames.mean(axis=1, keepdims=True)
    power = np.abs(np.fft.rfft(frames * np.hanning(512), axis=1)) ** 2
    bins = band_bins(512)
    bands = np.stack([power[:, first:end].mean(axis=1)
                      for first, end in zip(bins, bins[1:])], axis=1)
    bands = np.log(bands + 1e-6)
    bands = np.clip(bands - bands.mean(axis=1, keepdims=True), -10, 10)
    rms = np.log(frames.std(axis=1) / 32768 + 1e-7)
    seconds = np.arange(max(0, len(pcm) // RATE - 1))
    base = features_at(np.column_stack((bands, rms)), seconds)

    offsets = seconds[:, None] * 4 + np.arange(8)
    spectral, temporal = [], []
    for start, stop in REGIONS:
        region = power[:, start:stop]
        triples = region[:, :-2] + region[:, 1:-1] + region[:, 2:]
        center = triples.argmax(axis=1) + 1
        height = triples.max(axis=1)
        total = region.sum(axis=1)
        near = np.arange(region.shape[1])[None, :] - center[:, None]
        shoulder = (abs(near) >= 2) & (abs(near) <= 5)
        low_energy = total < 1e-3
        concentration = np.clip(np.log((height + 1e-6) / (total + 1e-6)), -9, 0)
        contrast = np.clip(np.log((height / 3 + 1e-6) /
                                  ((region * shoulder).sum(axis=1) / shoulder.sum(axis=1) + 1e-6)), -2, 8)
        concentration[low_energy] = 0
        contrast[low_energy] = 0
        center[low_energy] = -1
        spectra = contrast[offsets]
        centers = center[offsets]
        stable = ((centers[:, 1:] >= 0) & (centers[:, :-1] >= 0)
                  & (abs(np.diff(centers, axis=1)) <= 2))
        spectral.extend((concentration[offsets].mean(axis=1), spectra.mean(axis=1)))
        pair = np.where(stable, np.minimum(spectra[:, 1:], spectra[:, :-1]), 0)
        temporal.extend((stable.mean(axis=1), np.maximum(0, pair.max(axis=1))))
    return np.column_stack((base, *spectral, *temporal)).astype(np.float32)
