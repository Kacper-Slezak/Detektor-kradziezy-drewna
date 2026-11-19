"""Portable tiny learned classifier over on-device DSP measurements.

Training happens on desktop. No numpy/scikit-learn at runtime. The model
contains trees learned from FILE-DISJOINT audio, not YAMNet embeddings.
"""
FEATURES = (
    'audio_low_ratio', 'audio_tonality', 'audio_flatness',
    'audio_harmonic_score', 'audio_ridge_score', 'audio_low_ridge_score',
    'audio_high_band_ratio', 'audio_engine_score',
    'audio_wide_ratio', 'audio_wide_flatness', 'audio_wide_concentration',
    'audio_wide_max_share', 'audio_wide_peak_count', 'audio_wide_score',
    'audio_transient',
)


def feature_vector(row):
    values = []
    for name in FEATURES:
        value = row.get(name)
        if value is None:
            value = -1.0
        else:
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = -1.0
            if value != value or abs(value) > 1.0e20:
                value = -1.0
        # Training data and firmware both explicitly clip numeric extremes.
        if value > 100.0:
            value = 100.0
        if value < -1.0:
            value = -1.0
        values.append(value)
    return values


def predict_probability(row, model):
    """Mean leaf probability of a compact, shallow random forest.

    Each tree stores tuples (feature_index, threshold, left, right, value).
    At leaves feature_index == -1 and value is the probability of ENGINE.
    """
    if getattr(model, 'MODEL_TYPE', None) == 'tiny_mlp_v42':
        try:
            from tg_nn import predict_score
        except ImportError:
            from algorithm.core.tg_nn import predict_score
        return predict_score(row, model)
    x = feature_vector(row)
    trees = model.TREES
    if not trees:
        return 0.0
    total = 0.0
    for tree in trees:
        index = 0
        while True:
            f, boundary, left, right, value = tree[index]
            if f == -1:
                total += value
                break
            index = left if x[f] <= boundary else right
    return total / len(trees)
