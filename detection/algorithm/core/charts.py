"""Mode-specific, publication-friendly diagnostic charts."""
from __future__ import annotations

from pathlib import Path

import numpy as np


def _get(rows: list[dict], field: str):
    return np.asarray([float(r.get(field, 0) or 0) for r in rows], dtype=float)


def _shade(ax, t, flags, hop_s, label=None, color="tab:orange", alpha=0.13):
    if len(t) == 0:
        return
    active = False
    begin = 0
    used = False
    for i in range(len(t) + 1):
        flagged = i < len(t) and bool(flags[i])
        if flagged and not active:
            begin = i
            active = True
        if not flagged and active:
            ax.axvspan(t[begin], t[i - 1] + hop_s, color=color, alpha=alpha,
                       label=label if not used else None)
            active = False
            used = True


def plot(rows: list[dict], model, mode: str, destination: str | Path,
         audio: tuple[int, np.ndarray] | None = None) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    t = _get(rows, "time_s")
    th = model.thresholds
    hop_s = model.settings.hop_s
    if mode == "audio":
        fig, axes = plt.subplots(5, 1, figsize=(15, 13), constrained_layout=True)
        if audio is not None:
            sr, samples = audio
            stride = max(1, int(len(samples) / 22000))
            time = np.arange(0, len(samples), stride) / sr
            axes[0].plot(time, samples[::stride], lw=0.5, color="tab:blue")
            axes[0].set_ylabel("Amplitude")
            axes[0].set_title("Microphone waveform (mono)")
            # Narrow-band, log-dB spectrogram for the low-frequency engine plus impacts.
            from matplotlib.mlab import specgram
            spec, f, tt = specgram(samples, NFFT=min(1024, len(samples)),
                                   Fs=sr, noverlap=min(768, max(0, len(samples) - 1)))
            keep = (f >= 35) & (f <= min(3500, sr / 2))
            z = 10 * np.log10(np.maximum(spec[keep], 1e-12))
            image = axes[1].pcolormesh(tt, f[keep], z, shading="auto", cmap="viridis",
                                        vmin=np.percentile(z, 15), vmax=np.percentile(z, 99))
            axes[1].set_yscale("log")
            axes[1].set_ylim(35, min(3500, sr / 2))
            axes[1].set_title("Audio spectrogram (frequency / time)")
            axes[1].set_ylabel("Frequency (Hz)")
            fig.colorbar(image, ax=axes[1], label="Power (dB)", pad=0.01)
        else:
            axes[0].text(0.5, 0.5, "No raw waveform", ha="center", va="center", transform=axes[0].transAxes)
            axes[1].text(0.5, 0.5, "No raw spectrogram", ha="center", va="center", transform=axes[1].transAxes)
        axes[2].plot(t, _get(rows, "audio_rms"), color="tab:blue", label="Audio RMS")
        axes[2].axhline(th["audio_rms"], ls="--", color="tab:red", label="RMS threshold")
        axes[2].set_ylabel("RMS")
        axes[2].legend(loc="upper right")
        axes[2].set_title("Loudness threshold")
        axes[3].plot(t, _get(rows, "audio_low_ratio"), label="Bass / total energy (40-250 Hz)")
        axes[3].axhline(model.settings.low_ratio_min, ls="--", color="tab:red", label="Engine spectral threshold")
        axes[3].set_ylim(0, 1.05)
        axes[3].set_ylabel("Bass fraction")
        axes[3].set_title("Low-frequency evidence for motor/engine")
        axes[3].legend(loc="upper right")
        axes[4].plot(t, _get(rows, "audio_transient"), label="50 ms transient / median")
        axes[4].axhline(th["audio_transient"], ls="--", color="tab:red", label="Transient threshold")
        _shade(axes[4], t, _get(rows, "engine_confirmed"), hop_s, "Confirmed engine", "tab:orange")
        markers = t[_get(rows, "audio_impact") > 0]
        if len(markers):
            axes[4].scatter(markers, np.interp(markers, t, _get(rows, "audio_transient")),
                            marker="x", s=25, color="tab:purple", label="Audio impulse")
        axes[4].set_ylabel("Peak / median")
        axes[4].set_title("Impact transients and engine periods (audio only, no theft alarm)")
        axes[4].legend(loc="upper right")
        axes[4].set_xlabel("Time (s)")
    elif mode == "vibration":
        fig, axes = plt.subplots(4, 1, figsize=(15, 11), sharex=True, constrained_layout=True)
        if "vibration_rms" in th:
            axes[0].plot(t, _get(rows, "vibration_rms"), label="Vibration RMS")
            axes[0].axhline(th["vibration_rms"], ls="--", color="tab:red", label="Threshold")
        else:
            axes[0].text(0.4, .5, "No vibration channel", transform=axes[0].transAxes)
        axes[0].set_title("Vibration energy")
        axes[0].set_ylabel("Sensor units")
        axes[0].legend(loc="upper right") if "vibration_rms" in th else None
        if "vibration_peak" in th:
            axes[1].plot(t, _get(rows, "vibration_peak"), label="Vibration peak")
            axes[1].axhline(th["vibration_peak"], ls="--", color="tab:red", label="Threshold")
        else:
            axes[1].text(0.4, .5, "No vibration channel", transform=axes[1].transAxes)
        axes[1].set_title("Vibration transients")
        axes[1].set_ylabel("Sensor units")
        axes[1].legend(loc="upper right") if "vibration_peak" in th else None
        if "accel_dynamic_rms" in th:
            axes[2].plot(t, _get(rows, "accel_dynamic_rms"), label="Accelerometer dynamic RMS")
            axes[2].axhline(th["accel_dynamic_rms"], ls="--", color="tab:red", label="Threshold")
            axes[2].legend(loc="upper right")
        else:
            axes[2].text(0.4, .5, "No accelerometer channel", transform=axes[2].transAxes)
        axes[2].set_title("Accelerometer dynamics (gravity removed)")
        axes[2].set_ylabel("Sensor units")
        axes[3].step(t, _get(rows, "motion_detected"), where="post", label="Motion detected")
        axes[3].step(t, _get(rows, "recent_motion_events"), where="post", label="Recent separate impacts", alpha=.75)
        axes[3].set_title("Motion events (no theft alarm without audio)")
        axes[3].set_xlabel("Time (s)")
        axes[3].legend(loc="upper right")
    else:
        fig, axes = plt.subplots(4, 1, figsize=(15, 11), sharex=True, constrained_layout=True)
        axes[0].plot(t, _get(rows, "audio_rms"), label="Audio RMS")
        axes[0].axhline(th["audio_rms"], ls="--", color="tab:red", label="Audio threshold")
        _shade(axes[0], t, _get(rows, "engine_confirmed"), hop_s, "Engine confirmed", "tab:orange", .20)
        axes[0].set_ylabel("RMS")
        axes[0].set_title("Criterion 1: engine-like sound")
        axes[0].legend(loc="upper right")
        if "vibration_rms" in th:
            axes[1].plot(t, _get(rows, "vibration_rms"), label="Vibration RMS")
            axes[1].axhline(th["vibration_rms"], ls="--", color="tab:red", label="Vibration threshold")
        if "accel_dynamic_rms" in th:
            axes[1].plot(t, _get(rows, "accel_dynamic_rms"), label="Accel dynamic RMS", alpha=.65)
            axes[1].axhline(th["accel_dynamic_rms"], ls=":", color="tab:purple", label="Accel threshold")
        _shade(axes[1], t, _get(rows, "motion_detected"), hop_s, "Motion event", "tab:green")
        axes[1].set_ylabel("Sensor units")
        axes[1].set_title("Criterion 2: mechanical motion")
        axes[1].legend(loc="upper right")
        axes[2].step(t, _get(rows, "engine_confirmed"), where="post", label="Engine present/recent")
        axes[2].step(t, _get(rows, "recent_motion_events"), where="post", label="Recent motion bursts")
        axes[2].axhline(model.settings.impacts_for_alarm, ls="--", color="tab:red", label="Required impacts")
        axes[2].set_title("Temporal fusion: engine + repeated motion bursts")
        axes[2].legend(loc="upper right")
        state_levels = {"BACKGROUND": 0, "MOTION_ONLY": 1, "ENGINE_ONLY": 2, "POSSIBLE_LOADING": 3}
        levels = [state_levels.get(row["state"], 0) for row in rows]
        axes[3].step(t, levels, where="post", lw=1.8)
        alarms = t[_get(rows, "alarm") > 0]
        if len(alarms):
            axes[3].scatter(alarms, [3] * len(alarms), s=65, marker="x", color="tab:red", label="Alarm notification")
        axes[3].set_yticks(list(state_levels.values()), list(state_levels))
        axes[3].set_title("Fused classification + alerts")
        axes[3].set_xlabel("Time (s)")
        axes[3].legend(loc="upper right") if len(alarms) else None
    for axis in axes:
        axis.grid(alpha=0.23)
    fig.suptitle(f"Timber Guard | {mode.upper()} | {model.calibration}", fontsize=15)
    fig.savefig(destination, dpi=130)
    plt.close(fig)
