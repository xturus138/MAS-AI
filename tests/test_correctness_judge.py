"""Tests for core/calibration/correctness_judge.py."""
import unittest
from unittest.mock import MagicMock

from core.calibration.correctness_judge import CorrectnessJudge


class _StubLLM:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.last_messages = None

    def invoke(self, messages, **kwargs):
        self.last_messages = messages
        return MagicMock(content=self.response_text)


class TestCorrectnessJudge(unittest.TestCase):
    def test_yes_response_is_correct(self):
        llm = _StubLLM("yes")
        judge = CorrectnessJudge(llm)
        result = judge.judge("Login button", "A blue button labeled Login", "Login screen")
        self.assertEqual(result.label, "yes")
        self.assertTrue(result.is_correct)

    def test_no_response_is_incorrect(self):
        llm = _StubLLM("no")
        judge = CorrectnessJudge(llm)
        result = judge.judge("Settings icon", "A blue button labeled Login", "Login screen")
        self.assertEqual(result.label, "no")
        self.assertFalse(result.is_correct)

    def test_case_insensitive_and_extra_text_after_first_line(self):
        llm = _StubLLM("Yes\nBecause both describe the same login action.")
        judge = CorrectnessJudge(llm)
        result = judge.judge("Login button", "A blue button labeled Login", "Login screen")
        self.assertEqual(result.label, "yes")

    def test_ambiguous_response_never_fabricates_a_verdict(self):
        llm = _StubLLM("yes and no depending on interpretation")
        judge = CorrectnessJudge(llm)
        result = judge.judge("X", "Y", "screen")
        self.assertEqual(result.label, "unparseable")
        self.assertFalse(result.is_correct)

    def test_empty_response_is_unparseable(self):
        llm = _StubLLM("")
        judge = CorrectnessJudge(llm)
        result = judge.judge("X", "Y", "screen")
        self.assertEqual(result.label, "unparseable")

    def test_prompt_includes_predicted_and_reference_text(self):
        llm = _StubLLM("yes")
        judge = CorrectnessJudge(llm)
        judge.judge("Login button", "A blue button labeled Login", "Login screen")
        human_msg = llm.last_messages[1][1]
        self.assertIn("Login button", human_msg)
        self.assertIn("A blue button labeled Login", human_msg)
        self.assertIn("Login screen", human_msg)

    def test_result_carries_raw_response_for_auditing(self):
        llm = _StubLLM("no, the icon type is different")
        judge = CorrectnessJudge(llm)
        result = judge.judge("X", "Y", "screen")
        self.assertEqual(result.raw_response, "no, the icon type is different")


if __name__ == "__main__":
    unittest.main()
