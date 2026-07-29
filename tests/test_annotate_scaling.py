"""Regression tests for annotate_screenshot's coordinate scaling.

Caught during the DSE calibration experiment: annotated screenshots showed
every widget box drifting progressively downward the further down the screen
it was — the top-most box looked pixel-perfect while the bottom-most box sat
~30px below the text it was supposed to bound.

The widget bounds themselves were correct (verified against real EasyOCR
output). The bug was purely in rendering: the scale factor was computed
unconditionally as `img_h / max_y`, where max_y is the bottom edge of the
lowest *detected element*, not the screen height. For a vision-only
screenshot whose lowest element ends at y=1886 in a 1920px-tall image, that
produced a spurious 1.018x vertical stretch.

The scaling is legitimate for its original purpose — XML hierarchy bounds
from a device whose logical resolution exceeds the captured screenshot — so
it's kept, but gated on the bounds actually overflowing the image.
"""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

# Stub easyocr before importing observer_tools (heavy torch-backed import,
# and the OCR model is irrelevant to what these tests verify).
_easyocr_stub = types.ModuleType("easyocr")
_easyocr_stub.Reader = MagicMock(return_value=MagicMock())
sys.modules.setdefault("easyocr", _easyocr_stub)

from tools.observer_tools import ObserverTools  # noqa: E402


def _get_annotate_tool():
    tools = ObserverTools(device_session=None).get_tools()
    return next(t for t in tools if t.name == "annotate_screenshot")


class TestAnnotateScreenshotScaling(unittest.TestCase):
    def setUp(self):
        self.annotate = _get_annotate_tool()
        self.img = np.zeros((1920, 1080, 3), dtype=np.uint8)

    def _rectangles_drawn(self, elements):
        """Run annotate_screenshot and capture the rectangle coordinates it
        actually draws (the first rectangle per element is the widget box;
        the second is the id-label background, which we ignore)."""
        drawn = []

        def fake_rectangle(img, pt1, pt2, color, thickness):
            drawn.append((pt1, pt2, thickness))
            return img

        with patch("tools.observer_tools.os.path.exists", return_value=True), \
             patch("tools.observer_tools.cv2.imread", return_value=self.img), \
             patch("tools.observer_tools.cv2.imwrite", return_value=True), \
             patch("tools.observer_tools.cv2.rectangle", side_effect=fake_rectangle), \
             patch("tools.observer_tools.cv2.circle"), \
             patch("tools.observer_tools.cv2.putText"):
            self.annotate.invoke({
                "image_path": "fake.png",
                "elements": elements,
                "save_path": "/tmp/unused.png",
            })
        # thickness=-1 is the filled label background, not the widget box.
        return [(p1, p2) for p1, p2, th in drawn if th != -1]

    def test_bounds_within_image_are_drawn_unscaled(self):
        """The actual bug: real pixel-space bounds must be drawn verbatim.

        Uses the real bounds from Screen Annotation screen 60363, where this
        was caught. max_y across these elements is 1886 (< 1920), which
        previously triggered a 1.018x stretch.
        """
        elements = [
            {"id": 0, "bounds": [150, 107, 546, 179], "text": "Test description"},
            {"id": 1, "bounds": [285, 1629, 801, 1689], "text": "Continue to the test"},
            {"id": 2, "bounds": [0, 1850, 1080, 1886], "text": ""},
        ]
        rects = self._rectangles_drawn(elements)

        self.assertEqual(rects[0], ((150, 107), (546, 179)))
        # This is the one that visibly detached: was drawn at y=1658..1719.
        self.assertEqual(rects[1], ((285, 1629), (801, 1689)))
        self.assertEqual(rects[2], ((0, 1850), (1080, 1886)))

    def test_bounds_overflowing_image_are_scaled_down(self):
        """The case the scaling was written for must still work: XML bounds
        from a 1440x2560 device rendered onto a 1080x1920 screenshot."""
        elements = [
            {"id": 0, "bounds": [0, 0, 1440, 2560], "text": ""},
            {"id": 1, "bounds": [720, 1280, 1440, 2560], "text": ""},
        ]
        rects = self._rectangles_drawn(elements)

        # scale_x = 1080/1440 = 0.75, scale_y = 1920/2560 = 0.75
        self.assertEqual(rects[0], ((0, 0), (1080, 1920)))
        self.assertEqual(rects[1], ((540, 960), (1080, 1920)))

    def test_exact_fit_is_not_rescaled(self):
        """Bounds that exactly match the image dimensions are already correct
        and must be left alone (scale factor exactly 1.0, no rounding drift)."""
        elements = [{"id": 0, "bounds": [0, 0, 1080, 1920], "text": ""}]
        rects = self._rectangles_drawn(elements)
        self.assertEqual(rects[0], ((0, 0), (1080, 1920)))

    def test_center_dot_uses_unscaled_bounds_too(self):
        """The green center dot is drawn from `bounds` via the same scale
        factors, so it drifted identically. Verify it lands on the true
        center of the widget."""
        elements = [
            {"id": 0, "bounds": [285, 1629, 801, 1689], "text": "Continue to the test"},
            {"id": 1, "bounds": [0, 1850, 1080, 1886], "text": ""},
        ]
        circles = []

        def fake_circle(img, center, radius, color, thickness):
            circles.append(center)
            return img

        with patch("tools.observer_tools.os.path.exists", return_value=True), \
             patch("tools.observer_tools.cv2.imread", return_value=self.img), \
             patch("tools.observer_tools.cv2.imwrite", return_value=True), \
             patch("tools.observer_tools.cv2.rectangle"), \
             patch("tools.observer_tools.cv2.circle", side_effect=fake_circle), \
             patch("tools.observer_tools.cv2.putText"):
            self.annotate.invoke({
                "image_path": "fake.png",
                "elements": elements,
                "save_path": "/tmp/unused.png",
            })

        self.assertEqual(circles[0], ((285 + 801) // 2, (1629 + 1689) // 2))


if __name__ == "__main__":
    unittest.main()
