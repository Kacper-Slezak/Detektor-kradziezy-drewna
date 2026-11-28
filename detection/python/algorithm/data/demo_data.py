"""Synthetic sensor recordings to test the *pipeline*, not real-world accuracy."""
from __future__ import annotations

import csv
import wave
from pathlib import Path

import numpy as np


def _wav_write(path: Path, samples: np.ndarray, rate: int) -> None:
    pcm = np.round(np.clip(samples, -0.999, 0.999) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(pcm.tobytes())


def _synth(path: Path, duration: float, *, events: bool, rng: np.random.Generator) -> None:
    path.mkdir(parents=True, exist_ok=True)
    audio_rate = 8000
    sensor_rate = 100
    ta = np.arange(round(duration * audio_rate)) / audio_rate
    ts = np.arange(round(duration * sensor_rate)) / sensor_rate

    # Some stationary environmental noise: mic and sensors not identical.
    audio = 0.015 * rng.normal(size=len(ta))
    audio += 0.006 * np.sin(2 * np.pi * 430 * ta)
    ax = 0.006 * rng.normal(size=len(ts))
    ay = 0.006 * rng.normal(size=len(ts))
    az = 1.0 + 0.006 * rng.normal(size=len(ts))  # Approx 1g gravity.
    vib = 0.022 * rng.normal(size=len(ts))

    if events:
        # Truck passes nearby 20-40s; later truck stays 50-91s for loading.
        active_audio = ((ta >= 20) & (ta < 40)) | ((ta >= 50) & (ta < 91))
        engine = (0.10 * np.sin(2 * np.pi * (72 * ta + 0.02 * ta**2))
                  + 0.053 * np.sin(2 * np.pi * 143 * ta))
        audio[active_audio] += engine[active_audio]
        # Mild background vibration from a stationary running truck, below
        # loading impact threshold (not falsely sufficient for alarm).
        running = (ts >= 50) & (ts < 91)
        vib[running] += 0.01 * np.sin(2 * np.pi * 7 * ts[running])

        # Five distinct simulated log-loading impacts, spaced > window width.
        for impact_time in (56.0, 62.0, 68.0, 74.0, 80.0):
            age = ts - impact_time
            pulse = np.where((age >= 0) & (age < 0.8),
                             np.exp(-np.maximum(age, 0) * 5.0)
                             * np.sin(2 * np.pi * 21 * age), 0.0)
            vib += 1.4 * pulse
            ax += 0.36 * pulse
            ay += 0.22 * pulse
            az += 0.17 * pulse
            # Audible metallic/wood collision as a short transient.
            audio_age = ta - impact_time
            hit = np.where((audio_age >= 0) & (audio_age < 0.3),
                           np.exp(-np.maximum(audio_age, 0) * 20)
                           * np.sin(2 * np.pi * 620 * audio_age), 0)
            audio += 0.72 * hit
    _wav_write(path / "microphone.wav", audio, audio_rate)
    with (path / "sensors.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time_s", "accel_x", "accel_y", "accel_z", "vibration"])
        for row in zip(ts, ax, ay, az, vib):
            writer.writerow((f"{row[0]:.3f}", *(f"{x:.7f}" for x in row[1:])))

    # Ground truth is a manually defined scenario interval, for convenience.
    # Positive labels denote time with modeled actual log movement, NOT all
    # windows in which the model should continue considering the site risky.
    with (path / "scenario.txt").open("w", encoding="utf-8") as fh:
        if events:
            fh.write("0-20: background\n20-40: truck only (negative)\n"
                     "40-50: background\n50-56: truck parked\n"
                     "56-81: simulated loading impacts (positive)\n"
                     "81-91: truck stays; no new impacts\n91-110: background\n")
        else:
            fh.write("Quiet background only, for calibration.\n")


def generate(root: str | Path, *, seed: int = 42) -> None:
    root = Path(root)
    rng = np.random.default_rng(seed)
    _synth(root / "calibration", 40, events=False, rng=rng)
    _synth(root / "scenario", 110, events=True, rng=rng)
