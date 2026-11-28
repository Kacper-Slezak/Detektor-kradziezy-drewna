"""Hard-label training and continuous CSV diagnostics regression tests."""
import argparse
import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from algorithm.app.v4_2_train import run as train
from algorithm.app.v4_2_compare_csv import (read_csv, summarize, verify_alignment)
from algorithm.app.v4_2_teacher_diagnose import teacher_scores_for_windows
from algorithm.core.tg_nn import predict_score
from algorithm.core.tg_ml import FEATURES
from algorithm.app.v4_2_infer import load_student


class V42ExperimentTests(unittest.TestCase):
    def test_hard_label_training_does_not_require_teacher_and_is_portable(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            prepared = root/'prepared'
            prepared.mkdir()
            # Synthetic test: verifies the training/export plumbing, NOT accuracy.
            rng = np.random.default_rng(123)
            X=[]; y=[]; splits=[]; meta=[]
            for split in ('train', 'val', 'test'):
                for label in (0, 1):
                    for j in range(12):
                        x = rng.normal(0, .2, 63).astype(np.float32)
                        x[:10] += label*.5
                        X.append(x);y.append(label);splits.append(split)
                        meta.append({'index':len(X)-1,'source':f'{split}-{label}-{j//4}',
                                     'time_s':float(j%4),'label':label,
                                     'split':split,'teacher_audio':''})
            np.savez_compressed(prepared/'features.npz',
                                X=np.asarray(X, dtype=np.float32),
                                y=np.asarray(y, dtype=np.int8),
                                splits=np.asarray(splits, dtype='<U5'))
            with (prepared/'windows.csv').open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=list(meta[0]))
                writer.writeheader();writer.writerows(meta)
            out = root/'hard'
            args=argparse.Namespace(results=prepared,output_dir=out,
                                    teacher_alpha=0.0,epochs=3,batch=12,
                                    lr=0.001,seed=2026)
            train(args)
            self.assertFalse((prepared/'tg_model_v42.py').exists())
            self.assertTrue((out/'report.json').is_file())
            self.assertTrue((out/'test_windows.csv').is_file())
            self.assertEqual(json.loads((out/'report.json').read_text())['teacher_alpha'],0)
            model=load_student(out/'tg_model_v42.py')
            row=dict(zip(FEATURES,X[0][:15]))
            row['tiny_spectral_bands']=X[0][15:]
            self.assertTrue(0<=predict_score(row,model)<=1)
            with self.assertRaisesRegex(FileNotFoundError,'teacher_report.json'):
                train(argparse.Namespace(**{**vars(args),'output_dir':root/'teacher',
                                            'teacher_alpha':0.2}))

    def test_compare_does_not_count_negative_events_as_positive(self):
        def row(t, hit, confirmed=0):
            return {'time_s':float(t),'midpoint':float(t)+1,'valid':True,
                    'score':.9 if hit else .1,'detected':int(hit),
                    'confirmed':int(confirmed),'alarm':0}
        forest=[row(0,0),row(1,1),row(2,0)]
        truck=[row(18,0),row(19,1),row(20,1,1),row(39,0),row(41,1)]
        m=summarize(forest,truck,19,40)
        self.assertEqual(m['counts'],dict(TP=2,FN=1,FP=2,TN=3))
        self.assertEqual(m['first_engine_confirmation_s'],21)
        self.assertEqual(m['false_confirmations_forest_windows'],0)
        verify_alignment(forest,[dict(r) for r in forest],'forest')
        with self.assertRaises(ValueError):
            verify_alignment(forest,truck,'bad')

    def test_teacher_patch_alignment(self):
        centers=np.array([.48,.96,1.44,1.92,2.40])
        scores=np.array([.1,.5,.3,.8,.6])
        student=[{'time_s':'0','window_end_s':'2'},
                 {'time_s':'1','window_end_s':'3'}]
        out=teacher_scores_for_windows(centers,scores,student)
        self.assertAlmostEqual(out[0],(.8+.5)/2)
        self.assertAlmostEqual(out[1],(.8+.6)/2)


if __name__=='__main__': unittest.main()
