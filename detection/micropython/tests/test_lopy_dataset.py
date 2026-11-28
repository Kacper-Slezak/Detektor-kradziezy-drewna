from array import array
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from algorithm.app.lopy_dataset import create_manifest, enforce_history, session_registry, validate_labels
from firmware.lib.tg_burst_capture import CaptureWriter, VALID
from tests.test_lopy_bench import metadata


def session(key, split, **extra):
    return dict(dict(session_id=key, group_id=key, site_id=key, site_date='2026-11-20',
                     split=split, exposure='fresh', vehicle_ids=[]), **extra)


def field_file(path, key, value):
    header = metadata(session_id=key, capture_kind='field', implementation='micropython',
                      machine='LoPy with ESP32', clock_kind='operator_utc_anchor',
                      start_utc='2026-11-20T09:00:00Z')
    with path.open('wb') as stream:
        writer = CaptureWriter(stream, header)
        writer.slot(0, 0, 0, 0, 0, 0, VALID, 128000,
                    array('h', [value]) * 512, array('H', [0]) * 512)
        writer.finish(1)


def recording(file, key):
    return dict(file=file, session_id=key, annotation_source='observer video', sync_method='marker',
                sync_uncertainty_s=.05, events=[dict(start_s=.01, end_s=.1, label='truck', distance_m=25)])


class TestLoPyDataset(unittest.TestCase):
    def test_group_site_vehicle_and_exposed_session_guards(self):
        a = session('a', 'train', vehicle_ids=['truck-one'])
        for b, message in (
            (session('b', 'validation', group_id='a'), 'crosses splits'),
            (session('b', 'validation', vehicle_ids=['truck-one']), 'Same known vehicle'),
            (session('b', 'validation', site_id='a'), 'Same known vehicle'),
            (session('b', 'test', exposure='exposed'), 'Invalid or duplicate'),
        ):
            with self.subTest(b=b), self.assertRaisesRegex(ValueError, message):
                session_registry([a, b])
        self.assertEqual(set(session_registry([a, session('b', 'train', group_id='a')])), {'a', 'b'})

    def test_labels_cannot_cross_or_extend_past_capture(self):
        a = dict(start_s=0, end_s=3, label='diesel')
        b = dict(start_s=2, end_s=6, label='rain')
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            validate_labels([a, b], 10, 'trace')
        with self.assertRaisesRegex(ValueError, 'out-of-bounds'):
            validate_labels([a], 2, 'trace')

    def test_catalog_locks_final_annotations_and_rejects_duplicate_payload(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            field_file(root / 'a.lopy', 'a', 16)
            field_file(root / 'b.lopy', 'b', 32)
            catalog = root / 'catalog.json'
            items = [recording('a.lopy', 'a'), recording('b.lopy', 'b')]
            def write():
                catalog.write_text(json.dumps(dict(sessions=[session('a', 'train'), session('b', 'test')],
                                                   recordings=items)), encoding='utf8')
            write()
            original = create_manifest(catalog)
            self.assertEqual(original, create_manifest(catalog, previous=original))
            items[1]['events'][0]['label'] = 'rain'
            write()
            with self.assertRaisesRegex(ValueError, 'final test is locked'):
                create_manifest(catalog, previous=original)
            with self.assertRaisesRegex(ValueError, 'assignment changed'):
                changed = dict(original, sessions=[session('a', 'validation'), session('b', 'test')])
                enforce_history(original, changed)
            field_file(root / 'b.lopy', 'b', 16)
            with self.assertRaisesRegex(ValueError, 'Duplicate PCM'):
                create_manifest(catalog)


if __name__ == '__main__':
    unittest.main()
