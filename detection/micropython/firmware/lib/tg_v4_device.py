"""Experimental Pycom LoPy v4 engine-presence monitor.

No trained YAMNet on the device. Sensor features use the shared v3 pipeline;
inference uses tiny exported trees. One-shot alert is physically DISABLED unless
explicitly enabled AND a validated local clock indicates nonworking hours.
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
    payload=dict(kwargs)
    payload['message_type']=kind
    print('TG '+json.dumps(payload))


def off_hours():
    # The Pycom RTC is not automatically local time. Do not guess the
    # timezone or trust an unsynchronized clock.
    if not config.CLOCK_IS_LOCAL_AND_SYNCED:
        return None
    tm=time.localtime()
    if tm[0] < 2025:
        return None
    day=tm[6] # Monday=0 ... Sunday=6
    hour=tm[3]
    if day in config.WEEKEND_DAYS:
        return True
    return not (config.WORK_START_HOUR <= hour < config.WORK_END_HOUR)


def run():
    if config.AUDIO_RATE_HZ not in (1000,4000):
        raise ValueError('Unsupported audio rate')
    if config.MODE != 'audio' or not config.AUDIO_ENABLED:
        raise ValueError('v4 requires MODE=audio and microphone enabled')
    if config.STARTUP_ACTION not in ('diagnose','monitor'):
        raise ValueError('v4 supports diagnose or monitor')
    if config.AUDIO_RATE_HZ == 4000:
        from tg_model_4k import TREES, RATE
        import tg_model_4k as model
    else:
        from tg_model_1k import TREES, RATE
        import tg_model_1k as model
    if model.RATE != config.AUDIO_RATE_HZ:
        raise ValueError('Model sample rate mismatch')
    from tg_ml import FEATURES
    if not TREES or len(FEATURES)!=15:
        raise ValueError('Invalid model payload')
    hub=SensorHub(config)
    sampler=Sampler(hub,config)
    detector=Presence(model, config.ML_SCORE_THRESHOLD,
                      config.PERSISTENCE_SECONDS,config.PERSISTENCE_FRACTION,
                      off_hours=None, cooldown_s=config.COOLDOWN_S,
                      reset_after_s=config.RESET_AFTER_S)
    emit('status',state='READY',model='v4_random_forest',rate=config.AUDIO_RATE_HZ,
         action=config.STARTUP_ACTION,
         physical_alarm_enabled=bool(config.ENABLE_PHYSICAL_ALARM),
         note='Experimental audio model, not validated on deployment site')
    previous=None
    while True:
        ch=sampler.read_second()
        if previous is not None:
            row=build_window(previous,ch,config.MAX_LATE_SAMPLES_RATIO,
                             config.AUDIO_RATE_HZ)
            decision=detector.step(row,off_hours=off_hours())
            if config.PRINT_EVERY_WINDOW or decision['alarm']:
                emit('window',time_s=decision['time_s'],state=decision['state'],
                     ml_engine_score=decision['ml_engine_score'],
                     votes=decision['engine_vote_count'],
                     required=decision['engine_required_votes'],
                     persistent=decision['engine_confirmed'],
                     off_hours=decision['off_hours'],
                     alert_candidate=decision['alarm'],
                     valid=decision['valid'],
                     late_samples=decision.get('late_samples',0),
                     processing_gap_us=decision.get('processing_gap_us',0))
            if decision['alarm']:
                emit('alert_candidate',event='PERSISTENT_ENGINE',
                     time_s=decision['time_s'],event_id=decision['alarm_event_id'],
                     physical_alarm_sent=bool(config.ENABLE_PHYSICAL_ALARM
                         and config.STARTUP_ACTION=='monitor'),
                     note='Presence duration only; distance/stop not proven')
                if config.ENABLE_PHYSICAL_ALARM and config.STARTUP_ACTION=='monitor':
                    hub.pulse_alarm()
        previous=ch


def main():
    try:
        run()
    except KeyboardInterrupt:
        emit('status',state='STOPPED')
    except Exception as exc:
        emit('status',state='ERROR_NO_MONITORING',reason=str(exc))
        raise
