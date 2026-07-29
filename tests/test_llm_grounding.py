"""Tests for ObserverAgent._detect_widgets_via_llm — the zero-shot VLM
widget-grounding detector that replaced Canny+region+OCR as the default
detection method on 2026-07-29 (OBSERVER_DETECTION_METHOD="llm").

See shared/prompts/observer_prompts.py::GROUNDING_PROMPT for the real
validation numbers (66.7-72.7% recall@IoU0.5 on Screen Annotation ground
truth vs ~35-46% for the classical pipeline) and
Dokumen Kepake/memory/thesis_vlm_grounding_alternative.md for full context.
These tests verify wiring and the box_2d -> pixel bounds conversion, not
detection accuracy — that was validated manually against real ground truth
data, which isn't available in this sandbox.
"""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# Stub easyocr before importing anything that imports tools.observer_tools
# (heavy torch-backed import, irrelevant to the LLM grounding path).
_easyocr_stub = types.ModuleType("easyocr")
_easyocr_stub.Reader = MagicMock(return_value=MagicMock())
sys.modules.setdefault("easyocr", _easyocr_stub)

from agents.observer_agent import ObserverAgent, _GroundedWidget, _GroundingResult  # noqa: E402


def _make_agent(llm):
    return ObserverAgent(llm=llm, tools=[MagicMock()] * 6, memory=None, logger=None, monitor=None)


class TestDetectWidgetsViaLLM(unittest.TestCase):
    def setUp(self):
        # A real temp file so open(raw_path, "rb") in the method under test
        # succeeds — content doesn't matter, only that it's readable bytes.
        import tempfile
        self.tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        self.tmp.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        self.tmp.close()
        self.addCleanup(lambda: __import__("os").unlink(self.tmp.name))

    def test_converts_normalized_box_2d_to_pixel_bounds(self):
        """The core coordinate conversion: box_2d is [ymin,xmin,ymax,xmax]
        normalized 0-1000, must convert to pixel [x1,y1,x2,y2] against the
        REAL image dimensions passed in (not whatever size was sent to the
        model — box_2d is resolution-independent by construction)."""
        fake_result = _GroundingResult(widgets=[
            _GroundedWidget(label="Log In", type="BUTTON", box_2d=[883, 669, 904, 776]),
        ])
        llm = MagicMock()
        llm.with_structured_output.return_value.invoke.return_value = fake_result

        agent = _make_agent(llm)
        widgets = agent._detect_widgets_via_llm(self.tmp.name, image_width=540, image_height=960)

        self.assertEqual(len(widgets), 1)
        w = widgets[0]
        # x1 = 669/1000*540 = 361.26 -> 361, x2 = 776/1000*540 = 419.04 -> 419
        # y1 = 883/1000*960 = 847.68 -> 848, y2 = 904/1000*960 = 867.84 -> 868
        self.assertEqual(w["bounds"], [361, 848, 419, 868])
        self.assertEqual(w["text"], "Log In")
        self.assertEqual(w["type"], "container")
        self.assertEqual(w["class"], "Interactive")
        self.assertEqual(w["llm_type"], "BUTTON")
        self.assertEqual(w["id"], 1)

    def test_text_type_maps_to_text_stub(self):
        """TEXT elements must map to the same type/class the classical
        pipeline used for non-actionable text, so downstream code (decider,
        annotate_screenshot coloring) doesn't need to special-case the
        detection source."""
        fake_result = _GroundingResult(widgets=[
            _GroundedWidget(label="Already have an account?", type="TEXT",
                            box_2d=[883, 223, 904, 660]),
        ])
        llm = MagicMock()
        llm.with_structured_output.return_value.invoke.return_value = fake_result

        agent = _make_agent(llm)
        widgets = agent._detect_widgets_via_llm(self.tmp.name, 540, 960)

        self.assertEqual(widgets[0]["type"], "text_stub")
        self.assertEqual(widgets[0]["class"], "StaticText")

    def test_same_line_different_actionability_stays_split(self):
        """The exact real case this replaced the classical pipeline for:
        'Already have an account? Log In' must come back as TWO widgets,
        not merged into one — the classical Canny+OCR pipeline always
        merged this and had no safe geometric fix (see GROUNDING_PROMPT
        module docstring / thesis_vlm_grounding_alternative.md)."""
        fake_result = _GroundingResult(widgets=[
            _GroundedWidget(label="Already have an account?", type="TEXT",
                            box_2d=[883, 223, 904, 660]),
            _GroundedWidget(label="Log In", type="BUTTON", box_2d=[883, 669, 904, 776]),
        ])
        llm = MagicMock()
        llm.with_structured_output.return_value.invoke.return_value = fake_result

        agent = _make_agent(llm)
        widgets = agent._detect_widgets_via_llm(self.tmp.name, 540, 960)

        self.assertEqual(len(widgets), 2)
        texts = sorted(w["text"] for w in widgets)
        self.assertEqual(texts, ["Already have an account?", "Log In"])

    def test_malformed_box_2d_is_skipped_not_crashed(self):
        """A box_2d that isn't exactly 4 ints (model misbehavior despite the
        structured-output schema) must be dropped, not raise and take down
        the whole detection call for one bad widget."""
        good = _GroundedWidget(label="OK", type="BUTTON", box_2d=[100, 100, 200, 200])
        bad = _GroundedWidget.model_construct(label="Bad", type="BUTTON", box_2d=[1, 2, 3])
        fake_result = _GroundingResult.model_construct(widgets=[bad, good])
        llm = MagicMock()
        llm.with_structured_output.return_value.invoke.return_value = fake_result

        agent = _make_agent(llm)
        widgets = agent._detect_widgets_via_llm(self.tmp.name, 540, 960)

        self.assertEqual(len(widgets), 1)
        self.assertEqual(widgets[0]["text"], "OK")

    def test_swapped_min_max_coordinates_are_normalized(self):
        """Defensive handling: if the model returns ymin>ymax or xmin>xmax,
        bounds must still come out as a valid, correctly-ordered box rather
        than an inverted/negative-area rectangle that breaks downstream
        rendering and IoU math."""
        fake_result = _GroundingResult(widgets=[
            _GroundedWidget(label="Weird", type="BUTTON", box_2d=[500, 800, 200, 400]),
        ])
        llm = MagicMock()
        llm.with_structured_output.return_value.invoke.return_value = fake_result

        agent = _make_agent(llm)
        widgets = agent._detect_widgets_via_llm(self.tmp.name, 1000, 1000)

        x1, y1, x2, y2 = widgets[0]["bounds"]
        self.assertLess(x1, x2)
        self.assertLess(y1, y2)

    def test_zero_area_box_is_dropped(self):
        fake_result = _GroundingResult(widgets=[
            _GroundedWidget(label="Degenerate", type="BUTTON", box_2d=[500, 500, 500, 600]),
        ])
        llm = MagicMock()
        llm.with_structured_output.return_value.invoke.return_value = fake_result

        agent = _make_agent(llm)
        widgets = agent._detect_widgets_via_llm(self.tmp.name, 1000, 1000)
        self.assertEqual(widgets, [])

    def test_retries_on_rate_limit_then_succeeds(self):
        fake_result = _GroundingResult(widgets=[
            _GroundedWidget(label="OK", type="BUTTON", box_2d=[100, 100, 200, 200]),
        ])
        llm = MagicMock()
        structured = llm.with_structured_output.return_value
        structured.invoke.side_effect = [Exception("429 rate limit exceeded"), fake_result]

        agent = _make_agent(llm)
        with patch("agents.observer_agent.time.sleep"):
            widgets = agent._detect_widgets_via_llm(self.tmp.name, 540, 960)

        self.assertEqual(len(widgets), 1)
        self.assertEqual(structured.invoke.call_count, 2)

    def test_non_retryable_error_raises(self):
        llm = MagicMock()
        llm.with_structured_output.return_value.invoke.side_effect = ValueError("bad schema")

        agent = _make_agent(llm)
        with self.assertRaises(ValueError):
            agent._detect_widgets_via_llm(self.tmp.name, 540, 960)


class TestAnalyzeDetectionMethodSwitch(unittest.TestCase):
    """Verifies ObserverAgent.analyze() actually branches on
    config.OBSERVER_DETECTION_METHOD and falls back to cv_ocr when the LLM
    grounding call fails, without going through the full memory/XML/semantic
    pipeline (memory=None sidesteps an unrelated pre-existing test-fixture
    bug in the memory-retrieval branch, see test_observer_agent.py)."""

    def setUp(self):
        import tempfile
        self.step_dir = tempfile.mkdtemp()
        # _detect_widgets_via_llm reads real bytes off disk (matches what
        # was actually validated: raw screenshot bytes, unresized), and
        # analyze() also cv2.imread's this same path — needs to be a real,
        # decodable image, not just any bytes.
        import numpy as np
        import cv2
        img = np.zeros((960, 540, 3), dtype="uint8")
        cv2.imwrite(f"{self.step_dir}/raw.png", img)

    def _make_state(self):
        return {"current_step": 1, "step_dir": self.step_dir}

    def _make_tools(self):
        take_screenshot = MagicMock()
        take_screenshot.invoke = MagicMock(return_value="raw.png")
        ocr_extract_text = MagicMock()
        ocr_extract_text.invoke = MagicMock(return_value="[]")
        detect_visual_elements = MagicMock()
        detect_visual_elements.invoke = MagicMock(return_value="[]")
        annotate_screenshot = MagicMock()
        annotate_screenshot.invoke = MagicMock(return_value="annotated.png")
        check_keyboard_state = MagicMock()
        check_keyboard_state.invoke = MagicMock(return_value='{"is_shown": false}')
        dump_hierarchy = MagicMock()
        dump_hierarchy.invoke = MagicMock(return_value="")  # no XML -> skip refinement
        return [take_screenshot, ocr_extract_text, detect_visual_elements,
                annotate_screenshot, check_keyboard_state, dump_hierarchy]

    def test_llm_grounding_used_when_configured_and_successful(self):
        from shared import config
        tools = self._make_tools()
        llm = MagicMock()
        fake_result = _GroundingResult(widgets=[
            _GroundedWidget(label="OK", type="BUTTON", box_2d=[100, 100, 200, 200]),
        ])
        llm.with_structured_output.return_value.invoke.return_value = fake_result
        llm.invoke.return_value = MagicMock(content="SEMANTIC_MAP:\n[1]: Button - OK\nSUMMARY: ok")

        agent = ObserverAgent(llm=llm, tools=tools, memory=None, logger=None, monitor=None)

        orig = config.OBSERVER_DETECTION_METHOD
        config.OBSERVER_DETECTION_METHOD = "llm"
        try:
            agent.analyze(self._make_state())
        finally:
            config.OBSERVER_DETECTION_METHOD = orig

        tools[2].invoke.assert_not_called()  # detect_visual_elements (cv_ocr path) unused
        tools[1].invoke.assert_not_called()  # ocr_extract_text (cv_ocr path) unused

    def test_falls_back_to_cv_ocr_when_llm_grounding_fails(self):
        from shared import config
        tools = self._make_tools()
        llm = MagicMock()
        llm.with_structured_output.return_value.invoke.side_effect = RuntimeError("API down")
        llm.invoke.return_value = MagicMock(content="SEMANTIC_MAP:\nSUMMARY: ok")

        agent = ObserverAgent(llm=llm, tools=tools, memory=None, logger=None, monitor=None)

        orig = config.OBSERVER_DETECTION_METHOD
        config.OBSERVER_DETECTION_METHOD = "llm"
        try:
            agent.analyze(self._make_state())
        finally:
            config.OBSERVER_DETECTION_METHOD = orig

        # Fallback must have actually run the classical pipeline's tools.
        tools[2].invoke.assert_called_once()  # detect_visual_elements
        tools[1].invoke.assert_called_once()  # ocr_extract_text


if __name__ == "__main__":
    unittest.main()
