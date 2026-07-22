import sys
import math
import unittest

sys.path.append(".")
from core.uncertainty.dse import raw_dse, normalized_dse


class TestDSEMath(unittest.TestCase):
    def test_single_cluster_is_zero(self):
        self.assertAlmostEqual(raw_dse([5]), 0.0, places=6)
        self.assertAlmostEqual(normalized_dse([5]), 0.0, places=6)

    def test_three_two_split(self):
        # counts [3,2], M=5: raw = -(0.6 ln0.6 + 0.4 ln0.4) ~= 0.6730
        self.assertAlmostEqual(raw_dse([3, 2]), 0.6730116670, places=6)
        # normalized = raw / ln(5) ~= 0.4182
        self.assertAlmostEqual(normalized_dse([3, 2]), 0.4181656601, places=6)

    def test_all_distinct_is_one(self):
        self.assertAlmostEqual(raw_dse([1, 1, 1, 1, 1]), math.log(5), places=6)
        self.assertAlmostEqual(normalized_dse([1, 1, 1, 1, 1]), 1.0, places=6)

    def test_empty_and_single_sample(self):
        self.assertEqual(raw_dse([]), 0.0)
        self.assertEqual(normalized_dse([]), 0.0)
        self.assertEqual(normalized_dse([1]), 0.0)   # effective_M == 1 -> 0.0
        self.assertEqual(normalized_dse([3]), 0.0)   # single cluster, effective_M == 3

    def test_zero_counts_ignored(self):
        self.assertAlmostEqual(raw_dse([3, 0, 2]), raw_dse([3, 2]), places=6)


if __name__ == "__main__":
    unittest.main()
