"""Conservative stateful engine + physical impact detection.

Diagnostics are emitted each hop. An ALERT is a one-shot event in *fusion*
mode only; neither an engine nor vibration by itself proves wood theft.
Compatible with both CPython and original Pycom MicroPython.
"""


class Detector:
    def __init__(self, thresholds, settings, mode='fusion'):
        if mode not in ('audio', 'vibration', 'fusion'):
            raise ValueError('Unknown mode: ' + mode)
        self.th = thresholds
        self.s = settings
        self.mode = mode
        self.reset()

    def reset(self):
        self.engine_hits = []
        self.wide_hits = []
        self.last_engine_t = -1e9
        self.engine_session_start = None
        self.prev_motion = False
        self.impacts = []
        self.last_alarm_t = -1e9
        self.alarm_latched = False
        self.previous_t = None
        self.event_id = 0

    def _drop_evidence(self):
        # A sample gap invalidates inference, NOT the fact that we already
        # emitted an alert. Preserve one-shot protection across lost samples.
        last_alarm = self.last_alarm_t
        event_id = self.event_id
        latched = self.alarm_latched
        self.reset()
        self.last_alarm_t = last_alarm
        self.event_id = event_id
        self.alarm_latched = latched

    def _fail(self, row, t, state):
        # A gap, missing spectral evidence or any lost sensor invalidates all
        # temporary engine/motion evidence. Never emit an alarm on bad data.
        self._drop_evidence()
        self.previous_t = t
        out = dict(row)
        out.update(engine_score=0.0, engine_detected=0, engine_confirmed=0,
                   engine_recent=0, engine_reason='unavailable',
                   audio_impact=0, vibration_detected=0,
                   accelerometer_detected=0, motion_detected=0,
                   recent_motion_events=0, eligible_motion_events=0,
                   state=state, alarm=0, alarm_event_id=0)
        return out

    def step(self, row):
        s = self.s
        t = float(row['time_s'])
        if self.previous_t is not None:
            if t <= self.previous_t:
                raise ValueError('time_s must increase')
            if t - self.previous_t > 1.5 * float(s['hop_s']):
                self._drop_evidence()
        self.previous_t = t
        if not row.get('valid', True):
            return self._fail(row, t, 'DATA_INVALID')

        need_audio = self.mode in ('audio', 'fusion')
        need_motion = self.mode in ('vibration', 'fusion')
        has_audio = (row.get('audio_rms') is not None
                     and row.get('audio_engine_score') is not None)
        has_motion = (row.get('vibration_rms') is not None or
                      row.get('accel_dynamic_rms') is not None)
        if (need_audio and not has_audio) or (need_motion and not has_motion):
            return self._fail(row, t, 'SENSOR_MISSING')

        score = float(row.get('audio_engine_score') or 0.0)
        pitch = row.get('audio_engine_pitch_hz')
        # A coherent low-order spectral ridge has its own high-band and
        # narrow-line checks. Do not reject quiet diesel orders just because
        # the amplitude is slightly below the generic RMS gate.
        gate_factor = (s['engine_low_ridge_rms_gate_factor'] if row.get('audio_engine_method') == 'low_ridge'
                       else s['engine_rms_gate_factor'])
        audible = bool(has_audio and row['audio_rms'] >=
                       self.th['audio_rms'] * gate_factor)
        # Slightly lower instantaneous score is permitted only for the
        # constrained low-order track. Temporal coherence is still mandatory.
        score_min = (s['engine_low_ridge_score_min'] if row.get('audio_engine_method') == 'low_ridge'
                     else s['engine_score_min'])
        low_candidate = bool(audible and pitch is not None and score >= score_min)
        # Optional v3 path only on 4-kHz input. Requiring high-band energy
        # relative to low-frequency energy plus several separate tonal ridges
        # rejects many broadband signals that look 'bass-heavy' at 1 kHz.
        # A low-rate LoPy configuration retains the v2.1 conservative path.
        wide_score = float(row.get('audio_wide_score') or 0.0)
        wide_peaks = row.get('audio_wide_peaks_hz') or []
        wide_ratio = float(row.get('audio_wide_ratio') or 0.0)
        wide_candidate = bool(has_audio and audible and
                              wide_score >= s.get('engine_wide_score_min', 0.76) and
                              wide_ratio >= s.get('engine_wide_ratio_min', 1.2) and
                              len(wide_peaks) >= 3)
        if low_candidate:
            self.engine_hits.append((t, float(pitch)))
        if wide_candidate:
            self.wide_hits.append((t, tuple(wide_peaks)))
        while self.engine_hits and self.engine_hits[0][0] < t - s['engine_vote_s']:
            self.engine_hits.pop(0)
        while self.wide_hits and self.wide_hits[0][0] < t - s['engine_vote_s']:
            self.wide_hits.pop(0)
        tracked = []
        if low_candidate:
            for event_t, frequency in self.engine_hits:
                if abs(frequency - pitch) <= max(3.0, pitch * 0.12):
                    tracked.append(event_t)
        low_confirmed = low_candidate and len(tracked) >= s['engine_confirm_windows']
        # Wideband multi-ridge association: two non-adjacent windows must
        # have an order/tonal component near a current peak. This permits
        # changing dominant harmonics without accepting unrelated peaks.
        wide_tracked = []
        if wide_candidate:
            for hit_t, prev_peaks in self.wide_hits:
                if any(abs(p - q) <= max(10.0, 0.055 * p)
                       for p in wide_peaks for q in prev_peaks):
                    wide_tracked.append(hit_t)
        wide_confirmed = (wide_candidate and
                          len(wide_tracked) >= s['engine_confirm_windows'])
        candidate = low_candidate or wide_candidate
        confirmed_now = low_confirmed or wide_confirmed
        if confirmed_now:
            self.last_engine_t = t
            if self.engine_session_start is None:
                evidence = tracked if low_confirmed else wide_tracked
                self.engine_session_start = min(evidence)
        engine_recent = bool(t - self.last_engine_t <= s['engine_memory_s'])
        if not engine_recent:
            self.engine_session_start = None

        audio_impact = bool(has_audio and 'audio_transient' in self.th
                            and row['audio_rms'] >= self.th['audio_rms'] * 0.65
                            and row['audio_transient'] > self.th['audio_transient'])
        vib_hit = bool(row.get('vibration_rms') is not None
                       and row['vibration_rms'] > self.th.get('vibration_rms', 1e9)
                       and row.get('vibration_peak', 0) > self.th.get('vibration_peak', 1e9))
        accel_hit = bool(row.get('accel_dynamic_rms') is not None
                         and row['accel_dynamic_rms'] > self.th.get('accel_dynamic_rms', 1e9)
                         and row.get('accel_peak', 0) > self.th.get('accel_peak', 1e9))
        motion = bool(vib_hit or accel_hit)
        if motion and not self.prev_motion:
            self.impacts.append(t)
        self.prev_motion = motion
        while self.impacts and self.impacts[0] < t - s['impact_memory_s']:
            self.impacts.pop(0)
        eligible = 0
        if engine_recent and self.engine_session_start is not None:
            for impact_t in self.impacts:
                if impact_t >= self.engine_session_start - s['impact_pre_engine_s']:
                    eligible += 1
        alarm = 0
        if self.mode == 'audio':
            if confirmed_now:
                state = 'ENGINE_DETECTED'
            elif candidate:
                state = 'ENGINE_CANDIDATE'
            elif engine_recent:
                state = 'ENGINE_RECENT'
            elif audio_impact:
                state = 'AUDIO_IMPACT'
            else:
                state = 'BACKGROUND'
        elif self.mode == 'vibration':
            state = 'MOTION_DETECTED' if motion else 'BACKGROUND'
        else:
            possible = engine_recent and eligible >= s['impacts_for_alarm']
            if (possible and not self.alarm_latched and
                    t - self.last_alarm_t > s['cooldown_s']):
                alarm = 1
                self.last_alarm_t = t
                self.alarm_latched = True
                self.event_id += 1
            if alarm:
                state = 'ALARM'
            elif self.alarm_latched:
                state = 'ALARM_LATCHED'
            elif engine_recent and eligible >= 1:
                state = 'LOADING_SUSPECTED'
            elif confirmed_now or engine_recent:
                state = 'ENGINE_DETECTED'
            elif candidate:
                state = 'ENGINE_CANDIDATE'
            elif motion:
                state = 'MOTION_ONLY'
            else:
                state = 'BACKGROUND'
            # New episode only once the engine memory AND impact memory expired.
            if (self.alarm_latched and not engine_recent and not self.impacts
                    and not motion and t - self.last_alarm_t >= s['engine_memory_s']):
                self.alarm_latched = False

        out = dict(row)
        out.update(engine_score=round(max(score, wide_score), 4),
                   engine_low_confirmed=int(low_confirmed),
                   engine_wide_confirmed=int(wide_confirmed),
                   engine_low_vote_count=len(tracked),
                   engine_wide_vote_count=len(wide_tracked),
                   engine_detected=int(candidate),
                   engine_confirmed=int(confirmed_now),
                   engine_recent=int(engine_recent),
                   engine_reason=('wide_multi' if wide_confirmed or
                                  (wide_candidate and not low_candidate) else
                                  row.get('audio_engine_method', 'none') if low_candidate else
                                  'insufficient_evidence'),
                   audio_impact=int(audio_impact), vibration_detected=int(vib_hit),
                   accelerometer_detected=int(accel_hit), motion_detected=int(motion),
                   recent_motion_events=len(self.impacts), eligible_motion_events=eligible,
                   state=state, alarm=alarm,
                   alarm_event_id=self.event_id if alarm else 0)
        return out
