"""Tests for core/calibration/run_calibration.py.

Mocks every heavy/external boundary (image I/O, widget extraction, LLM
calls, DSE sampling, correctness judging — each already unit-tested in
their own modules) to verify process_screen()'s ORCHESTRATION logic: does
it wire widget -> production description -> raw_dse -> ground-truth match
-> correctness label together correctly, and does it skip (not fabricate)
when a piece is missing.
"""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class TestProcessScreen(unittest.TestCase):
    def setUp(self):
        self._easyocr_stub = types.ModuleType("easyocr")
        self._easyocr_stub.Reader = MagicMock(return_value=MagicMock())
        sys.modules.setdefault("easyocr", self._easyocr_stub)

    def _widgets(self):
        return [
            {"id": 1, "text": "Login", "bounds": [10, 10, 100, 40], "type": "container"},
            {"id": 2, "text": "Cancel", "bounds": [200, 200, 300, 240], "type": "container"},
        ]

    def _ground_truth(self):
        # Native 0-999 normalized [x1, y1, x2, y2] order (already converted
        # by sample_screen_annotation.py's to_xyxy_0_999).
        return [
            {"type": "BUTTON", "text": "Sign in button", "bbox": [5, 5, 105, 45]},
            {"type": "TEXT", "text": "Some unrelated label", "bbox": [500, 500, 600, 550]},
        ]

    def test_widget_matched_to_ground_truth_gets_labeled(self):
        from core.calibration import run_calibration as m

        fake_img = MagicMock()
        fake_img.shape = (1920, 1080, 3)

        with patch.object(m, "extract_widgets_from_image", return_value=self._widgets()), \
             patch.object(m, "build_static_observer") as mock_build, \
             patch.object(m, "encode_image", return_value="b64=="), \
             patch("cv2.imread", return_value=fake_img), \
             patch.object(m, "parse_semantic_map",
                          return_value={1: "Login button", 2: "Cancel button"}), \
             patch.object(m.ObserverUncertaintyService, "measure",
                          return_value={"widgets": [
                              {"element_id": 1, "raw_dse": 0.1},
                              {"element_id": 2, "raw_dse": 0.9},
                          ]}), \
             patch.object(m.CorrectnessJudge, "judge") as mock_judge:

            mock_observer = MagicMock()
            mock_build.return_value = mock_observer

            llm = MagicMock()
            llm.invoke.return_value = MagicMock(content="[1]: Button - Login\nSUMMARY: x")

            def judge_side_effect(predicted, reference, screen_desc):
                is_login = "Login" in predicted
                res = MagicMock()
                res.label = "yes" if is_login else "no"
                res.is_correct = is_login
                return res
            mock_judge.side_effect = judge_side_effect

            result = m.process_screen("999", "fake.jpg", self._ground_truth(),
                                      llm, llm, "/tmp/calib_work_test")

        self.assertEqual(result["screen_id"], "999")
        # Widget 1 (bounds [10,10,100,40]) should align to the Screen
        # Annotation BUTTON at [5,5,105,45] via high IoU.
        widget_1 = next(w for w in result["widgets"] if w["element_id"] == 1)
        self.assertEqual(widget_1["ground_truth_text"], "Sign in button")
        self.assertEqual(widget_1["raw_dse"], 0.1)
        self.assertTrue(widget_1["is_correct"])

        # Widget 2 has no ground-truth match nearby -> skipped, not guessed.
        self.assertEqual(len(result["widgets"]), 1)
        self.assertEqual(result["skipped_no_ground_truth_match"], 1)

    def test_widget_with_no_dse_measurement_is_skipped_not_fabricated(self):
        from core.calibration import run_calibration as m

        fake_img = MagicMock()
        fake_img.shape = (1920, 1080, 3)

        with patch.object(m, "extract_widgets_from_image", return_value=self._widgets()), \
             patch.object(m, "build_static_observer") as mock_build, \
             patch.object(m, "encode_image", return_value="b64=="), \
             patch("cv2.imread", return_value=fake_img), \
             patch.object(m, "parse_semantic_map", return_value={1: "Login button"}), \
             patch.object(m.ObserverUncertaintyService, "measure",
                          return_value={"widgets": [{"element_id": 1, "raw_dse": 0.1}]}):
            mock_build.return_value = MagicMock()
            llm = MagicMock()
            # Only widget 1 reaches the correctness judge (widget 2 is
            # dropped earlier for lacking a raw_dse entry) — "yes" makes
            # that judge call resolve cleanly so this test isolates the
            # "missing raw_dse" skip path specifically.
            llm.invoke.return_value = MagicMock(content="yes")

            result = m.process_screen("999", "fake.jpg", self._ground_truth(),
                                      llm, llm, "/tmp/calib_work_test2")

        # Widget 2 has neither a predicted description nor a raw_dse entry.
        self.assertEqual(result["skipped_parse_failure"], 1)
        self.assertEqual(len(result["widgets"]), 1)
        self.assertEqual(result["widgets"][0]["element_id"], 1)


if __name__ == "__main__":
    unittest.main()
