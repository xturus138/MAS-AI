import sys
import unittest

sys.path.append(".")
from core.uncertainty.clusterer import (
    EntailmentClusterer,
    WidgetContext,
    SemanticClusterer,
)


class _StubLLM:
    """Returns queued labels in order, one per invoke() call."""
    def __init__(self, labels):
        self._labels = list(labels)
        self.calls = 0

    def invoke(self, messages, **kwargs):
        self.calls += 1
        label = self._labels.pop(0) if self._labels else "neutral"

        class _R:
            content = label
        return _R()


CTX = WidgetContext(element_id=1, text="Login", role="button", screen_desc="Login screen")


class TestEntailmentClusterer(unittest.TestCase):
    def test_bidirectional_required_to_merge(self):
        # A vs B: A->B entailment but B->A neutral => must NOT merge (2 clusters)
        llm = _StubLLM(["entailment", "neutral"])
        c = EntailmentClusterer(llm)
        result = c.cluster(["Primary Button - Login", "Text Link - Login"], CTX)
        self.assertEqual(len(result.clusters), 2)
        self.assertEqual(sorted(result.counts, reverse=True), [1, 1])

    def test_mutual_entailment_merges(self):
        # A vs B: both directions entailment => merge (1 cluster)
        llm = _StubLLM(["entailment", "entailment"])
        c = EntailmentClusterer(llm)
        result = c.cluster(["Primary Button - Login", "Button - Login"], CTX)
        self.assertEqual(len(result.clusters), 1)
        self.assertEqual(result.counts, [2])

    def test_single_response_single_cluster_no_llm_call(self):
        llm = _StubLLM([])
        c = EntailmentClusterer(llm)
        result = c.cluster(["Only One"], CTX)
        self.assertEqual(result.counts, [1])
        self.assertEqual(llm.calls, 0)

    def test_pairwise_decisions_recorded(self):
        llm = _StubLLM(["entailment", "entailment"])
        c = EntailmentClusterer(llm)
        result = c.cluster(["A", "B"], CTX)
        self.assertTrue(len(result.pairwise) >= 1)
        self.assertEqual(result.pairwise[0].context["element_id"], 1)

    def test_is_subclass(self):
        self.assertTrue(issubclass(EntailmentClusterer, SemanticClusterer))


if __name__ == "__main__":
    unittest.main()
