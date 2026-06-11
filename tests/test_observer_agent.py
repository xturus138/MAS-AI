import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.append(".")

# Mock config
from shared import config
config.OBSERVER_MODE = "xml_first"
config.FAST_VISION_MODE = True

from core.models.state import AgentState
from agents.observer_agent import ObserverAgent

class TestObserverAgentXML(unittest.TestCase):
    def setUp(self):
        # Tools: [take_screenshot, ocr_extract_text, detect_visual_elements, annotate_screenshot, check_keyboard_state, dump_hierarchy]
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
            self.dump_hierarchy
        ]

        self.llm = MagicMock()
        self.llm.invoke.return_value = MagicMock(content="Mocked LLM Analysis")

        self.memory = MagicMock()
        self.memory.retrieve.return_value = "Mocked Memory Context"
        self.memory.core.get.return_value = "Mocked Field"
        self.memory.episodic.last_by_actor.return_value = None

        self.logger = MagicMock()

        self.agent = ObserverAgent(self.llm, self.tools, memory=self.memory, logger=self.logger)

    def test_xml_first_path(self):
        # Create temp dir for outputs
        step_dir = "test_step_dir"
        os.makedirs(step_dir, exist_ok=True)

        state: AgentState = {
            "current_step": 1,
            "step_dir": step_dir,
            "observer_analysis": "",
            "widgets": []
        }

        # We need mock raw.png to satisfy OpenCV imread in annotation
        import cv2
        import numpy as np
        blank_image = np.zeros((2400, 1080, 3), np.uint8)
        cv2.imwrite(os.path.join(step_dir, "raw.png"), blank_image)

        result = self.agent.analyze(state)

        # Assertions
        self.assertEqual(result["observation_source"], "xml")
        self.assertEqual(result["confidence_score"], 1.0)
        self.assertTrue(len(result["widgets"]) > 0)
        self.assertEqual(result["widgets"][0]["label"], "Submit")
        self.assertEqual(result["widgets"][0]["role"], "button")

        # Verify dump_hierarchy tool called
        self.dump_hierarchy.invoke.assert_called_once()

        # Clean up
        import shutil
        shutil.rmtree(step_dir)

    def test_xml_fallback_to_vision(self):
        # Test low confidence triggers fallback
        # Valid XML syntax but empty node list -> confidence 0.0, "No valid elements parsed after filtering"
        self.dump_hierarchy.invoke.return_value = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
        <hierarchy rotation="0">
            <node index="0" bounds="[0,0][1080,2400]">
                <!-- Empty or unparsable contents -->
            </node>
        </hierarchy>
        """

        step_dir = "test_step_dir_fallback"
        os.makedirs(step_dir, exist_ok=True)

        # Mock OCR output
        self.ocr_extract_text.invoke.return_value = '[{"text": "Submit Button", "bounds": [100, 200, 300, 300], "confidence": 0.9}]'
        self.detect_visual_elements.invoke.return_value = '[{"bounds": [100, 200, 300, 300]}]'

        state: AgentState = {
            "current_step": 1,
            "step_dir": step_dir,
            "observer_analysis": "",
            "widgets": []
        }

        import cv2
        import numpy as np
        blank_image = np.zeros((2400, 1080, 3), np.uint8)
        cv2.imwrite(os.path.join(step_dir, "raw.png"), blank_image)

        result = self.agent.analyze(state)

        # Assertions
        self.assertEqual(result["observation_source"], "hybrid")
        self.assertTrue(result["confidence_score"] < 0.5)
        self.assertEqual(result["fallback_reason"], "No valid elements parsed after filtering")
        self.assertTrue(len(result["widgets"]) > 0)

        # Verify vision tools called
        self.take_screenshot.invoke.assert_called()
        self.ocr_extract_text.invoke.assert_called_once()
        self.detect_visual_elements.invoke.assert_called_once()

        import shutil
        shutil.rmtree(step_dir)

if __name__ == "__main__":
    unittest.main()
