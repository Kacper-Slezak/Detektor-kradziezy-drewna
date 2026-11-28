import csv
import hashlib
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from algorithm.app.burst_stage_lopy import read_export, stage
from algorithm.app.recall_audio import MANIFEST, acquire, recordings, verify
from algorithm.app.recall_evaluate import phase_diagnostic, predict_export
from algorithm.app.recall_train import fit_mask
from firmware.lib.tg_burst import RATE, Votes

MODEL = MANIFEST.parent / 'models' / 'tg_model_recall.py'


class TestRecall(unittest.TestCase):
    def test_historical_mixes_and_nontraining_rows_are_excluded(self):
        rows = [
            dict(split='train', source='train.wav', augmented='0'),
            dict(split='train', source='train.wav:aug:1', augmented='1'),
            dict(split='train', source='train.wav:aug:2', augmented='0'),
            dict(split='train', source='other.wav', augmented='1'),
            dict(split='val', source='validation.wav', augmented='0'),
            dict(split='test', source='test.wav', augmented='0'),
        ]
        self.assertEqual(fit_mask(rows).tolist(), [True, False, False, False, False, False])

    def test_manifest_rejects_cross_role_recording_groups_and_unpinned_audio(self):
        rows = recordings(MANIFEST)
        validation = next(row for row in rows if row['role'] == 'validation')
        validation['group'] = rows[0]['group']
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'sources.csv'
            with path.open('w', encoding='utf8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0])
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, 'duplicate recording'):
                recordings(path)
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            verify(b'wrong recording', rows[0])

    def test_capture_phase_uses_constant_window_count(self):
        model = read_export(MODEL)
        result = phase_diagnostic(np.zeros(3 * RATE, dtype=np.int16), model)
        self.assertEqual(result['offset_samples'], [0, 122, 244, 366, 488])
        self.assertEqual(result['windows'], 2)
        self.assertEqual(len(result['hits_per_offset']), 5)
        self.assertEqual(result['min_max_score'], result['max_score'])

    def test_acquisition_pins_bytes_and_reuses_the_local_copy(self):
        data = b'archive downloader fixture'
        row = recordings(MANIFEST)[0]
        row['sha256'] = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'sources.csv'
            destination = Path(temp) / 'downloads'
            with path.open('w', encoding='utf8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=row)
                writer.writeheader()
                writer.writerow(row)
            with patch('algorithm.app.recall_audio.urlopen', return_value=BytesIO(b'wrong')):
                with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                    acquire(path, destination)
            self.assertFalse((destination / row['file']).exists())
            with patch('algorithm.app.recall_audio.urlopen', return_value=BytesIO(data)) as download:
                acquire(path, destination)
                acquire(path, destination)
                download.assert_called_once()
            self.assertEqual((destination / row['file']).read_bytes(), data)

    def test_optional_export_loads_and_stages_with_existing_device_modules(self):
        model = read_export(MODEL)
        self.assertEqual((model.INPUTS, model.HIDDEN, model.THRESHOLD), (32, 16, .83))
        self.assertEqual((model.SPAN, model.REQUIRED, len(model.WEIGHTS)), (2, 1, 528))
        scores = predict_export(model, np.zeros((2, model.INPUTS), np.float32))
        self.assertTrue(np.all((0 < scores) & (scores < 1)))
        votes = Votes(model.THRESHOLD, model.SPAN, model.REQUIRED)
        self.assertFalse(votes.step(.1))
        self.assertTrue(votes.step(.9))
        self.assertFalse(votes.step(None))
        self.assertFalse(votes.step(.9))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'stage'
            stage(path, MODEL)
            staged = path / 'lib' / 'tg_model_burst.py'
            self.assertEqual(staged.read_bytes(), MODEL.read_bytes())


if __name__ == '__main__':
    unittest.main()
