import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from algorithm.app.burst_prepare import HOP, all_windows
from algorithm.app.spectral_features import extract
from algorithm.app.spectral_transfer import META, cohort, confirm_table, portable_score, vector_score
from firmware.lib.tg_burst import RATE
from firmware.lib.tg_spectral_probe import SpectralProbe, summarize_peaks


class TestSpectralProbe(unittest.TestCase):
    def test_reference_and_portable_features_follow_ring_order(self):
        t = np.arange(5 * RATE) / RATE
        pcm = (3500 * np.sin(2 * np.pi * (126 * t + 7 * t * t)) +
               1200 * np.sin(2 * np.pi * 1480 * t)).astype(np.int16)
        pcm[2 * RATE:2 * RATE + HOP] = 0
        reference = extract(pcm)
        buffer = SpectralProbe()
        rows = []
        for start in range(0, len(pcm), HOP):
            for i in range(512):
                buffer.spectrum.pcm[i] = int(pcm[start + i])
            if buffer.push():
                rows.append(list(buffer.features))
        np.testing.assert_allclose(reference, rows, atol=5e-4, rtol=0)
        np.testing.assert_array_equal(reference[:, :32], all_windows(pcm, 512).astype(np.float32))

    def test_ordered_features_skip_the_artificial_last_to_first_pair(self):
        ring = np.zeros(48)
        centers = [10, 20, 30, 40, 50, 60, 70, 10]
        for i, center in enumerate(centers):
            offset = ((3 + i) % 8) * 6
            ring[offset + 1:offset + 3] = [4, center]
        out = np.zeros(40)
        summarize_peaks(ring, 3, out)
        self.assertEqual(out[33], 4)
        self.assertEqual(out[36], 0)
        self.assertEqual(out[37], 0)

    def test_linear_scores_and_invalid_reset(self):
        rng = np.random.default_rng(2026)
        pcm = rng.integers(-1000, 1000, 3 * RATE, dtype=np.int16)
        model = SimpleNamespace(FEATURE_VERSION=2, INPUTS=40, WEIGHTS=bytes(range(40)),
                                MEAN=(0.,) * 40, INVERSE_STD=(.1,) * 40, SCALE=.02, BIAS=.1)
        np.testing.assert_allclose(portable_score(pcm, model), vector_score(model, extract(pcm)),
                                   atol=5e-4, rtol=0)
        probe = SpectralProbe()
        ready = [probe.push() for _ in range(8)]
        self.assertEqual(ready, [False] * 7 + [True])
        self.assertFalse(probe.push(valid=False))
        self.assertEqual([probe.push() for _ in range(8)], ready)

    def test_transfer_preserves_native_ineligibility_and_common_counts(self):
        engine = dict(id='engine', label=1, category='VehicleEngine', weather_named=True)
        negative = dict(id='other', label=0, category='Generator', weather_named=False)
        result = confirm_table([(engine, {'a': [.8, .7]}), (negative, {'a': [.2, .8]})],
                               {'a': (.6, (15, 9))})['a']
        self.assertIsNone(result['native']['metrics']['recall'])
        self.assertEqual(result['native']['metrics']['ineligible_engine'], 1)
        self.assertEqual(result['two_consecutive']['metrics']['TP'], 1)
        self.assertEqual(result['two_consecutive']['metrics']['FP'], 0)
        self.assertEqual(result['one_of_two']['metrics']['FP'], 1)

    def test_transfer_source_id_hash_and_cross_label_exclusion(self):
        archive = {
            META: b'Source File Name,Dataset File Name,Class Name\n'
                  b'10001__known.wav,clip1.wav,VehicleEngine\n'
                  b'10002__new.wav,clip2.wav,VehicleEngine\n'
                  b'10002__new-take.wav,clip3.wav,VehicleEngine\n'
                  b'10003__seen-hash.wav,clip4.wav,VehicleEngine\n'
                  b'10004__ambiguous.wav,clip5.wav,VehicleEngine\n'
                  b'10004__ambiguous.wav,clip6.wav,Generator\n',
            'FSC22-main/Audios/clip2.wav': b'unique',
            'FSC22-main/Audios/clip4.wav': b'historical audio',
        }
        entry = dict(source_id='10001', sha256=hashlib.sha256(b'historical audio').hexdigest())
        with patch('algorithm.app.spectral_transfer.manifest_rows', return_value=([], [entry])):
            selected = cohort(SimpleNamespace(read=archive.__getitem__), [Path('manifest.csv')])
        self.assertEqual([(row['id'], row['file']) for row, _ in selected], [('10002', 'clip2.wav')])


if __name__ == '__main__':
    unittest.main()
