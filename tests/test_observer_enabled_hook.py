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

    def test_prints_no_disagreement_line_when_all_widgets_agree(self):
        import io, contextlib
        from unittest.mock import MagicMock

        class _StubBuilder:
            prompt_hash = "x"
            def build(self, **kwargs):
                return [("system", "s"), ("human", "h")]

        class _StubLLM:
            provider = "stub"
            model_name = "m"
            def invoke(self, messages, **kwargs):
                # EntailmentClusterer issues real pairwise judge calls even
                # when the raw sample text is identical (it never
                # short-circuits on exact string equality) — a judge-unaware
                # stub returning the same canned text for every call causes
                # _parse_label() to default to "neutral", so responses never
                # merge and raw_dse ends up > 0, defeating "all widgets
                # agree". Detect judge-shaped calls by system-prompt identity
                # (same technique test 2 below uses for the explainer call)
                # and answer "entailment" so identical samples merge into one
                # cluster, producing a genuine raw_dse == 0 result.
                from shared.prompts.entailment_prompts import ENTAILMENT_SYSTEM_PROMPT
                if messages and messages[0][1] == ENTAILMENT_SYSTEM_PROMPT:
                    return MagicMock(content="entailment")
                return MagicMock(content="[1]: Button - Login")

        obs = ObserverAgent.__new__(ObserverAgent)
        obs.llm = _StubLLM()
        obs.logger = None

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            obs._maybe_run_uncertainty(
                enabled=True, builder=_StubBuilder(), scenario_desc="s",
                navigation_context="n", elements_json="[]", img_b64="x",
                widgets=[{"id": 1, "text": "Login", "xml_role": "button"}],
                step_dir=__import__("tempfile").mkdtemp(),
            )
        output = buf.getvalue()
        self.assertIn("[Uncertainty]", output)
        self.assertIn("No disagreement detected", output)

    def test_prints_nothing_extra_when_disagreement_exists_but_explainer_fails(self):
        # manifest["explanation"] is None (explainer LLM call failed) AND some
        # widget has raw_dse > 0 -> spec 3.8 says print nothing extra (skip
        # silently), not the "No disagreement" line, since disagreement DID exist.
        import io, contextlib
        from unittest.mock import MagicMock

        class _StubBuilder:
            prompt_hash = "x"
            def build(self, **kwargs):
                return [("system", "s"), ("human", "h")]

        call_count = {"n": 0}

        class _FlakyLLM:
            provider = "stub"
            model_name = "m"
            def invoke(self, messages, **kwargs):
                call_count["n"] += 1
                # First 5 calls: DSE sampling (varying responses to force disagreement).
                if call_count["n"] <= 5:
                    text = "[1]: Primary Button - Login" if call_count["n"] <= 3 else "[1]: Text Link - Login"
                    return MagicMock(content=text)
                # Entailment judge calls and the explainer call itself: raise to
                # force the explainer path to fail (explanation stays None) while
                # DSE clustering still needs the judge — simplest way to guarantee
                # explanation=None without mocking the clusterer separately is to
                # let the real EntailmentClusterer's judge calls also go through
                # this LLM; they call invoke() with a different message shape but
                # this stub does not branch on shape, so raising here would break
                # clustering too. Instead: return a neutral judge label so
                # clustering completes (producing 2 clusters -> raw_dse > 0), and
                # only the FINAL explainer call (recognizable as the last call)
                # raises. Since call order is: 5 samples, then judge calls, then
                # the explainer call last, raise unconditionally after sample
                # exhaustion is wrong. Use a simpler approach: raise on any call
                # whose messages contain the explainer system prompt text.
                from shared.prompts.uncertainty_explainer_prompts import EXPLAINER_SYSTEM_PROMPT
                if messages and messages[0][1] == EXPLAINER_SYSTEM_PROMPT:
                    raise RuntimeError("explainer call failed")
                return MagicMock(content="neutral")

        obs = ObserverAgent.__new__(ObserverAgent)
        obs.llm = _FlakyLLM()
        obs.logger = None

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            obs._maybe_run_uncertainty(
                enabled=True, builder=_StubBuilder(), scenario_desc="s",
                navigation_context="n", elements_json="[]", img_b64="x",
                widgets=[{"id": 1, "text": "Login", "xml_role": "button"}],
                step_dir=__import__("tempfile").mkdtemp(),
            )
        output = buf.getvalue()
        self.assertNotIn("[Uncertainty]", output)


if __name__ == "__main__":
    unittest.main()
