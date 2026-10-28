"""Independent extraction of microphone and motion features in aligned windows."""
from __future__ import annotations

import math

import numpy as np


def _rms(array: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(array)))) if len(array) else 0.0


def audio_window_features(samples: np.ndarray, sample_rate: int) -> dict[str, float]:
    """RMS, bass fraction and short transient (impact) relative to steady audio."""
    centered = samples.astype(np.float64) - float(np.mean(samples))
    rms = _rms(centered)
    power = np.abs(np.fft.rfft(centered * np.hanning(len(centered)))) ** 2
    freqs = np.fft.rfftfreq(len(centered), 1 / sample_rate)
    useful = (freqs >= 35) & (freqs <= min(3500, sample_rate / 2))
    bass = (freqs >= 40) & (freqs <= 250)
    low_ratio = float(np.sum(power[bass]) / (np.sum(power[useful]) + 1e-15))
    # Use 50 ms frames: impacts are brief rises compared with average sound.
    frame_size = max(32, int(round(0.05 * sample_rate)))
    trimmed = centered[:len(centered) // frame_size * frame_size]
    if len(trimmed):
        frame_rms = np.sqrt(np.mean(trimmed.reshape(-1, frame_size) ** 2, axis=1))
        transient = float(np.max(frame_rms) / max(float(np.median(frame_rms)), 1e-8))
    else:
        transient = 0.0
    return {"audio_rms": rms, "audio_low_ratio": low_ratio,
            "audio_transient": transient}


def motion_window_features(sensors: dict[str, np.ndarray], indices: slice) -> dict[str, float]:
    """Detrended vibration, accelerometer dynamics; no assumptions about units."""
    values = {}
    if "vibration" in sensors:
        v = sensors["vibration"][indices]
        centered = v - np.mean(v)
        values["vibration_rms"] = _rms(centered)
        values["vibration_peak"] = float(np.max(np.abs(centered)))
    else:
        values["vibration_rms"] = None
        values["vibration_peak"] = None
    if "accel_x" in sensors:
        axes = np.column_stack([sensors[k][indices] for k in ("accel_x", "accel_y", "accel_z")])
        centered_axes = axes - np.mean(axes, axis=0)
        magnitude = np.linalg.norm(centered_axes, axis=1)
        values["accel_dynamic_rms"] = _rms(magnitude)
        values["accel_peak"] = float(np.max(magnitude))
    else:
        values["accel_dynamic_rms"] = None
        values["accel_peak"] = None
    return values


def extract(audio: tuple[int, np.ndarray] | None, sensors: dict[str, np.ndarray] | None,
            window_s: float = 2.0, hop_s: float = 1.0) -> list[dict]:
    if window_s <= 0 or hop_s <= 0 or hop_s > window_s:
        raise ValueError("Require 0 < hop_s <= window_s")
    if audio is None and sensors is None:
        raise ValueError("No input was specified")
    starts = []
    ends = []
    if audio is not None:
        sample_rate, samples = audio
        starts.append(0.0)
        ends.append(len(samples) / sample_rate)
    if sensors is not None:
        ts = sensors["time_s"]
        dt = float(np.median(np.diff(ts)))
        starts.append(float(ts[0]))
        ends.append(float(ts[-1]) + dt)
    start, end = max(starts), min(ends)
    if end - start < window_s:
        raise ValueError("Input is shorter than a complete window or audio/sensors do not overlap")
    n_windows = math.floor((end - start - window_s + 1e-8) / hop_s) + 1
    result: list[dict] = []
    for i in range(n_windows):
        t0, t1 = start + i * hop_s, start + i * hop_s + window_s
        row: dict = {"time_s": round(t0, 5)}
        if audio is not None:
            i0, i1 = int(round(t0 * sample_rate)), int(round(t1 * sample_rate))
            frame = samples[i0:i1]
            if len(frame) < int(0.95 * sample_rate * window_s):
                continue
            row.update(audio_window_features(frame, sample_rate))
        if sensors is not None:
            ts = sensors["time_s"]
            first, last = np.searchsorted(ts, [t0, t1], side="left")
            indices = slice(first, last)
            dt = float(np.median(np.diff(ts)))
            sample_times = ts[indices]
            # For safe fusion, reject windows with sensor dropout or poor coverage.
            if (len(sample_times) < max(3, int(window_s / dt * 0.65))
                or sample_times[0] - t0 > 2.5 * dt
                or t1 - sample_times[-1] > 2.5 * dt
                or np.any(np.diff(sample_times) > 3.0 * dt)):
                continue
            row.update(motion_window_features(sensors, indices))
        result.append(row)
    if not result:
        raise ValueError("No usable windows: check sampling, timing and gaps in sensor CSV")
    return result
