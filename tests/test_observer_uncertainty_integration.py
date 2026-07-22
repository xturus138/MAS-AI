import sys
import unittest

sys.path.append(".")
from core.uncertainty.request_builder import ObserverSemanticRequestBuilder
from agents.observer_agent import ObserverAgent


class TestObserverUsesSharedBuilder(unittest.TestCase):
    def test_observer_exposes_shared_builder_factory(self):
        # ObserverAgent must build messages via the shared builder class,
        # not inline — proving one source of truth with the standalone runner.
        self.assertTrue(hasattr(ObserverAgent, "_build_semantic_request_builder"))

    def test_builder_factory_returns_builder(self):
        builder = ObserverAgent._build_semantic_request_builder()
        self.assertIsInstance(builder, ObserverSemanticRequestBuilder)
        self.assertEqual(len(builder.prompt_hash), 64)


if __name__ == "__main__":
    unittest.main()
