"""v4.3 LoPy selective teacher training export and evaluation checks."""
import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from algorithm.app.v4_3_lopy_train import (selective_targets, teacher_weight_multiplier,
                                           choose_operating_threshold, run)
from algorithm.app.v4_3_compare import evaluate
from algorithm.app.v4_2_infer import load_student
from algorithm.core.tg_ml import FEATURES
from algorithm.core.tg_nn import predict_score


class SelectiveDistillationTests(unittest.TestCase):
    def test_teacher_disagreement_never_corrupts_hard_labels(self):
        target,agreements=selective_targets(
            [1,1,0,0],[.05,.75,.95,.02],alpha=.2,cutoff=.24)
        np.testing.assert_allclose(target,[1.0,.95,0.0,.004],rtol=0,atol=1e-6)
        np.testing.assert_array_equal(agreements,[False,True,False,True])
        w=teacher_weight_multiplier([1,0,0],[.01,.95,.01],cutoff=.24,boost=2)
        self.assertEqual(w[0],1)
        self.assertGreater(w[1],w[2])

    def test_threshold_does_not_hide_constraint_failure(self):
        y=np.array([1,1,0,0]);s=np.array([.8,.6,.7,.2])
        _,_,details=choose_operating_threshold(y,s,1.0,1.0)
        self.assertFalse(details['meets_both_targets'])

    def test_multi_model_compare(self):
        r=lambda t,h,p,a:dict(midpoint=t,valid=True,hit=h,persistent=p,alarm=a,score=.5)
        result=evaluate([r(1,1,0,0),r(2,0,0,0)],
                        [r(18,0,0,0),r(20,1,0,0),r(21,1,1,0)],19,40)
        self.assertEqual(result['truck_positive_hits'],2)
        self.assertEqual(result['forest_hits'],1)
        self.assertEqual(result['truck_first_confirmation_midpoint_s'],21)

    def test_training_and_export_without_adding_lopy_runtime_dependencies(self):
        # Tiny synthetic data verifies code, NOT acoustic accuracy.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);prepared=root/'prepared';prepared.mkdir()
            rng=np.random.default_rng(321)
            X=[];y=[];sp=[];rows=[];teacher=[]
            for split in ('train','val','test'):
                for label in (0,1):
                    for j in range(20):
                        x=rng.normal(0,.3,63).astype(np.float32)
                        x[:10] += .7*label
                        X.append(x);y.append(label);sp.append(split)
                        teacher.append(.82 if label else .06)
                        rows.append({'index':len(X)-1,'source':'%s-%s-%d' % (split,label,j//4),
                                     'time_s':j%4,'label':label,'split':split,'teacher_audio':'dummy.wav'})
            np.savez_compressed(prepared/'features.npz',X=np.asarray(X,dtype=np.float32),
                                y=np.asarray(y,dtype=np.int8),
                                splits=np.asarray(sp,dtype='<U5'))
            with (prepared/'windows.csv').open('w',newline='',encoding='utf-8') as f:
                wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
            files={x:hashlib.sha256((prepared/x).read_bytes()).hexdigest()
                   for x in ('features.npz','windows.csv')}
            (prepared/'teacher_report.json').write_text(json.dumps({
                'features_sha256':files['features.npz'],
                'windows_sha256':files['windows.csv']}),encoding='utf-8')
            scores=np.asarray(teacher,np.float32)
            scores[len(sp)//3:]=np.nan # only training scores need be defined
            np.save(prepared/'teacher_scores.npy',scores)
            output=root/'lopy_student'
            args=SimpleNamespace(results=prepared,output_dir=output,teacher_alpha=.2,
                teacher_cutoff=.24,hard_negative_boost=1.5,
                min_val_recall=.7,target_val_specificity=.9,
                epochs=5,batch=24,lr=.001,seed=123,max_export_bytes=32768,overwrite=False)
            run(args)
            report=json.loads((output/'report.json').read_text())
            self.assertLess(report['model_flash_file_bytes'],32768)
            self.assertEqual(report['int8_weight_bytes'],4200)
            self.assertEqual(report['architecture'],[63,48,24,1])
            student=load_student(output/'tg_model_v42.py')
            row=dict(zip(FEATURES,X[0][:15]));row['tiny_spectral_bands']=X[0][15:]
            self.assertTrue(0<=predict_score(row,student)<=1)
            self.assertFalse(report['hardware_ram_measured'])
            staged=root/'staged'
            command=[sys.executable,'-m','algorithm.app.v4_3_stage_lopy',
                     '--model',str(output/'tg_model_v42.py'),'--output',str(staged)]
            p=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertTrue((staged/'lib'/'tg_model_v42.py').is_file())
            self.assertTrue((staged/'lopy_memory_probe.py').is_file())
            with self.assertRaises(FileExistsError):run(args)


if __name__=='__main__':unittest.main()
