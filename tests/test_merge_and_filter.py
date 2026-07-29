"""Regression tests for ObserverAgent._merge_and_filter's CV+OCR box merging.

Covers a real bug found via the DSE calibration experiment: Canny edge
detection routinely splits one line of text into multiple adjacent contours
(e.g. one contour per word, when there's visible letter-spacing). Before this
fix, whichever CV box matched an OCR text block first "won" the text, and
every other CV box that also matched the *same* OCR block became a separate,
textless duplicate widget instead of being consolidated — inflating the
detected-widget count and wasting DSE sampling budget on empty duplicates.

The fixture in `test_two_cv_boxes_matching_one_ocr_line_merge_into_one_widget`
is not invented: it's the real bounding boxes recorded in
`outputs/calibration/results/_work_60363/{ocr,cv}.json` for the header "Test
description" on Screen Annotation screen 60363, where this was first caught.

Fix approach follows Chen et al. 2020 (ESEC/FSE), "Object Detection for
Graphical User Interface: Old Fashioned or Deep Learning or a Combination?",
which documents this exact fragmentation for Canny/contour-based GUI
detectors (their REMAUI baseline) and prescribes non-maximum
suppression — consolidating duplicate candidate boxes into one — rather than
keeping them as separate detections.
"""
import unittest
from unittest.mock import MagicMock

from agents.observer_agent import ObserverAgent


def _make_agent():
    return ObserverAgent(llm=None, tools=[MagicMock()] * 6, memory=None, logger=None, monitor=None)


class TestMergeAndFilter(unittest.TestCase):
    def test_two_cv_boxes_matching_one_ocr_line_merge_into_one_widget(self):
        # Real bounds from _work_60363/ocr.json and cv.json.
        ocr_elements = [
            {"text": "Test description", "bounds": [151, 108, 545, 176]},
        ]
        cv_elements = [
            {"bounds": [154, 115, 263, 162]},  # roughly the "Test" contour
            {"bounds": [270, 113, 538, 172]},  # roughly the "description" contour
        ]

        agent = _make_agent()
        result = agent._merge_and_filter(cv_elements, ocr_elements, image_height=1920)

        # Must produce exactly ONE widget for this line, not two — and it
        # must carry the real text, not be left empty.
        container_widgets = [w for w in result if w["type"] == "container"]
        self.assertEqual(len(container_widgets), 1)
        self.assertEqual(container_widgets[0]["text"], "Test description")
        # Bounds should span both original CV contours.
        b = container_widgets[0]["bounds"]
        self.assertEqual(b, [151, 108, 545, 176])
        # cv_bounds must match too — annotate_screenshot() draws using
        # cv_bounds preferentially (tools/observer_tools.py), so if this is
        # left as only the first matching CV fragment, the rendered box only
        # covers one word even though `bounds`/`text` are correctly merged.
        self.assertEqual(container_widgets[0]["cv_bounds"], [151, 108, 545, 176])

    def test_no_empty_duplicate_widget_is_created(self):
        """The specific symptom that was visible in the annotated screenshot:
        a second, textless box left over from the CV box that lost the race
        for the OCR text. After the fix this must not exist at all."""
        ocr_elements = [{"text": "Test description", "bounds": [151, 108, 545, 176]}]
        cv_elements = [
            {"bounds": [154, 115, 263, 162]},
            {"bounds": [270, 113, 538, 172]},
        ]
        agent = _make_agent()
        result = agent._merge_and_filter(cv_elements, ocr_elements, image_height=1920)

        empty_text_widgets = [w for w in result if w["type"] == "container" and not w["text"]]
        self.assertEqual(empty_text_widgets, [])

    def test_cv_box_with_no_ocr_match_keeps_old_behavior(self):
        """An icon-only button (no OCR text nearby) must still produce a
        textless container widget — this is legitimate, not a duplicate."""
        ocr_elements = [{"text": "Continue to the test", "bounds": [280, 1624, 801, 1697]}]
        cv_elements = [
            {"bounds": [280, 1624, 801, 1697]},   # matches the OCR text
            {"bounds": [900, 200, 950, 260]},      # far away, e.g. an icon
        ]
        agent = _make_agent()
        result = agent._merge_and_filter(cv_elements, ocr_elements, image_height=1920)

        container_widgets = [w for w in result if w["type"] == "container"]
        self.assertEqual(len(container_widgets), 2)
        texts = sorted(w["text"] for w in container_widgets)
        self.assertEqual(texts, ["", "Continue to the test"])

    def test_unmatched_ocr_falls_through_to_text_stub(self):
        ocr_elements = [{"text": "Orphan label text", "bounds": [10, 200, 200, 240]}]
        cv_elements = []  # nothing detected nearby
        agent = _make_agent()
        result = agent._merge_and_filter(cv_elements, ocr_elements, image_height=1920)

        stubs = [w for w in result if w["type"] == "text_stub"]
        self.assertEqual(len(stubs), 1)
        self.assertEqual(stubs[0]["text"], "Orphan label text")

    def test_simple_one_to_one_match_unchanged(self):
        """Baseline case that already worked before the fix — must keep
        working identically."""
        ocr_elements = [{"text": "Log In", "bounds": [666, 873, 781, 910]}]
        cv_elements = [{"bounds": [666, 873, 781, 910]}]
        agent = _make_agent()
        result = agent._merge_and_filter(cv_elements, ocr_elements, image_height=1920)

        container_widgets = [w for w in result if w["type"] == "container"]
        self.assertEqual(len(container_widgets), 1)
        self.assertEqual(container_widgets[0]["text"], "Log In")


if __name__ == "__main__":
    unittest.main()
