"""Evaluate a v4.6 model on independent continuous forest/truck CSV recordings.

Counts per-window detections and false alarms; no optimistic accuracy estimate
from the training dataset. Alarms per hour on 5 minutes are NOT robust rates.
"""
from __future__ import annotations
import argparse,csv,json
from pathlib import Path

def read(path):
    with path.open(newline='',encoding='utf8') as f:
        rows=list(csv.DictReader(f))
    if not rows:raise ValueError('Empty CSV: '+str(path))
    return rows

def evaluate(forest,truck,start,end):
    def check(rows):
        for r in rows:
            if 'time_s' not in r or 'ml_engine_score' not in r:
                raise ValueError('Missing time_s or ml_engine_score in CSV')
        return rows
    f=check(read(forest));t=check(read(truck))
    inside=[r for r in t if start<= (float(r['time_s'])+float(r['window_end_s']))/2 <end]
    if not inside:raise ValueError('No windows in the indicated truck interval')
    def summary(rows):
        scores=[float(r['ml_engine_score']) for r in rows if r['ml_engine_score'] not in ('','None')]
        return dict(windows=len(rows),hits=sum(int(r['engine_detected']) for r in rows),
                    confirmed_windows=sum(int(r['engine_confirmed']) for r in rows),
                    alarm_events=sum(int(r['alarm']) for r in rows),
                    mean_score=(sum(scores)/len(scores)) if scores else None)
    result={'truck_interval_midpoints_s':[start,end],
            'truck_during_event':summary(inside),
            'forest_all':summary(f),
            'truck_full_recording':summary(t),
            'warning':'A few minutes of forest do not establish false alarms per hour. Paired controls are not training data.'}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--forest',type=Path,required=True)
    p.add_argument('--truck',type=Path,required=True)
    p.add_argument('--start',type=float,default=19)
    p.add_argument('--end',type=float,default=40)
    a=p.parse_args()
    print(json.dumps(evaluate(a.forest,a.truck,a.start,a.end),indent=2))
if __name__=='__main__':main()
