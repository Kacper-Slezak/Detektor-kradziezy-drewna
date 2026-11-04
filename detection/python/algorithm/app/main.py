"""Command-line entry point: python -m detection.app.main --help"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..core.charts import plot
from ..core.detector import Model, Settings, calibrate, classify, summarize
from ..core.features import extract
from ..core.io_utils import read_audio, read_sensors, write_csv
from ..data.demo_data import generate

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"


def _inputs(audio_path, sensor_path, *, offset_s: float = 0):
    audio = read_audio(audio_path) if audio_path else None
    sensors = read_sensors(sensor_path, offset_s) if sensor_path else None
    return audio, sensors


def _process(mode: str, audio_path: str | None, sensor_path: str | None,
             target: Path, model_path: str | None = None,
             baseline_audio: str | None = None, baseline_sensors: str | None = None,
             sensor_offset: float = 0, window_s: float = 2.0, hop_s: float = 1.0,
             low_ratio_min: float = 0.48) -> dict:
    if mode == "audio" and not audio_path:
        raise ValueError("Audio mode requires --audio")
    if mode == "vibration" and not sensor_path:
        raise ValueError("Vibration mode requires --sensors")
    if mode == "fusion" and (not audio_path or not sensor_path):
        raise ValueError("Fusion mode requires both --audio and --sensors")
    if model_path and (baseline_audio or baseline_sensors):
        raise ValueError("Choose --model OR --baseline-audio/--baseline-sensors")
    if baseline_audio and not audio_path:
        raise ValueError("--baseline-audio requires --audio")
    if baseline_sensors and not sensor_path:
        raise ValueError("--baseline-sensors requires --sensors")
    settings = Settings(window_s=window_s, hop_s=hop_s, low_ratio_min=low_ratio_min)
    audio, sensors = _inputs(audio_path, sensor_path, offset_s=sensor_offset)
    features = extract(audio if mode != "vibration" else None,
                       sensors if mode != "audio" else None, settings.window_s, settings.hop_s)
    if model_path:
        model = Model.load(model_path)
        if (abs(model.settings.window_s - settings.window_s) > 1e-8
            or abs(model.settings.hop_s - settings.hop_s) > 1e-8):
            raise ValueError("--window-s / --hop-s must match saved --model")
    elif baseline_audio or baseline_sensors:
        # Separate baseline recordings may have different durations; process independently.
        baseline = []
        if baseline_audio:
            b_audio, _ = _inputs(baseline_audio, None)
            baseline.extend(extract(b_audio, None, settings.window_s, settings.hop_s))
        if baseline_sensors:
            _, b_sensors = _inputs(None, baseline_sensors)
            baseline.extend(extract(None, b_sensors, settings.window_s, settings.hop_s))
        model = calibrate(baseline, settings, quiet=True)
        # If the user supplies only one modality baseline in fusion, calibrate the
        # remaining modality with heuristic thresholds (not demo-device thresholds).
        fallback = calibrate(features, settings, quiet=False)
        missing_from_baseline = set(fallback.thresholds) - set(model.thresholds)
        for metric, threshold in fallback.thresholds.items():
            model.thresholds.setdefault(metric, threshold)
        if missing_from_baseline:
            model.calibration = "mixed_quiet_and_heuristic"
    else:
        model = calibrate(features, settings, quiet=False)
    # Audio impact threshold always exists with an audio channel, and all thresholds
    # necessary for the selected mode must exist to prevent silent bad output.
    required = []
    if mode in {"audio", "fusion"}:
        required += ["audio_rms", "audio_transient"]
    if mode in {"vibration", "fusion"}:
        if any(row.get("vibration_rms") is not None for row in features):
            required += ["vibration_rms", "vibration_peak"]
        if any(row.get("accel_dynamic_rms") is not None for row in features):
            required += ["accel_dynamic_rms", "accel_peak"]
    missing = set(required) - set(model.thresholds)
    if missing:
        raise ValueError(f"Model lacks thresholds: {', '.join(sorted(missing))}")
    results = classify(features, model, mode)
    target.mkdir(parents=True, exist_ok=True)
    write_csv(target / "features.csv", features)
    write_csv(target / "predictions.csv", results)
    model.save(target / "model.json")
    chart = target / "result.png"
    plot(results, model, mode, chart, audio if mode == "audio" else None)
    summary = summarize(results, mode, model)
    summary["audio_file"] = str(Path(audio_path).resolve()) if audio_path else None
    summary["sensor_file"] = str(Path(sensor_path).resolve()) if sensor_path else None
    (target / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[{mode}] {len(results)} windows; {summary['alarm_count']} alerts")
    print(f"  States: {summary['state_counts']}")
    print(f"  Results: {target.resolve()}")
    if summary["calibration"] != "separate_quiet_baseline":
        print("  NOTE: threshold calibration is provisional; validate on quiet site recordings")
    return summary


def _demo(out: Path, args):
    print("Generating reproducible synthetic calibration + scenario signals ...")
    source = out / "raw_demo"
    generate(source)
    audio = source / "scenario" / "microphone.wav"
    sensors = source / "scenario" / "sensors.csv"
    baseline_audio = source / "calibration" / "microphone.wav"
    baseline_sensors = source / "calibration" / "sensors.csv"
    for mode in ("audio", "vibration", "fusion"):
        _process(mode, str(audio) if mode != "vibration" else None,
                 str(sensors) if mode != "audio" else None,
                 out / mode,
                 baseline_audio=str(baseline_audio) if mode != "vibration" else None,
                 baseline_sensors=str(baseline_sensors) if mode != "audio" else None,
                 window_s=args.window_s, hop_s=args.hop_s)
    print("Demo contains background, passing truck, stationary truck and loading impacts.")
    print("WARNING: these results do NOT estimate performance on real field data.")


def main():
    p = argparse.ArgumentParser(description="Timber Guard: WAV/MP3 audio, vibration, sensor fusion")
    commands = p.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Generate data and plots for all modes")
    demo.add_argument("--out", type=Path, default=RESULTS_DIR / "demo")
    demo.add_argument("--window-s", type=float, default=2.0)
    demo.add_argument("--hop-s", type=float, default=1.0)
    analyze = commands.add_parser("analyze", help="Analyze custom WAV/MP3 and/or sensor CSV")
    analyze.add_argument("--mode", choices=("audio", "vibration", "fusion", "all"), required=True)
    analyze.add_argument("--audio", help="Any WAV or MP3 (path may contain spaces)")
    analyze.add_argument("--sensors", help="CSV: time_s and vibration or accel_x/y/z")
    analyze.add_argument("--model", help="Previously saved model.json from quiet calibration")
    analyze.add_argument("--baseline-audio", help="Optional separate quiet WAV/MP3")
    analyze.add_argument("--baseline-sensors", help="Optional separate quiet sensor CSV")
    analyze.add_argument("--sensor-offset", type=float, default=0.0,
                         help="Seconds added to sensor time_s for alignment (fusion)")
    analyze.add_argument("--out", type=Path, default=RESULTS_DIR / "custom")
    analyze.add_argument("--window-s", type=float, default=2.0)
    analyze.add_argument("--hop-s", type=float, default=1.0)
    analyze.add_argument("--low-ratio", type=float, default=0.48,
                         help="Min fraction of spectral power in 40-250 Hz for engine")
    cal = commands.add_parser("calibrate", help="Create a reusable model from QUIET recordings")
    cal.add_argument("--audio", help="Quiet microphone WAV/MP3")
    cal.add_argument("--sensors", help="Quiet sensor CSV")
    cal.add_argument("--out", type=Path, default=RESULTS_DIR / "quiet_model.json")
    cal.add_argument("--window-s", type=float, default=2.0)
    cal.add_argument("--hop-s", type=float, default=1.0)
    cal.add_argument("--low-ratio", type=float, default=0.48)
    args = p.parse_args()
    try:
        if args.command == "demo":
            _demo(args.out, args)
        elif args.command == "analyze":
            if args.mode == "all" and (not args.audio or not args.sensors):
                raise ValueError("--mode all requires --audio and --sensors")
            modes = ("audio", "vibration", "fusion") if args.mode == "all" else (args.mode,)
            for mode in modes:
                _process(mode,
                         args.audio if mode != "vibration" else None,
                         args.sensors if mode != "audio" else None,
                         args.out / mode,
                         model_path=args.model,
                         baseline_audio=args.baseline_audio if mode != "vibration" else None,
                         baseline_sensors=args.baseline_sensors if mode != "audio" else None,
                         sensor_offset=args.sensor_offset,
                         window_s=args.window_s, hop_s=args.hop_s,
                         low_ratio_min=args.low_ratio)
        else:
            if not args.audio and not args.sensors:
                raise ValueError("Calibrate requires --audio and/or --sensors")
            settings = Settings(window_s=args.window_s, hop_s=args.hop_s,
                                low_ratio_min=args.low_ratio)
            a, s = _inputs(args.audio, args.sensors)
            # Quiet files don't need to align in time: calibrate each individually.
            rows = []
            if a is not None:
                rows.extend(extract(a, None, settings.window_s, settings.hop_s))
            if s is not None:
                rows.extend(extract(None, s, settings.window_s, settings.hop_s))
            model = calibrate(rows, settings, quiet=True)
            model.save(args.out)
            print(f"Calibrated {len(rows)} QUIET baseline windows -> {args.out.resolve()}")
            print("Thresholds:", json.dumps(model.thresholds, indent=2))
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        p.error(str(exc))


if __name__ == "__main__":
    main()
