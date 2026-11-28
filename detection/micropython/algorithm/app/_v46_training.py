"""Training helpers used by the v4.6 student only.

Retains the exact v4.2/4.3 metrics, source weighting, selective targets,
and operating-threshold logic. YAMNet remains PC-only.
"""
from __future__ import annotations
import numpy as np
from collections import Counter
def sigmoid(z):
    z=np.clip(z,-30,30)
    return 1.0/(1.0+np.exp(-z))



def metrics(y,p,th):
    preds=(p>=th).astype(np.int8)
    tp=int(((y==1)&(preds==1)).sum());fn=int(((y==1)&(preds==0)).sum())
    fp=int(((y==0)&(preds==1)).sum());tn=int(((y==0)&(preds==0)).sum())
    recall=tp/max(tp+fn,1);spec=tn/max(tn+fp,1)
    return dict(TP=tp,FN=fn,FP=fp,TN=tn,recall=round(recall,4),
                specificity=round(spec,4),balanced_accuracy=round((recall+spec)/2,4))



def choose_threshold(y,p):
    # Balanced accuracy trades off both error types; no all-negative shortcut.
    # All tuning uses validation only, never the held-out test.
    best=None
    for threshold in np.arange(0.20,0.951,0.01):
        m=metrics(y,p,float(threshold))
        criterion=(m['balanced_accuracy'],m['specificity'])
        if best is None or criterion>best[0]:
            best=(criterion,float(threshold),m)
    return best[1],best[2]



def weights_for_sources(y,source):
    group=[str(x).split(':aug:')[0] for x in source]
    counts=Counter(group)
    group_label={}
    for g,l in zip(group,y):
        if g in group_label and group_label[g]!=l:
            raise ValueError('Mixed labels for an original recording')
        group_label[g]=int(l)
    n_groups=Counter(group_label.values())
    result=np.asarray([1.0/(counts[g]*n_groups[int(l)]) for g,l in zip(group,y)],np.float32)
    return result/max(float(result.mean()),1e-12)



def selective_targets(labels, teacher, alpha=0.20, cutoff=0.24):
    """Never change labels toward a teacher score when they disagree.

    Positive: if teacher rejects the event, use its real label.
    Negative: if teacher falsely sees an engine, use its real label.
    """
    labels = np.asarray(labels, dtype=np.int8)
    teacher = np.asarray(teacher, dtype=np.float32)
    if labels.shape != teacher.shape:
        raise ValueError('Label/teacher shape mismatch')
    if not np.all(np.isfinite(teacher)):
        raise ValueError('Teacher scores must be finite')
    if np.any((teacher < 0) | (teacher > 1)):
        raise ValueError('Teacher scores must be in [0,1]')
    agrees = np.where(labels == 1, teacher >= cutoff, teacher < cutoff)
    targets = labels.astype(np.float32)
    targets[agrees] = ((1-alpha)*labels[agrees] + alpha*teacher[agrees])
    return targets, agrees



def teacher_weight_multiplier(labels, teacher, cutoff=0.24, boost=1.5):
    """Emphasize negative clips where the teacher hallucinates engines.

    This boosts training LOSS only; it never assigns ENGINE to a forest clip.
    """
    labels = np.asarray(labels)
    teacher = np.asarray(teacher, dtype=np.float32)
    extra = np.clip((teacher-cutoff)/max(1.0-cutoff,1e-6),0.0,1.0)
    return np.where(labels == 0, 1.0 + boost*extra, 1.0).astype(np.float32)



def choose_operating_threshold(y, scores, min_recall=0.80, target_specificity=0.97):
    """Select on validation ONLY; prioritize specificity at usable recall.

    Always report whether *both* requested constraints were achieved.
    When no threshold meets min recall, use balanced accuracy fallback.
    """
    candidates = []
    for threshold in np.linspace(0.05,0.99,95):
        m = metrics(y,scores,float(threshold))
        candidates.append((float(threshold),m))
    viable = [(t,m) for t,m in candidates if m['recall'] >= min_recall]
    suitable = [(t,m) for t,m in viable if m['specificity'] >= target_specificity]
    if suitable:
        # Once both constraints are met, recover as much recall as possible.
        th,m = max(suitable,key=lambda x:(x[1]['recall'],x[1]['specificity'],-x[0]))
        strategy = 'highest_recall_under_specificity_target'
    elif viable:
        # Constraints not simultaneously feasible; report this explicitly.
        th,m = max(viable,key=lambda x:(x[1]['specificity'],x[1]['recall'],-x[0]))
        strategy = 'highest_specificity_at_minimum_recall_target_not_met'
    else:
        th,m = max(candidates,key=lambda x:(x[1]['balanced_accuracy'],x[1]['specificity']))
        strategy = 'balanced_accuracy_fallback_min_recall_not_reached'
    return th,m,{
        'strategy':strategy,
        'requested_min_recall':float(min_recall),
        'requested_target_specificity':float(target_specificity),
        'meets_both_targets':bool(m['recall']>=min_recall and m['specificity']>=target_specificity),
    }

