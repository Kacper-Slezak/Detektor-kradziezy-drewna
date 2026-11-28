"""Live original Pycom LoPy student monitor. Safe fail-closed prototype.

Requires tg_model_v42.py copied from algorithm/results/v4_2 after training.
ADC at 4 kHz and Python FFT processing are NOT validated on original LoPy.
"""
try:
    import ujson as json
except ImportError:
    import json
import time
import config
from tg_sampling import Sampler
from tg_hardware import SensorHub
from tg_features import build_window
from tg_presence import Presence


def emit(kind, **kwargs):
    data = dict(kwargs)
    data['message_type'] = kind
    print('TG ' + json.dumps(data))


def off_hours():
    if not config.CLOCK_IS_LOCAL_AND_SYNCED:
        return None
    tm = time.localtime()
    if tm[0] < 2025:
        return None
    if tm[6] in config.WEEKEND_DAYS:
        return True
    return not (config.WORK_START_HOUR <= tm[3] < config.WORK_END_HOUR)


def run():
    if config.AUDIO_RATE_HZ != 4000 or config.MODE != 'audio':
        raise ValueError('v4.2 student needs MODE=audio and AUDIO_RATE_HZ=4000')
    if config.ACCEL_ENABLED or config.VIBRATION_INPUT != 'off':
        raise ValueError('v4.2 uses audio only; disable other sensors')
    try:
        import tg_model_v42 as model
    except ImportError:
        raise RuntimeError('Missing trained tg_model_v42.py: NOT MONITORING')
    if (getattr(model,'MODEL_TYPE',None) != 'tiny_mlp_v42' or
            getattr(model,'RATE',None) != 4000 or
            len(model.MEAN) != model.DIMS[0]):
        raise RuntimeError('Invalid trained student model: NOT MONITORING')
    hub = SensorHub(config)
    sampler = Sampler(hub, config)
    detector = Presence(model, threshold=model.THRESHOLD,
                        span=config.PERSISTENCE_SECONDS,
                        fraction=config.PERSISTENCE_FRACTION,
                        off_hours=None, cooldown_s=config.COOLDOWN_S,
                        reset_after_s=config.RESET_AFTER_S)
    emit('status',state='READY', model='v4_2_yamnet_distilled_student',
         rate=config.AUDIO_RATE_HZ,
         physical_alarm_enabled=bool(config.ENABLE_PHYSICAL_ALARM),
         note='Unverified LoPy ADC+FFT timing. Presence does not prove distance.')
    previous = None
    while True:
        current = sampler.read_second()
        if previous is not None:
            row = build_window(previous,current,config.MAX_LATE_SAMPLES_RATIO,
                               config.AUDIO_RATE_HZ)
            decision = detector.step(row, off_hours=off_hours())
            if config.PRINT_EVERY_WINDOW or decision['alarm']:
                emit('window',time_s=decision['time_s'],state=decision['state'],
                     score=decision['ml_engine_score'],
                     votes=decision['engine_vote_count'],
                     required=decision['engine_required_votes'],
                     alert_candidate=decision['alarm'],
                     valid=decision['valid'],
                     late_samples=decision.get('late_samples',0),
                     gap_us=decision.get('processing_gap_us',0))
            if decision['alarm']:
                enabled = (config.STARTUP_ACTION == 'monitor'
                           and config.ENABLE_PHYSICAL_ALARM)
                emit('alert_candidate',time_s=decision['time_s'],
                     event_id=decision['alarm_event_id'],
                     physical_alarm_sent=bool(enabled))
                if enabled:
                    hub.pulse_alarm()
        previous = current


def main():
    try:
        run()
    except KeyboardInterrupt:
        emit('status',state='STOPPED')
    except Exception as exc:
        emit('status',state='ERROR_NO_MONITORING',reason=str(exc))
        raise
