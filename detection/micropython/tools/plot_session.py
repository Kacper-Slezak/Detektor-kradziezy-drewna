"""Build 3 illustrative plots from LIVE LoPy telemetry, no simulated readings."""
import argparse
import json
from pathlib import Path


def read_records(path):
    values = []
    with path.open(encoding='utf-8') as src:
        for line in src:
            raw = line.strip()
            if raw.startswith('TG '):
                raw = raw[3:]
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if entry.get('message_type') == 'window' and 'time_s' in entry:
                values.append(entry)
    return values


def chart(x, series, title, path, thresholds=None, events=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    keys = list(series)
    fig, axes = plt.subplots(len(keys), 1, figsize=(12, max(3, 2.2 * len(keys))), sharex=True)
    if len(keys) == 1:
        axes = [axes]
    for ax, key in zip(axes, keys):
        y = series[key]
        ax.plot(x, y, label=key, linewidth=1.3)
        if thresholds and key in thresholds:
            ax.axhline(thresholds[key], color='tab:red', linestyle='--', label='Threshold')
        if events:
            for event in events:
                ax.axvline(event, alpha=0.4, linewidth=1, color='tab:orange')
        ax.set_ylabel(key)
        ax.grid(alpha=.25)
        ax.legend(loc='upper right')
    axes[-1].set_xlabel('Time (s)')
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description='Plot LoPy recordings')
    p.add_argument('file', type=Path, help='JSONL from capture_serial or copied TG lines')
    p.add_argument('--out', type=Path, default=Path('captures/plots'))
    args = p.parse_args()
    rows = read_records(args.file)
    if not rows:
        raise SystemExit('No TG window records in input')
    args.out.mkdir(parents=True, exist_ok=True)
    time_s = [r['time_s'] for r in rows]
    alerts = [r['time_s'] for r in rows if r.get('alarm')]
    th = {}
    with args.file.open(encoding='utf-8') as src:
        for line in src:
            try:
                obj = json.loads(line.strip()[3:] if line.startswith('TG ') else line)
            except ValueError:
                continue
            if obj.get('message_type') == 'status' and obj.get('thresholds'):
                th = obj['thresholds']
    groups = {
        'audio': ('audio_rms', 'audio_low_ratio', 'audio_transient',
                  'engine_detected', 'audio_impact'),
        'vibration': ('vibration_rms', 'vibration_peak', 'accel_dynamic_rms',
                      'accel_peak', 'motion_detected'),
        'fusion': ('engine_confirmed', 'motion_detected',
                   'recent_motion_events', 'alarm', 'valid'),
    }
    for mode, metrics in groups.items():
        existing = [k for k in metrics if any(r.get(k) is not None for r in rows)]
        if not existing:
            continue
        series = {key: [float(r.get(key) or 0) for r in rows] for key in existing}
        target = args.out / (mode + '.png')
        chart(time_s, series, mode.capitalize() + ' - LoPy live data', target,
              th, alerts if mode == 'fusion' else None)
        print('Saved', target)
    print('Alerts:', len(alerts), 'Windows:', len(rows))


if __name__ == '__main__':
    main()
