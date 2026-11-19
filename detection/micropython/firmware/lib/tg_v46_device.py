"""v4.6 diagnostic-only wideband monitor for ORIGINAL Pycom LoPy.

No physical alarm output, no network. Software-timed ADC is NOT suitable
for validated real-time use without measuring sampling gaps and FFT timing.
"""
try:
    import ujson as json
except ImportError:
    import json
import gc,time
import config
from tg_sampling_v46 import Sampler
from tg_hardware import SensorHub
from tg_temporal_v46 import MelFFT,make_row
from tg_presence_v46 import Presence


def emit(**fields):
    print('TG '+json.dumps(fields))


def run():
    if config.AUDIO_RATE_HZ != 4000 or config.MODE != 'audio' or not config.AUDIO_ENABLED:
        raise ValueError('v4.6 requires 4000Hz microphone, audio-only mode')
    if config.ACCEL_ENABLED or config.VIBRATION_INPUT!='off':
        raise ValueError('v4.6 diagnostic requires other sensors disabled')
    import tg_model_v46 as model
    if model.MODEL_TYPE!='tiny_cnn_wide_v46' or model.RATE != 4000:
        raise ValueError('Expected trained wideband v4.6 model')
    hub=SensorHub(config)
    sampler=Sampler(hub,config)
    fft=MelFFT()
    detector=Presence(model,threshold=model.THRESHOLD,
        span=config.PERSISTENCE_SECONDS,fraction=config.PERSISTENCE_FRACTION,
        off_hours=None,cooldown_s=config.COOLDOWN_S,
        reset_after_s=config.RESET_AFTER_S)
    gc.collect()
    emit(type='status',state='READY_DIAGNOSTIC_ONLY',model='v4_6_wideband',
         free_heap=gc.mem_free(),physical_alarm_enabled=False,
         note='Software ADC/FFT latency unverified on original LoPy')
    prev=None
    while True:
        current=sampler.read_second()
        if prev is not None:
            t0=time.ticks_ms()
            row=make_row(prev,current,fft,config.MAX_LATE_SAMPLES_RATIO,
                         config.MAX_PROCESSING_GAP_US)
            decision=detector.step(row,off_hours=None)
            processing_ms=time.ticks_diff(time.ticks_ms(),t0)
            gc.collect()
            emit(type='window',time_s=decision['time_s'],
                score=decision['ml_engine_score'],detected=decision['engine_detected'],
                confirmed=decision['engine_confirmed'],votes=decision['engine_vote_count'],
                valid=decision['valid'],processing_ms=processing_ms,
                late_samples=decision.get('late_samples',0),
                processing_gap_us=decision.get('processing_gap_us',0),
                heap_free=gc.mem_free())
        prev=current


def main():
    try:run()
    except KeyboardInterrupt:emit(type='status',state='STOPPED')
    except Exception as exc:
        emit(type='status',state='ERROR_NO_MONITORING',reason=str(exc))
        raise
