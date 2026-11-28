"""Original LoPy REPL: import lopy_v46_memory_probe; lopy_v46_memory_probe.main()

Heap + compute time on synthetic frames, not a 4kHz ADC speed validation.
No physical alarm will activate.
"""
import gc,time

def snapshot(label):
    gc.collect()
    print(label,'heap_free_bytes',gc.mem_free(),'heap_allocated_bytes',gc.mem_alloc())

def main():
    snapshot('start')
    import tg_model_v46 as model
    snapshot('model_imported')
    from tg_cnn_v46 import score_features
    from tg_temporal_v46 import RawChunk,MelFFT,make_row
    fft=MelFFT()
    snapshot('fft_initialized')
    previous=RawChunk(0.0); current=RawChunk(1.0)
    for ch in (previous,current):
        for i in range(4000):
            ch.add_sample(0.5+0.1*((i%31)-15)/15.0)
            ch.total_samples+=1
    snapshot('two_pcm_chunks')
    start=time.ticks_ms()
    row=make_row(previous,current,fft)
    score=score_features(row['wide_patch'],row['energy_envelope'],model)
    ms=time.ticks_diff(time.ticks_ms(),start)
    snapshot('after_inference')
    print('extract_and_infer_ms',ms,'synthetic_score',score)
    print('not verified: continuous 4kHz ADC timing, sampling gaps, flash space')
