"""Threshold-based stateful classification; compatible with desktop rules.

Pure Python 3.5 subset: runs in Pycom MicroPython and CPython. No NumPy.
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
        self.engine_streak = 0
        self.last_engine_t = -1e9
        self.prev_motion = False
        self.impacts = []
        self.last_alarm_t = -1e9
        self.previous_t = None

    def step(self, row):
        s = self.s
        t = float(row['time_s'])
        valid = bool(row.get('valid', True))
        if self.previous_t is not None:
            if t <= self.previous_t:
                raise ValueError('time_s must increase')
            if t - self.previous_t > 1.5 * float(s['hop_s']):
                self.reset()
        self.previous_t = t

        # Fails closed on loss of sampling integrity or sensor availability.
        if not valid:
            self.reset()
            self.previous_t = t
            row = dict(row)
            row.update(engine_detected=0, engine_confirmed=0, audio_impact=0,
                       vibration_detected=0, accelerometer_detected=0,
                       motion_detected=0, recent_motion_events=0,
                       state='DATA_INVALID', alarm=0)
            return row

        need_audio = self.mode in ('audio', 'fusion')
        need_motion = self.mode in ('vibration', 'fusion')
        has_audio = row.get('audio_rms') is not None
        has_motion = (row.get('vibration_rms') is not None
                      or row.get('accel_dynamic_rms') is not None)
        if (need_audio and not has_audio) or (need_motion and not has_motion):
            self.reset()
            self.previous_t = t
            row = dict(row)
            row.update(engine_detected=0, engine_confirmed=0, audio_impact=0,
                       vibration_detected=0, accelerometer_detected=0,
                       motion_detected=0, recent_motion_events=0,
                       state='SENSOR_MISSING', alarm=0)
            return row

        th = self.th
        engine_now = bool(has_audio and 'audio_rms' in th
                          and row['audio_rms'] > th['audio_rms']
                          and row['audio_low_ratio'] >= s['low_ratio_min'])
        audio_impact = bool(has_audio and 'audio_transient' in th
                            and row['audio_rms'] >= th['audio_rms'] * 0.65
                            and row['audio_transient'] > th['audio_transient'])
        self.engine_streak = self.engine_streak + 1 if engine_now else 0
        if self.engine_streak >= s['engine_confirm_windows']:
            self.last_engine_t = t
        engine_recent = bool(t - self.last_engine_t <= s['engine_memory_s'])

        v_hit = bool(row.get('vibration_rms') is not None
                     and 'vibration_rms' in th and 'vibration_peak' in th
                     and row['vibration_rms'] > th['vibration_rms']
                     and row['vibration_peak'] > th['vibration_peak'])
        a_hit = bool(row.get('accel_dynamic_rms') is not None
                     and 'accel_dynamic_rms' in th and 'accel_peak' in th
                     and row['accel_dynamic_rms'] > th['accel_dynamic_rms']
                     and row['accel_peak'] > th['accel_peak'])
        motion = bool(v_hit or a_hit)
        if motion and not self.prev_motion:
            self.impacts.append(t)
        self.prev_motion = motion
        while self.impacts and self.impacts[0] < t - s['impact_memory_s']:
            self.impacts.pop(0)

        alarm = 0
        if self.mode == 'audio':
            if engine_recent and audio_impact:
                state = 'ENGINE_AND_AUDIO_IMPACT'
            elif engine_recent:
                state = 'ENGINE_SOUND'
            elif audio_impact:
                state = 'AUDIO_IMPACT'
            else:
                state = 'BACKGROUND'
        elif self.mode == 'vibration':
            state = 'MOTION_DETECTED' if motion else 'BACKGROUND'
        else:
            possible = engine_recent and len(self.impacts) >= s['impacts_for_alarm']
            alarm = int(possible and t - self.last_alarm_t > s['cooldown_s'])
            if alarm:
                self.last_alarm_t = t
            if possible:
                state = 'POSSIBLE_LOADING'
            elif engine_recent:
                state = 'ENGINE_ONLY'
            elif motion:
                state = 'MOTION_ONLY'
            else:
                state = 'BACKGROUND'
        out = dict(row)
        out.update(engine_detected=int(engine_now), engine_confirmed=int(engine_recent),
                   audio_impact=int(audio_impact), vibration_detected=int(v_hit),
                   accelerometer_detected=int(a_hit), motion_detected=int(motion),
                   recent_motion_events=len(self.impacts), state=state, alarm=alarm)
        return out
