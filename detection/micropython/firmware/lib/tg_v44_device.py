"""Experimental v4.4 LoPy live monitor; physical alarm ALWAYS suppressed.

Unverified 4kHz software ADC, FFT feature latency and heap. If sampling
misses timing constraints, windows are DATA_INVALID rather than confirmed.
Uses overlapping 1s int16 chunks; no YAMNet, TensorFlow or numpy on device.
"""
try:
    import ujson as json
except ImportError:
    import json
import gc,time
import config
from tg_sampling import Sampler
from tg_hardware import SensorHub
from tg_temporal import MelFFT,make_row
from tg_presence import Presence


def emit(**kw):
    print('TG '+json.dumps(kw))


def run():
    if config.AUDIO_RATE_HZ!=4000 or config.MODE!='audio' or not config.AUDIO_ENABLED:
        raise ValueError('v4.4 requires 4kHz analog microphone and audio mode')
    if config.ACCEL_ENABLED or config.VIBRATION_INPUT!='off':
        raise ValueError('v4.4 audio-only experiment; disable other sensors')
    import tg_model_v44 as model
    if model.MODEL_TYPE!='tiny_cnn_mel_v44' or model.RATE!=4000:
        raise ValueError('Invalid trained v4.4 model')
    hub=SensorHub(config)
    sampler=Sampler(hub,config,temporal=True)
    extractor=MelFFT()
    detector=Presence(model,threshold=model.THRESHOLD,
                      span=config.PERSISTENCE_SECONDS,
                      fraction=config.PERSISTENCE_FRACTION,
                      off_hours=None,cooldown_s=config.COOLDOWN_S,
                      reset_after_s=config.RESET_AFTER_S)
    gc.collect()
    emit(message_type='status',state='READY_DIAGNOSTICS_ONLY',
         model='v4_4_logmel_cnn',heap_free=gc.mem_free(),
         physical_alarm_enabled=False,
         note='4kHz software ADC and FFT timing not hardware verified')
    prev=None
    while True:
        current=sampler.read_second()
        if prev is not None:
            row=make_row(prev,current,extractor,
                         config.MAX_LATE_SAMPLES_RATIO,
                         config.MAX_PROCESSING_GAP_US)
            result=detector.step(row,off_hours=None)
            emit(message_type='window',time_s=result['time_s'],
                 score=result['ml_engine_score'],
                 detected=result['engine_detected'],
                 votes=result['engine_vote_count'],
                 confirmed=result['engine_confirmed'],
                 valid=result['valid'],
                 gap_us=result.get('processing_gap_us',0),
                 late_samples=result.get('late_samples',0),
                 heap_free=gc.mem_free())
            # No physical alarm, ever, in the experimental v4.4 device code.
            gc.collect()
        prev=current


def main():
    try:run()
    except KeyboardInterrupt:emit(message_type='status',state='STOPPED')
    except Exception as exc:
        emit(message_type='status',state='ERROR_NO_MONITORING',reason=str(exc))
        raise
