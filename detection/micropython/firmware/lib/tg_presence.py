"""Bounded state machine for engine presence, persistence and one-shot alarms.

A 15 s ratio rule is NOT a distance sensor. Without site calibration the
state is PERSISTENT_ENGINE (duration observed), NOT STOPPED_NEARBY.
"""
try:
    from tg_ml import predict_probability  # Pycom firmware /flash/lib
except ImportError:
    from algorithm.core.tg_ml import predict_probability  # desktop

class Presence:
    def __init__(self, model, threshold=0.50, span=15, fraction=0.60,
                 off_hours=False, cooldown_s=60, reset_after_s=8):
        if not (0 < threshold < 1 and 0 < fraction <= 1 and span >= 2):
            raise ValueError('Invalid detector settings')
        self.model = model
        self.threshold = threshold
        self.span = int(span)
        self.required = int(self.span * fraction + 0.999999)
        self.off_hours = off_hours
        self.cooldown_s = cooldown_s
        self.reset_after_s = reset_after_s
        self.history = []
        self.prev_time = None
        self.last_alarm_time = -1e9
        self.latched = False
        self.absent_for = 0
        self.event_id = 0

    def step(self, row, off_hours="use_default"):
        t = float(row['time_s'])
        hours = self.off_hours if off_hours == "use_default" else off_hours
        if self.prev_time is not None and (t <= self.prev_time):
            raise ValueError('non-monotonic timestamps')
        gap = self.prev_time is not None and t - self.prev_time > 1.5
        self.prev_time = t
        # None means time is unknown: alarms must fail closed.
        if gap or not row.get('valid', True) or row.get('audio_rms') is None:
            self.history = []
            self.absent_for = 0
            return dict(row, ml_engine_score=None, engine_detected=0,
                        engine_vote_count=0, engine_required_votes=self.required,
                        engine_confirmed=0, state='DATA_INVALID', alarm=0,
                        alarm_event_id=0, off_hours=hours)
        if getattr(self.model, 'MODEL_TYPE', None) == 'tiny_cnn_wide_v46':
            try:
                from tg_cnn_v46 import score_features
            except ImportError:
                from algorithm.core.tg_cnn_v46 import score_features
            if row.get('wide_patch') is None or row.get('energy_envelope') is None:
                raise ValueError('Missing 8x24 patch or energy envelope')
            score = float(score_features(row['wide_patch'],row['energy_envelope'],self.model))
        elif getattr(self.model, 'MODEL_TYPE', None) in ('tiny_cnn_mel_v44', 'tiny_cnn_mel_v45'):
            if self.model.MODEL_TYPE == 'tiny_cnn_mel_v45':
                try:
                    from tg_cnn_v45 import score_bands
                except ImportError:
                    from algorithm.core.tg_cnn_v45 import score_bands
            else:
                try:
                    from tg_cnn import score_bands
                except ImportError:
                    from algorithm.core.tg_cnn import score_bands
            if row.get('temporal_bands') is None:
                raise ValueError('Missing temporal_bands for CNN')
            score = float(score_bands(row['temporal_bands'], self.model))
        else:
            score = float(predict_probability(row, self.model))
        hit = int(score >= self.threshold)
        self.history.append(hit)
        if len(self.history) > self.span:
            self.history.pop(0)
        votes = sum(self.history)
        persistent = len(self.history) == self.span and votes >= self.required
        if hit:
            self.absent_for = 0
        else:
            self.absent_for += 1
        if self.absent_for >= self.reset_after_s:
            self.latched = False
        alarm = int(bool(persistent and hours is True and not self.latched and
                         t - self.last_alarm_time >= self.cooldown_s))
        if alarm:
            self.event_id += 1
            self.last_alarm_time = t
            self.latched = True
        if persistent:
            state = 'PERSISTENT_ENGINE'
        elif hit:
            state = 'PASS_BY'   # provisional sound episode, not a confirmed passing car
        elif votes:
            state = 'ENGINE_RECENT'
        else:
            state = 'BACKGROUND'
        return dict(row, ml_engine_score=round(score, 5), engine_detected=hit,
                    engine_vote_count=votes, engine_required_votes=self.required,
                    engine_confirmed=int(persistent), state=state,
                    alarm=alarm, alarm_event_id=self.event_id if alarm else 0,
                    off_hours=hours)
