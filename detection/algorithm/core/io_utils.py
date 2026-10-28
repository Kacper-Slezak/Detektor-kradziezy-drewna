"""I/O for audio and accelerometer/vibration CSVs."""
from __future__ import annotations

import csv
import math
import subprocess
from pathlib import Path

import numpy as np


def read_audio(path: str | Path, target_rate: int = 8000) -> tuple[int, np.ndarray]:
    """Decode WAV or MP3 to mono float32 via bundled FFmpeg (no system install)."""
    import imageio_ffmpeg

    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Audio does not exist: {path}")
    if path.suffix.lower() not in {".wav", ".mp3"}:
        raise ValueError("Supported audio formats: .wav, .mp3")
    if not 2000 <= target_rate <= 48000:
        raise ValueError("target_rate must be between 2000 and 48000")
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-nostdin",
               "-i", str(path), "-ac", "1", "-ar", str(target_rate),
               "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"]
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if process.returncode:
        error = process.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Could not decode {path}: {error[:400]}")
    samples = np.frombuffer(process.stdout, dtype="<f4").copy()
    if not len(samples):
        raise ValueError("Audio file has no decodable samples")
    if not np.all(np.isfinite(samples)):
        raise ValueError("Audio contains NaN or infinity")
    return target_rate, samples


def read_sensors(path: str | Path, offset_s: float = 0.0) -> dict[str, np.ndarray]:
    """Required time_s and at least vibration OR all accel_x/y/z.

    Each optional measurement is retained in original units. Vibration may be
    analog amplitude or a binary switching signal. Binary inputs need a suitable
    detector configuration; see README.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Sensor CSV does not exist: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = set(reader.fieldnames or [])
        has_vibration = "vibration" in fields
        has_acceleration = all(x in fields for x in ("accel_x", "accel_y", "accel_z"))
        if "time_s" not in fields or not (has_vibration or has_acceleration):
            raise ValueError("Sensor CSV needs time_s and vibration and/or accel_x,accel_y,accel_z")
        output: dict[str, list[float]] = {"time_s": []}
        if has_vibration:
            output["vibration"] = []
        if has_acceleration:
            for key in ("accel_x", "accel_y", "accel_z"):
                output[key] = []
        for index, row in enumerate(reader, 2):
            for key in output:
                try:
                    v = float(row[key])
                except (ValueError, TypeError) as exc:
                    raise ValueError(f"Invalid {key} at row {index} in {path}") from exc
                if not math.isfinite(v):
                    raise ValueError(f"Non-finite {key} at row {index} in {path}")
                output[key].append(v + offset_s if key == "time_s" else v)
    data = {key: np.asarray(values, dtype=float) for key, values in output.items()}
    times = data["time_s"]
    if len(times) < 10 or np.any(np.diff(times) <= 0):
        raise ValueError("Sensor CSV needs >=10 rows with strictly increasing time_s")
    return data


def write_csv(path: str | Path, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("Cannot write empty CSV")
    keys = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def make_json_serializable(value):
    if isinstance(value, dict):
        return {key: make_json_serializable(v) for key, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [make_json_serializable(v) for v in value]
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    return value
