import sys
import unittest

sys.path.append(".")
from agents.observer_agent import ObserverAgent


class TestEnabledHook(unittest.TestCase):
    def test_run_uncertainty_disabled_returns_empty(self):
        # When disabled, the helper must return "" and make no LLM calls.
        class _LLM:
            def invoke(self, *a, **k):
                raise AssertionError("LLM must not be called when disabled")
        obs = ObserverAgent.__new__(ObserverAgent)
        obs.llm = _LLM()
        result = obs._maybe_run_uncertainty(
            enabled=False, builder=None, scenario_desc="s",
            navigation_context="n", elements_json="[]", img_b64="x",
            widgets=[], step_dir="/tmp/nope",
        )
        self.assertEqual(result, "")

    def test_maybe_run_uncertainty_exists(self):
        self.assertTrue(hasattr(ObserverAgent, "_maybe_run_uncertainty"))


if __name__ == "__main__":
    unittest.main()
