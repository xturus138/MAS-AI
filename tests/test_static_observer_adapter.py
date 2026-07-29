"""Unit tests for core/calibration/static_observer.py.

Mocks ObserverTools and cv2 so this runs without a GPU/EasyOCR model
download or a live device — the point of this module is exactly that it
needs neither. Verifies wiring, not detection accuracy (that's covered by
the ground-truth-comparison scripts run manually against real data — see
Dokumen Kepake/memory/thesis_vlm_grounding_alternative.md).

As of 2026-07-29 the default detection method is "llm" (zero-shot VLM
grounding via ObserverAgent._detect_widgets_via_llm); "cv_ocr" (the
classical Canny+region+OCR pipeline) is kept as an explicit opt-in.
"""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


class TestExtractWidgetsFromImage(unittest.TestCase):
    def setUp(self):
        # Stub out easyocr so importing tools.observer_tools doesn't try to
        # download/load a real OCR model (heavy, network-dependent, and
        # irrelevant to what this test verifies).
        self._easyocr_stub = types.ModuleType("easyocr")
        self._easyocr_stub.Reader = MagicMock(return_value=MagicMock())
        sys.modules.setdefault("easyocr", self._easyocr_stub)

    def test_raises_on_unreadable_image(self):
        from core.calibration.static_observer import extract_widgets_from_image

        with patch("core.calibration.static_observer.cv2.imread", return_value=None):
            with self.assertRaises(ValueError):
                extract_widgets_from_image("nonexistent.png", "/tmp/does_not_matter")

    def test_llm_method_requires_llm(self):
        from core.calibration.static_observer import extract_widgets_from_image

        fake_img = MagicMock()
        fake_img.shape = (1920, 1080, 3)
        with patch("core.calibration.static_observer.cv2.imread", return_value=fake_img):
            with self.assertRaises(ValueError):
                extract_widgets_from_image(
                    "shot.png", "/tmp/calib_test_workdir", llm=None, method="llm"
                )

    def test_llm_method_calls_detect_widgets_via_llm(self):
        from core.calibration.static_observer import extract_widgets_from_image

        fake_img = MagicMock()
        fake_img.shape = (1920, 1080, 3)
        fake_widgets = [{"id": 1, "text": "Log In", "type": "container", "llm_type": "BUTTON"}]
        fake_llm = MagicMock()

        with patch("core.calibration.static_observer.cv2.imread", return_value=fake_img), \
             patch("core.calibration.static_observer.build_static_observer") as mock_build:
            mock_observer = MagicMock()
            mock_observer._detect_widgets_via_llm.return_value = fake_widgets
            mock_build.return_value = mock_observer

            result = extract_widgets_from_image(
                "shot.png", "/tmp/calib_test_workdir", llm=fake_llm, method="llm"
            )

            self.assertEqual(result, fake_widgets)
            mock_build.assert_called_once_with(llm=fake_llm)
            mock_observer._detect_widgets_via_llm.assert_called_once_with(
                "shot.png", 1080, 1920
            )

    def test_cv_ocr_method_calls_canny_pipeline_with_vision_only_args(self):
        from core.calibration.static_observer import extract_widgets_from_image

        fake_img = MagicMock()
        fake_img.shape = (1920, 1080, 3)

        fake_widgets = [{"id": 1, "text": "Login", "type": "container"}]

        with patch("core.calibration.static_observer.cv2.imread", return_value=fake_img), \
             patch("core.calibration.static_observer.build_static_observer") as mock_build:
            mock_observer = MagicMock()
            mock_observer._run_canny_pipeline.return_value = fake_widgets
            mock_build.return_value = mock_observer

            result = extract_widgets_from_image(
                "shot.png", "/tmp/calib_test_workdir", method="cv_ocr"
            )

            self.assertEqual(result, fake_widgets)
            mock_observer._run_canny_pipeline.assert_called_once()
            _, kwargs = mock_observer._run_canny_pipeline.call_args
            # Vision-only: no XML hierarchy exists for an externally-sourced
            # screenshot, so keyboard state must be forced False, not guessed.
            self.assertEqual(kwargs["is_kb_shown"], False)
            self.assertEqual(kwargs["image_height"], 1920)
            self.assertEqual(kwargs["raw_path"], "shot.png")

    def test_unknown_method_raises(self):
        from core.calibration.static_observer import extract_widgets_from_image

        fake_img = MagicMock()
        fake_img.shape = (1920, 1080, 3)
        with patch("core.calibration.static_observer.cv2.imread", return_value=fake_img):
            with self.assertRaises(ValueError):
                extract_widgets_from_image("shot.png", "/tmp/x", method="not_a_real_method")

    def test_build_static_observer_never_touches_device(self):
        from core.calibration.static_observer import build_static_observer

        with patch("core.calibration.static_observer.ObserverTools") as mock_tools_cls:
            mock_tools_cls.return_value.get_tools.return_value = [MagicMock()] * 6
            build_static_observer()
            # device_session must be None — this adapter has no live device.
            mock_tools_cls.assert_called_once_with(device_session=None)


if __name__ == "__main__":
    unittest.main()
