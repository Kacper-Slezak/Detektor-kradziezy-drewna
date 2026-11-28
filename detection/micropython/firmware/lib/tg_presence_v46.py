"""Compact on-device v4.6 engine persistence monitor, diagnostic only.

Identical 15s vote/one-shot event rules to PC Presence. Does not import
legacy feature/ML engines. Physical GPIO output is never activated here.
"""
from tg_cnn_v46 import score_features

class Presence:
    def __init__(self,model,threshold,span=15,fraction=0.6,
                 off_hours=None,cooldown_s=60,reset_after_s=8):
        if not (0<threshold<1 and 0<fraction<=1 and span>=2):
            raise ValueError('Invalid presence settings')
        self.model=model;self.threshold=threshold
        self.span=int(span);self.required=int(self.span*fraction+0.999999)
        self.off_hours=off_hours
        self.cooldown_s=cooldown_s;self.reset_after_s=reset_after_s
        self.history=[];self.prev_time=None
        self.last_alarm_time=-1e9
        self.latched=False;self.absent_for=0;self.event_id=0

    def step(self,row,off_hours='use_default'):
        t=float(row['time_s'])
        hours=self.off_hours if off_hours=='use_default' else off_hours
        if self.prev_time is not None and t<=self.prev_time:
            raise ValueError('Nonmonotonic timestamps')
        gap=self.prev_time is not None and t-self.prev_time>1.5
        self.prev_time=t
        if gap or not row.get('valid',True) or row.get('audio_rms') is None:
            self.history=[];self.absent_for=0
            return dict(time_s=t,ml_engine_score=None,engine_detected=0,
                        engine_vote_count=0,engine_required_votes=self.required,
                        engine_confirmed=0,state='DATA_INVALID',alarm=0,valid=False)
        score=float(score_features(row['wide_patch'],row['energy_envelope'],self.model))
        hit=int(score>=self.threshold)
        self.history.append(hit)
        if len(self.history)>self.span:self.history.pop(0)
        votes=sum(self.history)
        persistent=(len(self.history)==self.span and votes>=self.required)
        self.absent_for=0 if hit else self.absent_for+1
        if self.absent_for>=self.reset_after_s:self.latched=False
        alarm=int(bool(persistent and hours is True and not self.latched and
                       t-self.last_alarm_time>=self.cooldown_s))
        if alarm:
            self.event_id+=1;self.last_alarm_time=t;self.latched=True
        state=('PERSISTENT_ENGINE' if persistent else 'PASS_BY' if hit else
               'ENGINE_RECENT' if votes else 'BACKGROUND')
        return dict(time_s=t,ml_engine_score=round(score,5),engine_detected=hit,
                    engine_vote_count=votes,engine_required_votes=self.required,
                    engine_confirmed=int(persistent),state=state,alarm=alarm,
                    valid=True)
