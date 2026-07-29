"""Tests for core/calibration/ground_truth_alignment.py."""
import unittest

from core.calibration.ground_truth_alignment import align_widget_to_ground_truth


class TestAlignWidgetToGroundTruth(unittest.TestCase):
    def test_high_iou_match_wins(self):
        widget = [100, 100, 200, 150]
        gt = [
            {"type": "BUTTON", "text": "Login", "bbox": [102, 101, 198, 149]},
            {"type": "TEXT", "text": "Unrelated", "bbox": [500, 500, 600, 550]},
        ]
        match = align_widget_to_ground_truth(widget, gt)
        self.assertEqual(match["text"], "Login")

    def test_no_overlap_but_close_center_falls_back_to_distance(self):
        widget = [100, 100, 120, 120]  # center (110, 110)
        gt = [
            {"type": "ICON", "text": "Settings gear", "bbox": [125, 105, 140, 120]},  # center (132.5, 112.5), dist ~22.6
            {"type": "TEXT", "text": "Far away", "bbox": [800, 800, 900, 900]},
        ]
        match = align_widget_to_ground_truth(widget, gt, iou_threshold=0.15, dist_threshold=30.0)
        self.assertEqual(match["text"], "Settings gear")

    def test_nothing_within_threshold_returns_none(self):
        widget = [0, 0, 10, 10]
        gt = [{"type": "TEXT", "text": "Far", "bbox": [900, 900, 950, 950]}]
        match = align_widget_to_ground_truth(widget, gt)
        self.assertIsNone(match)

    def test_elements_with_none_bbox_are_skipped(self):
        widget = [100, 100, 200, 150]
        gt = [
            {"type": "TEXT", "text": "No bbox", "bbox": None},
            {"type": "BUTTON", "text": "Login", "bbox": [100, 100, 200, 150]},
        ]
        match = align_widget_to_ground_truth(widget, gt)
        self.assertEqual(match["text"], "Login")

    def test_empty_ground_truth_returns_none(self):
        self.assertIsNone(align_widget_to_ground_truth([0, 0, 10, 10], []))


if __name__ == "__main__":
    unittest.main()
