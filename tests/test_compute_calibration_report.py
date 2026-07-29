"""Tests for core/calibration/compute_calibration_report.py."""
import json
import os
import tempfile
import unittest

from core.calibration.compute_calibration_report import build_report, load_pairs


class TestComputeCalibrationReport(unittest.TestCase):
    def _write_screen(self, d, screen_id, widgets, skipped_match=0, skipped_parse=0):
        path = os.path.join(d, f"{screen_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "screen_id": screen_id,
                "widgets": widgets,
                "skipped_no_ground_truth_match": skipped_match,
                "skipped_parse_failure": skipped_parse,
            }, f)

    def test_load_pairs_pools_across_screens(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_screen(d, "1", [
                {"element_id": 1, "raw_dse": 0.0, "is_correct": True},
                {"element_id": 2, "raw_dse": 2.0, "is_correct": False},
            ], skipped_match=1)
            self._write_screen(d, "2", [
                {"element_id": 1, "raw_dse": 0.1, "is_correct": True},
            ], skipped_parse=2)

            scores, labels, n_screens, n_skipped = load_pairs(d)
            self.assertEqual(len(scores), 3)
            self.assertEqual(n_screens, 2)
            self.assertEqual(n_skipped, 3)

    def test_build_report_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            report = build_report(d)
        self.assertEqual(report["n_labeled_widgets"], 0)
        self.assertNotIn("auroc", report)
        self.assertIn("interpretation", report)

    def test_build_report_informative_case(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_screen(d, "1", [
                {"element_id": 1, "raw_dse": 0.0, "is_correct": True},
                {"element_id": 2, "raw_dse": 0.0, "is_correct": True},
                {"element_id": 3, "raw_dse": 3.0, "is_correct": False},
                {"element_id": 4, "raw_dse": 3.0, "is_correct": False},
            ])
            report = build_report(d)

        self.assertEqual(report["n_labeled_widgets"], 4)
        self.assertAlmostEqual(report["auroc"], 1.0)
        self.assertIn("meaningfully above 0.5", report["interpretation"])
        self.assertIn("rejection_accuracy_curve", report)

    def test_build_report_uninformative_case(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_screen(d, "1", [
                {"element_id": 1, "raw_dse": 1.0, "is_correct": True},
                {"element_id": 2, "raw_dse": 1.0, "is_correct": False},
                {"element_id": 3, "raw_dse": 1.0, "is_correct": True},
                {"element_id": 4, "raw_dse": 1.0, "is_correct": False},
            ])
            report = build_report(d)

        self.assertAlmostEqual(report["auroc"], 0.5)
        self.assertIn("close to 0.5", report["interpretation"])


if __name__ == "__main__":
    unittest.main()
