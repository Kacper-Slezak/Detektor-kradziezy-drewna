"""Main firmware application. Uses live sensors only, no synthetic samples."""
try:
    import ujson as json
except ImportError:
    import json

import time
import config
from tg_sampling import Sampler
from tg_hardware import SensorHub
from tg_features import build_window
from tg_calibration import calibrate, save, load
from tg_fusion import Detector


def settings():
    c = config
    return {'hop_s': c.HOP_S, 'window_s': c.WINDOW_S,
            'low_ratio_min': c.LOW_RATIO_MIN,
            'engine_confirm_windows': c.ENGINE_CONFIRM_WINDOWS,
            'engine_memory_s': c.ENGINE_MEMORY_S,
            'impact_memory_s': c.IMPACT_MEMORY_S,
            'impacts_for_alarm': c.IMPACTS_FOR_ALARM,
            'cooldown_s': c.COOLDOWN_S}


def floors():
    c = config
    return {'audio_rms': c.MIN_AUDIO_RMS,
            'audio_transient': c.MIN_AUDIO_TRANSIENT,
            'vibration_rms': c.MIN_VIBRATION_RMS,
            'vibration_peak': c.MIN_VIBRATION_PEAK,
            'accel_dynamic_rms': c.MIN_ACCEL_DYNAMIC_RMS,
            'accel_peak': c.MIN_ACCEL_PEAK}


def emit(kind, payload):
    data = dict(payload)
    data['message_type'] = kind
    print('TG ' + json.dumps(data))


def validate_config():
    c = config
    if c.MODE not in ('audio', 'vibration', 'fusion'):
        raise ValueError('MODE must be audio, vibration or fusion')
    if c.MODE in ('audio', 'fusion') and not c.AUDIO_ENABLED:
        raise ValueError('MODE needs audio enabled')
    if c.MODE in ('vibration', 'fusion') and not (
            c.VIBRATION_INPUT != 'off' or c.ACCEL_ENABLED):
        raise ValueError('MODE needs vibration sensor and/or accelerometer')


def check_thresholds(th):
    c = config
    required = []
    if c.MODE in ('audio', 'fusion'):
        required += ['audio_rms', 'audio_transient']
    if c.MODE in ('vibration', 'fusion'):
        if c.VIBRATION_INPUT != 'off':
            required += ['vibration_rms', 'vibration_peak']
        if c.ACCEL_ENABLED:
            required += ['accel_dynamic_rms', 'accel_peak']
    missing = [x for x in required if x not in th]
    if missing:
        raise ValueError('Calibration missing metrics: ' + ', '.join(missing))


def iter_windows(sampler):
    previous = None
    while True:
        current = sampler.read_second()
        if previous is not None:
            yield build_window(previous, current,
                               config.MAX_LATE_SAMPLES_RATIO,
                               config.AUDIO_RATE_HZ)
        previous = current


def perform_calibration(windows):
    rows = []
    emit('status', {'state': 'CALIBRATING', 'required_windows': config.CALIBRATION_WINDOWS,
                    'note': 'Keep all sensors in QUIET conditions; not theft detection.'})
    while len(rows) < config.CALIBRATION_WINDOWS:
        row = next(windows)
        if row['valid']:
            rows.append(row)
        else:
            emit('status', {'state': 'CALIBRATION_REJECTED', 'late_samples': row['late_samples']})
    th = calibrate(rows, floors())
    check_thresholds(th)
    save(config.CALIBRATION_FILE, config.HARDWARE_PROFILE, th)
    emit('calibration', {'state': 'SAVED', 'profile': config.HARDWARE_PROFILE,
                         'thresholds': th, 'path': config.CALIBRATION_FILE})
    return th


def run():
    validate_config()
    emit('status', {'state': 'STARTING', 'mode': config.MODE,
                    'sensor_profile': config.HARDWARE_PROFILE})
    hub = SensorHub(config)
    sampler = Sampler(hub, config)
    windows = iter_windows(sampler)

    if config.STARTUP_ACTION == 'calibrate':
        th = perform_calibration(windows)
    elif config.STARTUP_ACTION in ('monitor', 'diagnose'):
        if config.STARTUP_ACTION == 'diagnose':
            th = floors()           # diagnostics only, NEVER a valid calibration
        else:
            # Missing or incompatible calibration terminates safely, no alerts.
            th = load(config.CALIBRATION_FILE, config.HARDWARE_PROFILE)
            check_thresholds(th)
    else:
        raise ValueError('STARTUP_ACTION must be monitor, calibrate or diagnose')

    detector = Detector(th, settings(), config.MODE)
    emit('status', {'state': 'READY', 'mode': config.MODE,
                    'action': config.STARTUP_ACTION, 'thresholds': th,
                    'note': 'Suspicious pattern only; not proof of theft.'})
    for row in windows:
        classified = detector.step(row)
        if config.STARTUP_ACTION == 'diagnose':
            classified['alarm'] = 0
            classified['state'] = 'DIAGNOSTIC_' + classified['state']
        if config.PRINT_EVERY_WINDOW or classified['alarm']:
            emit('window', classified)
        if classified['alarm']:
            emit('alert', {'time_s': classified['time_s'], 'state': classified['state']})
            hub.pulse_alarm()


def main():
    try:
        run()
    except KeyboardInterrupt:
        emit('status', {'state': 'STOPPED'})
    except Exception as error:
        # Fail closed, never fake a sensor value or create a theft alert.
        emit('status', {'state': 'ERROR_NO_MONITORING',
                        'reason': str(error)})
        raise
