"""Check local waveform reuse and score an in-memory residual for diagnosis."""

import numpy as np

from algorithm.app.burst_evaluate import baseline_predict
from algorithm.app.burst_prepare import all_windows, decode
from algorithm.app.recall_evaluate import predict_export
from firmware.lib.tg_burst import RATE


def match_offset(reference, excerpt, excerpt_start):
    """Find a whole-excerpt alignment in a reference using normalized correlation."""
    if len(excerpt) > len(reference) or not len(excerpt):
        raise ValueError('Expected a nonempty excerpt within the reference duration')
    target = excerpt - excerpt.mean()
    n = len(target)
    padded = 1 << (len(reference) + n - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(reference, padded) * np.fft.rfft(target[::-1], padded), padded)
    sums = np.r_[0., np.cumsum(reference)]
    energy = np.r_[0., np.cumsum(reference ** 2)]
    energy = energy[n:] - energy[:-n] - (sums[n:] - sums[:-n]) ** 2 / n
    corr = corr[n - 1:len(reference)] / np.sqrt(np.maximum(energy, 1) * max(target @ target, 1))
    index = int(np.argmax(np.abs(corr)))
    return index - excerpt_start, float(corr[index])


def align(reference, offset, length):
    # Offset is the index in the reference at scene sample zero.
    aligned = np.zeros(length)
    first = max(0, -offset)
    end = min(length, len(reference) - offset)
    if end > first:
        aligned[first:end] = reference[first + offset:end + offset]
    return aligned


def band_snr(engine, background, rate):
    """Compare known source components by band, using 250 ms Hann frames."""
    size = rate // 4
    frames = len(engine) // size
    taper = np.hanning(size)
    hz = np.fft.rfftfreq(size, 1 / rate)
    spectra = []
    for pcm in (engine, background):
        blocks = pcm[:frames * size].reshape(frames, size)
        spectra.append(np.sum(np.abs(np.fft.rfft(blocks * taper, axis=1)) ** 2, axis=0))
    positive, noise = spectra
    edges = (35, 130, 350, 800, 1300, 1900, 2700, 3800)
    result = {}
    for lo, hi in zip(edges, edges[1:]):
        mask = (lo <= hz) & (hz < hi)
        result[f'{lo}_{hi}'] = float(10 * np.log10((positive[mask].sum() + 1e-6) /
                                                 (noise[mask].sum() + 1e-6)))
    return result


def component_audit(directory, baseline, models):
    def read(name, rate=RATE):
        return decode(directory / name, rate).astype(np.float64)

    scene = read('rain-wind-truck.wav')
    wind = read('wind-lake.wav')
    wind_start = 10 * RATE
    offset, corr = match_offset(wind, scene[wind_start:30 * RATE], wind_start)
    aligned_wind = align(wind, offset, len(scene))
    first_five = slice(0, 5 * RATE)
    x = aligned_wind[first_five]
    y = scene[first_five]
    centered = x - x.mean()
    gain = (centered @ (y - y.mean())) / (centered @ centered)
    residual = scene - gain * aligned_wind
    engine = read('catterpillar.wav')
    rain = read('rain-in-forest.wav')
    match_start = 19 * RATE
    excerpt = residual[match_start:35 * RATE]
    engine_offset, engine_corr = match_offset(engine, excerpt, match_start)
    rain_offset, rain_corr = match_offset(rain, excerpt, match_start)
    terms = np.column_stack((aligned_wind, align(engine, engine_offset, len(scene)),
                             align(rain, rain_offset, len(scene))))
    fit = slice(match_start, 35 * RATE)
    coefficients = np.linalg.lstsq(terms[fit], scene[fit], rcond=None)[0]
    error = scene - terms @ coefficients
    native_rate = 8000
    length = len(read('rain-wind-truck.wav', native_rate))
    expanded = [align(read(name, native_rate), shift * 2, length) * gain
                for name, shift, gain in zip(('wind-lake.wav', 'catterpillar.wav', 'rain-in-forest.wav'),
                                             (offset, engine_offset, rain_offset), coefficients)]
    fit_wide = slice(19 * native_rate, 35 * native_rate)

    def rms_ratio(part, whole):
        return float(20 * np.log10(part.std() / whole.std()))

    # Score only the fixed wind-subtraction counterfactual. No audio is exported.
    pcm = np.rint(np.clip(residual, -32768, 32767)).astype('<i2')
    scores = baseline_predict(pcm, baseline)
    model_scores = {'original': dict(max=float(max(scores)), hits=int((scores >= baseline.THRESHOLD).sum()))}
    for name, model in models.items():
        scores = predict_export(model, all_windows(pcm, model.BURST_SAMPLES))
        model_scores[name] = dict(max=float(max(scores)), hits=int((scores >= model.THRESHOLD).sum()))
    return dict(wind_offset_samples=offset, wind_excerpt_corr=corr, wind_gain_first_5s=float(gain),
                engine_offset_samples=engine_offset, wind_residual_engine_corr=engine_corr,
                rain_offset_samples=rain_offset, wind_residual_rain_corr=rain_corr,
                fit_gains=dict(zip(('wind', 'engine', 'rain'), coefficients.tolist())),
                matched_engine_to_wind_db_on_fit=rms_ratio(terms[fit, 1] * coefficients[1],
                                                          terms[fit, 0] * coefficients[0]),
                engine_to_wind_and_rain_by_band_db=band_snr(
                    expanded[1][fit_wide], expanded[0][fit_wide] + expanded[2][fit_wide], native_rate),
                wind_residual_to_wind_db=rms_ratio(residual, aligned_wind),
                reconstruction_error_db_in_fit=rms_ratio(error[fit], scene[fit]),
                reconstruction_error_db_outside_fit=rms_ratio(np.r_[error[:match_start], error[35 * RATE:]],
                                                              np.r_[scene[:match_start], scene[35 * RATE:]]),
                offline_wind_residual_scores=model_scores)
