"""On-device LoPy memory probe. Copy to /flash/lopy_memory_probe.py.

Run manually in REPL: import lopy_memory_probe; lopy_memory_probe.main()
Does not read sensors, transmit data, or enable physical alarms.
The output measures MicroPython heap, not complete device RAM usage.
"""
import gc


def free():
    gc.collect()
    return gc.mem_free()


def main():
    print('TG_MEMORY_PROBE_BEGIN')
    before=free()
    print('free_before_import_bytes',before)
    import tg_model_v42 as model
    after_model=free()
    print('free_after_model_import_bytes',after_model)
    from tg_nn import _layers
    _layers(model)
    after_decode=free()
    print('free_after_weight_decode_bytes',after_decode)
    print('model_import_heap_delta_bytes',before-after_model)
    print('weight_decode_heap_delta_bytes',after_model-after_decode)
    print('total_heap_delta_bytes',before-after_decode)
    print('heap_free_for_audio_and_features_bytes',after_decode)
    print('model_dims',model.DIMS)
    print('TG_MEMORY_PROBE_END')
