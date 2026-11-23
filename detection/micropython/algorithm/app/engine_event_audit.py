"""Clip eligibility and fixed-rule comparisons for recorded engine scores."""

from collections import Counter, defaultdict
from math import isfinite

from algorithm.app.burst_evaluate import episodes

COMMON_RULES = {'one_hit': (1, 1), 'two_consecutive': (2, 2), 'one_of_two': (2, 1)}


def score_runs(rows, scores):
    """Split each source at missing or invalid one-second hops."""
    if len(rows) != len(scores):
        raise ValueError('Scores and windows must align')
    sources = defaultdict(list)
    for row, score in zip(rows, scores):
        sources[row['source']].append((float(row['time_s']), int(row['label']), score))
    for source, items in sources.items():
        ordered = sorted(items, key=lambda item: item[0])
        label = ordered[0][1]
        previous, runs = None, []
        for second, current_label, score in ordered:
            if label != current_label or (previous is not None and second <= previous):
                raise ValueError('Inconsistent label or duplicate time in ' + source)
            if score is None or not isfinite(score):
                previous = second
                continue
            if not runs or second != runs[-1][0] + len(runs[-1][1]):
                runs.append((second, []))
            runs[-1][1].append(score)
            previous = second
        yield label, runs


def clip_comparison(rows, scores, threshold, native):
    """Use the same frozen classifier thresholds with native and common vote rules."""
    runs = list(score_runs(rows, scores))
    result = {}
    for name, (span, required) in {'native': native, **COMMON_RULES}.items():
        counts = {'engine': Counter(), 'negative': Counter()}
        for label, segments in runs:
            group = counts['engine' if label else 'negative']
            eligible = any(len(segment) >= span for _, segment in segments)
            group['eligible' if eligible else 'ineligible'] += 1
            if eligible and any(episodes(segment, threshold, span, required) for _, segment in segments):
                group['confirmed'] += 1
        result[name] = {kind: {key: bucket[key] for key in ('eligible', 'ineligible', 'confirmed')}
                        for kind, bucket in counts.items()}
    return result


def replay_comparison(scores, threshold, native, interval=None):
    """Report episode starts at window end; score timed labels on fully contained windows."""
    if interval is not None:
        start, end = interval
        contained = [(i, score) for i, score in enumerate(scores) if start <= i and i + 2 <= end]
    result = {}
    for name, (span, required) in {'native': native, **COMMON_RULES}.items():
        starts = episodes(scores, threshold, span, required)
        stat = dict(starts_s=starts, eligible=len(scores) >= span)
        if interval is not None:
            event_scores = [score for _, score in contained]
            inside = episodes(event_scores, threshold, span, required)
            stat['event_eligible_from_onset'] = len(event_scores) >= span
            stat['event_only_delay_s'] = contained[0][0] + inside[0] - start if inside else None
            stat['pre_onset_episodes'] = sum(second <= start for second in starts)
        result[name] = stat
    return result
