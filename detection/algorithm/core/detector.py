"""Threshold-based audio / vibration detection and temporal sensor fusion.

A warning means a suspicious sensor pattern, NOT evidence of an actual theft.
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


@dataclass
class Settings:
    window_s: float = 2.0
    hop_s: float = 1.0
    low_ratio_min: float = 0.48
    engine_confirm_windows: int = 3
    engine_memory_s: float = 18.0
    impact_memory_s: float = 14.0
    impacts_for_alarm: int = 2
    cooldown_s: float = 15.0
    audio_transient_min: float = 3.0
    # These absolute floors are intended ONLY for demo-scale sensor units.
    # Tune/calibrate them on measurements from the target sensor hardware.
    min_audio_rms: float = 0.012
    min_vibration_rms: float = 0.04
    min_vibration_peak: float = 0.10
    min_accel_dynamic_rms: float = 0.015
    min_accel_peak: float = 0.055


METRICS = ("audio_rms", "audio_transient", "vibration_rms", "vibration_peak",
           "accel_dynamic_rms", "accel_peak")


@dataclass
class Model:
    settings: Settings
    thresholds: dict[str, float]
    calibration: str

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 2, "settings": asdict(self.settings),
                                    "thresholds": self.thresholds,
                                    "calibration": self.calibration}, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "Model":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("version") != 2:
            raise ValueError("Model format unsupported. Run 'calibrate' again for version 2")
        return cls(Settings(**raw["settings"]), raw["thresholds"], raw["calibration"])


def calibrate(rows: list[dict], settings: Settings, *, quiet: bool = False) -> Model:
    """Quiet data: full baseline; otherwise use lower tail as rough heuristic.

    Self-calibration can fail when the entire recording is noisy / has an engine.
    Prefer a separate quiet baseline (--baseline-audio / --baseline-sensors).
    """
    if len(rows) < 5:
        raise ValueError("Need at least 5 analysis windows for calibration")
    floors = {"audio_rms": settings.min_audio_rms,
              "audio_transient": settings.audio_transient_min,
              "vibration_rms": settings.min_vibration_rms,
              "vibration_peak": settings.min_vibration_peak,
              "accel_dynamic_rms": settings.min_accel_dynamic_rms,
              "accel_peak": settings.min_accel_peak}
    thresholds: dict[str, float] = {}
    for metric in METRICS:
        values = np.asarray([row[metric] for row in rows if row.get(metric) is not None], dtype=float)
        if len(values) == 0:
            continue
        if not quiet:
            values = values[values <= np.quantile(values, 0.30)]
        med = float(np.median(values))
        mad = float(np.median(np.abs(values - med)))
        factor = 8.0 if metric in {"audio_rms", "audio_transient"} else 9.0
        # For audio transient, preserve minimum ratio; ratio is unitless.
        th = max(floors[metric], med + factor * 1.4826 * mad)
        thresholds[metric] = float(th)
    return Model(settings, thresholds, "separate_quiet_baseline" if quiet else "heuristic_low_30pct")


def classify(rows: list[dict], model: Model, mode: str) -> list[dict]:
    if mode not in {"audio", "vibration", "fusion"}:
        raise ValueError("mode must be audio, vibration, or fusion")
    if not rows:
        raise ValueError("No windows to classify")
    s, th = model.settings, model.thresholds
    engine_streak = 0
    last_engine_t = -float("inf")
    prev_motion = False
    impact_times: deque[float] = deque()
    last_alarm = -float("inf")
    previous_time = None
    output = []
    for raw in rows:
        t = float(raw["time_s"])
        if previous_time is not None:
            if t <= previous_time:
                raise ValueError("time_s must be strictly increasing")
            if t - previous_time > 1.5 * s.hop_s:
                engine_streak = 0
                prev_motion = False
                impact_times.clear()
                last_engine_t = -float("inf")
        previous_time = t
        has_audio = "audio_rms" in raw
        has_motion = "vibration_rms" in raw or "accel_dynamic_rms" in raw
        if mode in {"audio", "fusion"} and not has_audio:
            raise ValueError("No audio features; supply --audio")
        if mode in {"vibration", "fusion"} and not has_motion:
            raise ValueError("No sensor features; supply --sensors")

        engine_now = bool(has_audio and raw["audio_rms"] > th["audio_rms"]
                          and raw["audio_low_ratio"] >= s.low_ratio_min)
        audio_impact = bool(has_audio and raw["audio_rms"] >= th["audio_rms"] * 0.65
                            and raw["audio_transient"] > th["audio_transient"])
        engine_streak = engine_streak + 1 if engine_now else 0
        if engine_streak >= s.engine_confirm_windows:
            last_engine_t = t
        engine_recent = bool(t - last_engine_t <= s.engine_memory_s)

        v_hit = bool(raw.get("vibration_rms") is not None
                     and "vibration_rms" in th and "vibration_peak" in th
                     and raw["vibration_rms"] > th["vibration_rms"]
                     and raw["vibration_peak"] > th["vibration_peak"])
        a_hit = bool(raw.get("accel_dynamic_rms") is not None
                     and "accel_dynamic_rms" in th and "accel_peak" in th
                     and raw["accel_dynamic_rms"] > th["accel_dynamic_rms"]
                     and raw["accel_peak"] > th["accel_peak"])
        motion = bool(v_hit or a_hit)
        if motion and not prev_motion:
            impact_times.append(t)
        prev_motion = motion
        while impact_times and impact_times[0] < t - s.impact_memory_s:
            impact_times.popleft()

        if mode == "audio":
            alarm = 0  # No theft alert from microphone alone.
            if engine_recent and audio_impact:
                state = "ENGINE_AND_AUDIO_IMPACT"
            elif engine_recent:
                state = "ENGINE_SOUND"
            elif audio_impact:
                state = "AUDIO_IMPACT"
            else:
                state = "BACKGROUND"
        elif mode == "vibration":
            alarm = 0  # Motion alone is suspicious activity, not confirmed loading.
            state = "MOTION_DETECTED" if motion else "BACKGROUND"
        else:
            # Acoustic hit is auxiliary evidence, NOT a replacement for physical motion.
            possible_loading = engine_recent and len(impact_times) >= s.impacts_for_alarm
            alarm = int(possible_loading and (t - last_alarm > s.cooldown_s))
            if alarm:
                last_alarm = t
            if possible_loading:
                state = "POSSIBLE_LOADING"
            elif engine_recent:
                state = "ENGINE_ONLY"
            elif motion:
                state = "MOTION_ONLY"
            else:
                state = "BACKGROUND"
        row = dict(raw)
        row.update({"engine_detected": int(engine_now),
                    "engine_confirmed": int(engine_recent),
                    "audio_impact": int(audio_impact),
                    "vibration_detected": int(v_hit),
                    "accelerometer_detected": int(a_hit),
                    "motion_detected": int(motion),
                    "recent_motion_events": len(impact_times),
                    "state": state, "alarm": alarm})
        output.append(row)
    return output


def summarize(rows: list[dict], mode: str, model: Model) -> dict:
    states: dict[str, int] = {}
    for row in rows:
        states[row["state"]] = states.get(row["state"], 0) + 1
    return {"mode": mode, "windows": len(rows),
            "time_range_s": [float(rows[0]["time_s"]), float(rows[-1]["time_s"] + model.settings.window_s)],
            "state_counts": states,
            "engine_windows": sum(row["engine_detected"] for row in rows),
            "audio_impact_windows": sum(row["audio_impact"] for row in rows),
            "motion_windows": sum(row["motion_detected"] for row in rows),
            "alarm_count": sum(row["alarm"] for row in rows),
            "alarm_times_s": [row["time_s"] for row in rows if row["alarm"]],
            "thresholds": model.thresholds,
            "calibration": model.calibration,
            "warning": "Suspicious pattern only; NOT proof of theft. Thresholds require real data validation."}
