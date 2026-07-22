# tests/test_explainer.py
import sys
import unittest
from unittest.mock import MagicMock

sys.path.append(".")
from core.uncertainty.explainer import explain_step_uncertainty


def _widget(element_id, raw_dse, clusters, text="", role=""):
    return {
        "element_id": element_id,
        "raw_dse": raw_dse,
        "clusters": clusters,
        "text": text,
        "role": role,
    }


class TestExplainStepUncertainty(unittest.TestCase):
    def test_zero_uncertain_widgets_makes_no_llm_call(self):
        llm = MagicMock()
        widgets = [
            _widget(1, 0.0, [["Button - Login", "Button - Login"]]),
            _widget(2, 0.0, [["Header - Title"]]),
        ]
        result = explain_step_uncertainty(llm, widgets, "Login screen")
        self.assertIsNone(result)
        llm.invoke.assert_not_called()

    def test_empty_widgets_list_makes_no_llm_call(self):
        llm = MagicMock()
        result = explain_step_uncertainty(llm, [], "Login screen")
        self.assertIsNone(result)
        llm.invoke.assert_not_called()

    def test_uncertain_widget_triggers_one_call_and_returns_clean_text(self):
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(
            content="3 of 5 interpretations described it as a share icon, "
                    "2 described it as a text divider."
        )
        widgets = [
            _widget(
                7, 0.65,
                [["Icon Button - Share icon"] * 3, ["Static Text - divider"] * 2],
                text="", role="icon_button",
            ),
        ]
        result = explain_step_uncertainty(llm, widgets, "Notes screen")
        self.assertEqual(llm.invoke.call_count, 1)
        self.assertIn("share icon", result)
        self.assertIn("text divider", result)

    def test_banned_word_triggers_one_retry_then_succeeds(self):
        llm = MagicMock()
        llm.invoke.side_effect = [
            MagicMock(content="The widget was unreliable across samples."),
            MagicMock(content="3 of 5 said A, 2 said B."),
        ]
        widgets = [_widget(7, 0.65, [["A"] * 3, ["B"] * 2])]
        result = explain_step_uncertainty(llm, widgets, "Notes screen")
        self.assertEqual(llm.invoke.call_count, 2)
        self.assertEqual(result, "3 of 5 said A, 2 said B.")

    def test_banned_word_persists_after_retry_returns_none(self):
        llm = MagicMock()
        llm.invoke.side_effect = [
            MagicMock(content="The widget was unreliable."),
            MagicMock(content="Still unreliable across samples."),
        ]
        widgets = [_widget(7, 0.65, [["A"] * 3, ["B"] * 2])]
        result = explain_step_uncertainty(llm, widgets, "Notes screen")
        self.assertEqual(llm.invoke.call_count, 2)
        self.assertIsNone(result)

    def test_llm_exception_returns_none(self):
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("connection reset")
        widgets = [_widget(7, 0.65, [["A"] * 3, ["B"] * 2])]
        result = explain_step_uncertainty(llm, widgets, "Notes screen")
        self.assertIsNone(result)

    def test_exception_on_retry_call_returns_none(self):
        llm = MagicMock()
        llm.invoke.side_effect = [
            MagicMock(content="The widget was unreliable across samples."),
            RuntimeError("connection reset"),
        ]
        widgets = [_widget(7, 0.65, [["A"] * 3, ["B"] * 2])]
        result = explain_step_uncertainty(llm, widgets, "Notes screen")
        self.assertIsNone(result)
        self.assertEqual(llm.invoke.call_count, 2)

    def test_none_llm_returns_none_without_raising(self):
        widgets = [_widget(7, 0.65, [["A"] * 3, ["B"] * 2])]
        result = explain_step_uncertainty(None, widgets, "Notes screen")
        self.assertIsNone(result)

    def test_widgets_missing_text_role_keys_does_not_raise(self):
        llm = MagicMock()
        llm.invoke.return_value = MagicMock(content="3 of 5 said A, 2 said B.")
        widgets = [{"element_id": 7, "raw_dse": 0.65, "clusters": [["A"] * 3, ["B"] * 2]}]
        result = explain_step_uncertainty(llm, widgets, "Notes screen")
        self.assertEqual(result, "3 of 5 said A, 2 said B.")


if __name__ == "__main__":
    unittest.main()
