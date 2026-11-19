"""Run in Pycom REPL: import lopy_v44_memory_probe; lopy_v44_memory_probe.main()
Heap and single-window compute timing ONLY. No ADC, no physical alarm.
"""
import gc,time

def snapshot(label):
    gc.collect()
    print(label,'heap_free_bytes',gc.mem_free())

def main():
    snapshot('start')
    import tg_model_v44 as model
    snapshot('model_import')
    from tg_cnn import _decode,score_bands
    _decode(model)
    snapshot('weights_decoded')
    from tg_temporal import MelFFT,TemporalChunk,make_row
    fft=MelFFT()
    snapshot('fft_allocated')
    previous=TemporalChunk(0.0)
    current=TemporalChunk(1.0)
    for chunk in (previous,current):
        chunk.total_samples=4000
        for i in range(2000):
            chunk.samples.append((i*43)%2000-1000)
    snapshot('two_chunks_allocated')
    tick=time.ticks_ms()
    row=make_row(previous,current,fft)
    score=score_bands(row['temporal_bands'],model)
    millis=time.ticks_diff(time.ticks_ms(),tick)
    snapshot('after_extract_and_infer')
    print('single_window_extract_and_infer_ms',millis)
    print('score_not_a_real_detection',score)
    print('NOTE: This is not a real-time ADC test. 4kHz continuous sampling still unverified.')
