"""Tests for the uniform-region detection channel in detect_visual_elements.

Motivation (found during the DSE calibration experiment): a Material-style
filled button — rgb(213,214,212) on an rgb(250,250,250) page — produced
literally ZERO Canny edge pixels along its border, because after the 5x5
Gaussian blur the soft antialiased edge's gradient magnitude sits below
Canny's low threshold of 50. The button was never detected; only the text
drawn on top of it was, so the widget bounds covered the label instead of the
tappable control.

Lowering Canny's thresholds does not fix this (measured against Screen
Annotation ground truth: recall@IoU0.5 29.2% -> 30.7%, BUTTON recall flat at
26.0%) because the problem is the absence of a gradient, not the threshold
applied to it. Region-based segmentation of uniform-colour areas is the
standard remedy — see Chen et al. 2020, ESEC/FSE, "Object Detection for
Graphical User Interface: Old Fashioned or Deep Learning or a Combination?".

Held-out measurement (45 Screen Annotation screens not used for tuning):
    recall@IoU0.5   35.4% -> 46.5%
    BUTTON recall   34.9% -> 47.7%
    mean best IoU   0.376 -> 0.477
"""
import json
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock

import cv2
import numpy as np

_easyocr_stub = types.ModuleType("easyocr")
_easyocr_stub.Reader = MagicMock(return_value=MagicMock())
sys.modules.setdefault("easyocr", _easyocr_stub)

from tools.observer_tools import ObserverTools  # noqa: E402


def _iou(a, b):
    xA, yA = max(a[0], b[0]), max(a[1], b[1])
    xB, yB = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    if inter <= 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class TestUniformRegionDetection(unittest.TestCase):
    def setUp(self):
        tools = ObserverTools(device_session=None).get_tools()
        self.detect = next(t for t in tools if t.name == "detect_visual_elements")
        self.tmpdir = tempfile.mkdtemp()

    def _run(self, img):
        path = os.path.join(self.tmpdir, "shot.png")
        cv2.imwrite(path, img)
        return json.loads(self.detect.invoke({"image_path": path, "save_path": ""}))

    def test_low_contrast_filled_button_is_detected(self):
        """The exact real-world failure: a light grey button on a near-white
        page. Canny alone finds nothing here."""
        img = np.full((1920, 1080, 3), 250, dtype=np.uint8)
        button = [51, 1386, 1027, 1553]  # real GT bounds from screen 60363
        cv2.rectangle(img, (button[0], button[1]), (button[2], button[3]), (213, 214, 212), -1)

        # Sanity-check the premise: Canny really does see nothing here.
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edge_px = int((cv2.Canny(blurred, 50, 150) > 0).sum())
        self.assertEqual(edge_px, 0, "premise broken: Canny now sees this edge")

        elements = self._run(img)
        best = max((_iou(button, e["bounds"]) for e in elements), default=0.0)
        self.assertGreater(best, 0.85, f"button not recovered; best IoU={best:.3f}")

    def test_high_contrast_elements_still_detected(self):
        """Channel 1 must be unaffected — a dark bordered box on white is an
        ordinary Canny detection and must keep working."""
        img = np.full((800, 600, 3), 255, dtype=np.uint8)
        box = [100, 200, 400, 320]
        cv2.rectangle(img, (box[0], box[1]), (box[2], box[3]), (20, 20, 20), 3)

        elements = self._run(img)
        best = max((_iou(box, e["bounds"]) for e in elements), default=0.0)
        self.assertGreater(best, 0.7, f"bordered box lost; best IoU={best:.3f}")

    def test_blank_screen_produces_no_giant_box(self):
        """A featureless screen must not yield one huge region covering
        everything — the >80% total-area filter must still apply."""
        img = np.full((1000, 800, 3), 245, dtype=np.uint8)
        elements = self._run(img)
        total = 1000 * 800
        for e in elements:
            b = e["bounds"]
            area = (b[2] - b[0]) * (b[3] - b[1])
            self.assertLessEqual(area, total * 0.80)

    def test_duplicate_detections_are_suppressed(self):
        """A filled button with a visible dark border is found by BOTH
        channels; NMS must collapse them to one box, not emit two."""
        img = np.full((900, 700, 3), 250, dtype=np.uint8)
        box = [100, 300, 600, 420]
        cv2.rectangle(img, (box[0], box[1]), (box[2], box[3]), (200, 200, 200), -1)
        cv2.rectangle(img, (box[0], box[1]), (box[2], box[3]), (60, 60, 60), 2)

        elements = self._run(img)
        near_dupes = [e for e in elements if _iou(box, e["bounds"]) > 0.7]
        self.assertEqual(len(near_dupes), 1, f"expected 1 box, got {len(near_dupes)}")

    def test_output_schema_unchanged(self):
        """Region-channel boxes must be indistinguishable in shape from Canny
        boxes so downstream _merge_and_filter needs no changes."""
        img = np.full((900, 700, 3), 250, dtype=np.uint8)
        cv2.rectangle(img, (100, 300), (600, 420), (213, 214, 212), -1)
        for e in self._run(img):
            self.assertEqual(list(e.keys()), ["bounds"])
            self.assertEqual(len(e["bounds"]), 4)
            self.assertTrue(all(isinstance(v, int) for v in e["bounds"]))


if __name__ == "__main__":
    unittest.main()
