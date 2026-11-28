import unittest

import numpy as np

from algorithm.app.engine_diagnose import auc, describe_geometry
from algorithm.app.engine_event_audit import clip_comparison, replay_comparison
from algorithm.app.engine_provenance import align, match_offset


class TestEngineDiagnosis(unittest.TestCase):
    def test_auc_counts_ties_and_unavailable_groups(self):
        self.assertEqual(auc([1, 2], [0, 2]), .625)
        self.assertIsNone(auc([], [1]))

    def test_eligibility_uses_consecutive_valid_hops(self):
        rows = [dict(source='engine', time_s=t, label=1) for t in (0, 1, 2, 4)]
        rows += [dict(source='background', time_s=t, label=0) for t in (0, 1)]
        report = clip_comparison(rows, [1, None, 1, 1, 1, 1], .5, (15, 9))
        self.assertEqual(report['native']['engine']['eligible'], 0)
        self.assertEqual(report['two_consecutive']['engine']['eligible'], 0)
        self.assertEqual(report['two_consecutive']['negative']['confirmed'], 1)
        self.assertEqual(report['one_hit']['engine']['confirmed'], 1)

    def test_timed_event_starts_with_empty_vote_history(self):
        report = replay_comparison([0, 1, 1, 1, 1], .5, (2, 2), (2, 6))
        self.assertEqual(report['native']['starts_s'], [4])
        self.assertEqual(report['native']['event_only_delay_s'], 3)
        self.assertEqual(report['one_hit']['event_only_delay_s'], 2)
        self.assertIsNone(replay_comparison([0, 0, 0], .5, (2, 2), (0, 1))
                          ['native']['event_only_delay_s'])

    def test_alignment_handles_nonzero_offset_and_unequal_length(self):
        reference = np.random.default_rng(2026).normal(0, 30, 128)
        offset, score = match_offset(reference, reference[50:110], 55)
        self.assertEqual(offset, -5)
        self.assertAlmostEqual(score, 1.0)
        aligned = align(reference, offset, 140)
        np.testing.assert_array_equal(aligned[5:133], reference)
        self.assertFalse(aligned[:5].any())
        self.assertFalse(aligned[133:].any())

    def test_matched_geometries_use_the_same_window_count(self):
        result = describe_geometry({4000: np.zeros(12000), 8000: np.zeros(23999)})
        self.assertEqual([len(features['rms_dbfs']) for features in result.values()], [1, 1, 1])


if __name__ == '__main__':
    unittest.main()
