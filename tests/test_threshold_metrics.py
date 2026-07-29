"""Tests for core/calibration/threshold_metrics.py.

Uses hand-verifiable synthetic cases (not real calibration data — that
requires the actual N=400 run, see Phase 3) to confirm the AUROC / rejection
accuracy / AURAC math matches Farquhar et al. 2024's definitions.
"""
import unittest

from core.calibration.threshold_metrics import auroc, aurac, rejection_accuracy_curve


class TestAUROC(unittest.TestCase):
    def test_perfect_separation_is_one(self):
        # All correct answers have zero entropy (max confidence); all
        # incorrect have high entropy (min confidence). Every correct
        # beats every incorrect -> AUROC = 1.0.
        scores = [0.0, 0.0, 0.0, 2.0, 2.0, 2.0]
        correct = [True, True, True, False, False, False]
        self.assertAlmostEqual(auroc(scores, correct), 1.0)

    def test_perfectly_inverted_is_zero(self):
        # Incorrect answers have the lowest entropy (highest confidence) —
        # the uncertainty method is anti-informative here.
        scores = [0.0, 0.0, 0.0, 2.0, 2.0, 2.0]
        correct = [False, False, False, True, True, True]
        self.assertAlmostEqual(auroc(scores, correct), 0.0)

    def test_identical_scores_both_classes_is_half(self):
        # No separation at all: every score tied -> AUROC = 0.5 exactly
        # (average-rank tie handling).
        scores = [1.0, 1.0, 1.0, 1.0]
        correct = [True, False, True, False]
        self.assertAlmostEqual(auroc(scores, correct), 0.5)

    def test_all_correct_returns_uninformative_half(self):
        scores = [0.1, 0.5, 0.9]
        correct = [True, True, True]
        self.assertEqual(auroc(scores, correct), 0.5)

    def test_all_incorrect_returns_uninformative_half(self):
        scores = [0.1, 0.5, 0.9]
        correct = [False, False, False]
        self.assertEqual(auroc(scores, correct), 0.5)

    def test_empty_input_returns_half(self):
        self.assertEqual(auroc([], []), 0.5)

    def test_mismatched_lengths_raises(self):
        with self.assertRaises(ValueError):
            auroc([1.0, 2.0], [True])

    def test_partial_separation_known_value(self):
        # 2 correct (conf 3, 1), 2 incorrect (conf 2, 0) via raw_dse
        # (entropy) = -confidence -> scores = [-3, -1, -2, 0].
        # Mann-Whitney: correct-vs-incorrect wins: (3>2)=W,(3>0)=W,(1>2)=L,(1>0)=W
        # 3 wins out of 4 pairs -> AUROC = 0.75.
        scores = [-3.0, -1.0, -2.0, 0.0]
        correct = [True, True, False, False]
        self.assertAlmostEqual(auroc(scores, correct), 0.75)


class TestRejectionAccuracyCurve(unittest.TestCase):
    def test_most_confident_first_gives_full_accuracy_at_low_x(self):
        # Lowest entropy (most confident) 2 items are both correct; the
        # rest are incorrect. At X% covering only those 2, accuracy = 1.0.
        scores = [0.0, 0.1, 5.0, 5.0, 5.0, 5.0]
        correct = [True, True, False, False, False, False]
        curve = rejection_accuracy_curve(scores, correct, steps=6)
        # First cutoff (X=1/6*100=16.67%) keeps ceil-ish 1 item -> correct.
        first_x, first_acc = curve[0]
        self.assertAlmostEqual(first_acc, 1.0)
        # Last cutoff (X=100%) keeps everything -> overall accuracy = 2/6.
        last_x, last_acc = curve[-1]
        self.assertAlmostEqual(last_x, 100.0)
        self.assertAlmostEqual(last_acc, 2 / 6)

    def test_empty_input_returns_empty_curve(self):
        self.assertEqual(rejection_accuracy_curve([], []), [])

    def test_curve_length_matches_steps(self):
        scores = [0.1, 0.2, 0.3, 0.4]
        correct = [True, False, True, False]
        curve = rejection_accuracy_curve(scores, correct, steps=10)
        self.assertEqual(len(curve), 10)


class TestAURAC(unittest.TestCase):
    def test_perfect_classifier_gives_aurac_one(self):
        # Every cutoff has 100% accuracy -> area = 1.0.
        curve = [(x, 1.0) for x in range(10, 101, 10)]
        self.assertAlmostEqual(aurac(curve), 1.0)

    def test_constant_half_accuracy_gives_aurac_half(self):
        curve = [(x, 0.5) for x in range(10, 101, 10)]
        self.assertAlmostEqual(aurac(curve), 0.5)

    def test_empty_curve_gives_zero(self):
        self.assertEqual(aurac([]), 0.0)

    def test_end_to_end_with_rejection_curve(self):
        # Perfect separation end-to-end: AUROC=1.0 and AURAC should be high
        # (most-confident-first ordering keeps accuracy near 1.0 until the
        # incorrect answers are forced in near the end).
        scores = [0.0, 0.0, 0.0, 0.0, 5.0, 5.0]
        correct = [True, True, True, True, False, False]
        self.assertAlmostEqual(auroc(scores, correct), 1.0)
        curve = rejection_accuracy_curve(scores, correct, steps=6)
        area = aurac(curve)
        # Should be well above 0.5 (informative) and below 1.0 (last
        # cutoffs must include the incorrect answers, dragging accuracy
        # down from perfect).
        self.assertGreater(area, 0.8)
        self.assertLess(area, 1.0)


if __name__ == "__main__":
    unittest.main()
