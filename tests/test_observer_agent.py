import sys
import os
import json
import tempfile
import unittest
from unittest.mock import MagicMock

sys.path.append(".")

from shared import config
config.OBSERVER_MODE = "xml_first"

from core.models.state import AgentState
from agents.observer_agent import ObserverAgent


class TestObserverAgentVisionXMLRefine(unittest.TestCase):
    def setUp(self):
        self._original_detection_method = config.OBSERVER_DETECTION_METHOD
        config.OBSERVER_DETECTION_METHOD = "cv_ocr"

        self.take_screenshot = MagicMock()
        self.ocr_extract_text = MagicMock()
        self.detect_visual_elements = MagicMock()
        self.annotate_screenshot = MagicMock()
        self.check_keyboard_state = MagicMock()

        self.take_screenshot.invoke = MagicMock(return_value="raw.png")
        self.ocr_extract_text.invoke = MagicMock(return_value="[]")
        self.detect_visual_elements.invoke = MagicMock(return_value="[]")
        self.annotate_screenshot.invoke = MagicMock(return_value="annotated.png")
        self.check_keyboard_state.invoke = MagicMock(return_value='{"is_shown": false}')

        self.sample_xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
        <hierarchy rotation="0">
            <node index="0" text="" class="android.widget.FrameLayout" bounds="[0,0][1080,2400]">
                <node index="0" text="Submit" class="android.widget.Button" bounds="[100,200][300,300]" clickable="true" />
            </node>
        </hierarchy>
        """
        self.dump_hierarchy = MagicMock()
        self.dump_hierarchy.invoke = MagicMock(return_value=self.sample_xml)

        self.tools = [
            self.take_screenshot,
            self.ocr_extract_text,
            self.detect_visual_elements,
            self.annotate_screenshot,
            self.check_keyboard_state,
            self.dump_hierarchy,
        ]

        self.llm = MagicMock()
        self.llm.invoke.return_value = MagicMock(content="SEMANTIC_MAP:\n[1]: Button - Submit\nSUMMARY: A screen with a submit button.")

        self.memory = MagicMock()
        self.memory.retrieve.return_value = "Mocked Memory Context"
        self.memory.retrieve_with_labels.return_value = {
            "semantic": "Mocked semantic context",
            "vault": "Mocked knowledge context",
        }
        self.memory.core.get.return_value = "Mocked Field"
        self.memory.episodic.last_by_actor.return_value = None

        self.logger = MagicMock()

        self.agent = ObserverAgent(self.llm, self.tools, memory=self.memory, logger=self.logger)
        self._temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        config.OBSERVER_DETECTION_METHOD = self._original_detection_method
        self._temp_dir.cleanup()

    def _make_step_dir(self, name: str) -> str:
        import cv2, numpy as np
        path = os.path.join(self._temp_dir.name, name)
        os.makedirs(path, exist_ok=True)
        blank = np.zeros((2400, 1080, 3), np.uint8)
        cv2.imwrite(os.path.join(path, "raw.png"), blank)
        return path


    def test_vision_xml_refinement_appends_missed_actionable(self):
        """Vision finds nothing, XML has actionable button → appended as widget."""
        step_dir = self._make_step_dir("test_refine_append")
        state: AgentState = {"current_step": 1, "step_dir": step_dir, "observer_analysis": "", "widgets": []}

        result = self.agent.analyze(state)

        self.assertIn("xml_refined", result["observation_source"])
        self.assertTrue(len(result["widgets"]) > 0)
        self.assertEqual(result["widgets"][0]["source"], "xml")
        self.assertEqual(result["widgets"][0]["xml_label"], "Submit")

        self.take_screenshot.invoke.assert_called_once()
        self.ocr_extract_text.invoke.assert_called_once()
        self.detect_visual_elements.invoke.assert_called_once()
        self.dump_hierarchy.invoke.assert_called_once()
        self.annotate_screenshot.invoke.assert_called_once()

    def test_vision_only_when_xml_fails(self):
        """XML dump fails → vision-only output, no refinement."""
        self.dump_hierarchy.invoke.return_value = "<error>no device</error>"
        self.ocr_extract_text.invoke.return_value = json.dumps([
            {"text": "Cancel", "bounds": [50, 200, 200, 260], "confidence": 0.9}
        ])
        self.detect_visual_elements.invoke.return_value = json.dumps([
            {"bounds": [40, 190, 210, 270]}
        ])

        step_dir = self._make_step_dir("test_xml_fail")
        state: AgentState = {"current_step": 1, "step_dir": step_dir, "observer_analysis": "", "widgets": []}

        result = self.agent.analyze(state)

        self.assertEqual(result["observation_source"], "vision")
        self.assertEqual(result["confidence_score"], 1.0)
        self.assertTrue(len(result["widgets"]) > 0)

        self.take_screenshot.invoke.assert_called_once()
        self.ocr_extract_text.invoke.assert_called_once()
        self.detect_visual_elements.invoke.assert_called_once()
        self.annotate_screenshot.invoke.assert_called_once()

    def test_xml_refines_vision_bounds(self):
        """Vision has approximate coords, XML has precise → bounds replaced."""
        self.ocr_extract_text.invoke.return_value = json.dumps([
            {"text": "Submit", "bounds": [90, 190, 310, 310], "confidence": 0.9}
        ])
        self.detect_visual_elements.invoke.return_value = json.dumps([
            {"bounds": [85, 185, 315, 315]}
        ])

        step_dir = self._make_step_dir("test_bounds_refine")
        state: AgentState = {"current_step": 1, "step_dir": step_dir, "observer_analysis": "", "widgets": []}

        result = self.agent.analyze(state)

        self.assertIn("xml_refined", result["observation_source"])
        self.assertEqual(len(result["widgets"]), 1)
        self.assertEqual(result["widgets"][0]["source"], "xml")
        self.assertEqual(result["widgets"][0]["bounds"], [100, 200, 300, 300])

    def test_xml_adds_missed_actionable(self):
        """Vision detects one element, XML has extra actionable → appended."""
        self.ocr_extract_text.invoke.return_value = json.dumps([
            {"text": "Search", "bounds": [50, 100, 400, 150], "confidence": 0.9}
        ])
        self.detect_visual_elements.invoke.return_value = json.dumps([
            {"bounds": [40, 95, 410, 155]}
        ])
        self.dump_hierarchy.invoke.return_value = """<?xml version='1.0' encoding='UTF-8'?>
        <hierarchy rotation="0">
            <node bounds="[0,0][1080,2400]">
                <node index="0" text="Search" class="android.widget.EditText" bounds="[50,100][400,150]" clickable="true" focusable="true" />
                <node index="1" text="Login" class="android.widget.Button" bounds="[500,600][700,700]" clickable="true" />
            </node>
        </hierarchy>
        """

        step_dir = self._make_step_dir("test_extra_actionable")
        state: AgentState = {"current_step": 1, "step_dir": step_dir, "observer_analysis": "", "widgets": []}

        result = self.agent.analyze(state)

        self.assertIn("xml_refined", result["observation_source"])
        self.assertEqual(len(result["widgets"]), 2)

        self.assertEqual(result["widgets"][0]["source"], "xml")
        self.assertEqual(result["widgets"][0]["bounds"], [50, 100, 400, 150])

        self.assertEqual(result["widgets"][1]["source"], "xml")
        self.assertEqual(result["widgets"][1]["xml_label"], "Login")
        self.assertEqual(result["widgets"][1]["bounds"], [500, 600, 700, 700])

if __name__ == "__main__":
    unittest.main()
