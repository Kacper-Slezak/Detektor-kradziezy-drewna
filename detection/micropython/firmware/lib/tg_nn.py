"""TinyML v4.2: portable quantized student network (no TensorFlow on device).

Input: legacy 15 DSP features plus 48 log spectral-band measurements,
taken from two adjacent one-second chunks using the existing FFT pipeline.
The student learns hidden nonlinear combinations during training with YAMNet.
"""
try:
    import ubinascii as binascii
except ImportError:
    import binascii
import math


def feature_vector(row):
    try:
        from tg_ml import feature_vector as old_vector
    except ImportError:
        from algorithm.core.tg_ml import feature_vector as old_vector
    bands = row.get('tiny_spectral_bands')
    if bands is None or len(bands) != 48:
        raise ValueError('Missing v4.2 spectral features (requires 4kHz DSP)')
    return old_vector(row) + [float(v) for v in bands]


def _layers(model):
    cached = getattr(model, '_decoded_layers', None)
    if cached is not None:
        return cached
    unpacked = []
    for packed in model.WEIGHT_B64:
        unpacked.append(binascii.a2b_base64(packed))
    model._decoded_layers = unpacked
    return unpacked


def predict_score(row, model):
    if model.MODEL_TYPE != 'tiny_mlp_v42' or model.RATE != 4000:
        raise ValueError('Unsupported student model')
    x = feature_vector(row)
    if len(x) != len(model.MEAN) or len(x) != model.DIMS[0]:
        raise ValueError('Input shape does not match model')
    activations = [max(-6.0, min(6.0, (x[i] - model.MEAN[i]) * model.INV_STD[i]))
                   for i in range(len(x))]
    raw_weights = _layers(model)
    for layer_index in range(len(raw_weights)):
        raw = raw_weights[layer_index]
        n_input = model.DIMS[layer_index]
        n_output = model.DIMS[layer_index + 1]
        if len(raw) != n_input * n_output:
            raise ValueError('Corrupt model weight dimensions')
        scale = model.SCALES[layer_index]
        biases = model.BIASES[layer_index]
        output = [0.0] * n_output
        # Row-major weight layout (n_input, n_output).
        for out_i in range(n_output):
            result = biases[out_i]
            pos = out_i
            for in_i in range(n_input):
                q = raw[pos]
                if q > 127:
                    q -= 256
                result += activations[in_i] * (q * scale)
                pos += n_output
            if layer_index + 1 < len(raw_weights):
                output[out_i] = result if result > 0.0 else 0.0
            else:
                # Stable sigmoid with bounded input.
                result = max(-40.0, min(40.0, result))
                output[out_i] = 1.0 / (1.0 + math.exp(-result))
        activations = output
    return activations[0]
