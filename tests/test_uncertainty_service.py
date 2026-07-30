import sys
import os
import json
import tempfile
import unittest

sys.path.append(".")
from core.uncertainty.service import ObserverUncertaintyService, TemperatureRejectedError
from core.uncertainty.config import UncertaintyConfig
from core.uncertainty.clusterer import SemanticClusterer, ClusterResult


class _ExactMatchClusterer(SemanticClusterer):
    """Deterministic test helper: clusters by exact string equality (NOT the research path)."""
    def cluster(self, responses, context):
        buckets = {}
        order = []
        for r in responses:
            if r not in buckets:
                buckets[r] = 0
                order.append(r)
            buckets[r] += 1
        clusters = [[k] * buckets[k] for k in order]
        return ClusterResult(clusters=clusters, counts=[buckets[k] for k in order], pairwise=[])


def _cfg(samples=5):
    return UncertaintyConfig(enabled=True, samples=samples, temperature=1.0,
                             provider="stub", model="m", judge_model="m")


WIDGETS = [{"id": 1, "text": "Login", "xml_role": "button"}]


class TestService(unittest.TestCase):
    def test_measure_from_samples_single_cluster_zero(self):
        svc = ObserverUncertaintyService(llm=None, clusterer=_ExactMatchClusterer(),
                                         cfg=_cfg(), prompt_hash="deadbeef")
        samples = ["[1]: Primary Button - Login"] * 5
        with tempfile.TemporaryDirectory() as d:
            manifest = svc.measure_from_samples(samples, WIDGETS, "Login screen", d)
        w = manifest["widgets"][0]
        self.assertAlmostEqual(w["raw_dse"], 0.0, places=6)
        self.assertEqual(w["measurement_status"], "ok")
        self.assertIsNone(w["threshold"])
        self.assertEqual(w["calibration_status"], "not_calibrated")

    def test_measure_from_samples_three_two(self):
        svc = ObserverUncertaintyService(llm=None, clusterer=_ExactMatchClusterer(),
                                         cfg=_cfg(), prompt_hash="deadbeef")
        samples = (["[1]: Primary Button - Login"] * 3) + (["[1]: Text Link - Login"] * 2)
        with tempfile.TemporaryDirectory() as d:
            manifest = svc.measure_from_samples(samples, WIDGETS, "Login screen", d)
        w = manifest["widgets"][0]
        self.assertAlmostEqual(w["raw_dse"], 0.6730116670, places=6)

    def test_insufficient_samples_status(self):
        svc = ObserverUncertaintyService(llm=None, clusterer=_ExactMatchClusterer(),
                                         cfg=_cfg(samples=1), prompt_hash="x")
        with tempfile.TemporaryDirectory() as d:
            manifest = svc.measure_from_samples(["[1]: Button - Login"], WIDGETS, "s", d)
        w = manifest["widgets"][0]
        self.assertEqual(w["raw_dse"], 0.0)
        self.assertEqual(w["measurement_status"], "insufficient_samples")

    def test_partial_failure_uses_effective_m(self):
        # 3 good + 2 unparseable (blank) -> effective_M = 3, single cluster -> 0.0 but status ok
        svc = ObserverUncertaintyService(llm=None, clusterer=_ExactMatchClusterer(),
                                         cfg=_cfg(), prompt_hash="x")
        samples = (["[1]: Button - Login"] * 3) + ["garbage no id", "also garbage"]
        with tempfile.TemporaryDirectory() as d:
            manifest = svc.measure_from_samples(samples, WIDGETS, "s", d)
        w = manifest["widgets"][0]
        self.assertEqual(w["effective_sample_count"], 3)
        self.assertEqual(w["measurement_status"], "ok")

    def test_manifest_has_no_threshold_decision(self):
        svc = ObserverUncertaintyService(llm=None, clusterer=_ExactMatchClusterer(),
                                         cfg=_cfg(), prompt_hash="x")
        with tempfile.TemporaryDirectory() as d:
            manifest = svc.measure_from_samples(["[1]: Button - Login"] * 5, WIDGETS, "s", d)
        self.assertIsNone(manifest["threshold"])
        self.assertEqual(manifest["calibration_status"], "not_calibrated")
        self.assertEqual(manifest["temperature_application"], "requested_not_verified")
        self.assertEqual(manifest["temperature_status"], "provisional_not_evaluated")
        # Exclude the artifact path, whose literal dir name "uncertainty" contains
        # the substring "certain"; the ban targets decision words in measurement data.
        scanned = {k: v for k, v in manifest.items() if k != "uncertainty_dir"}
        blob = json.dumps(scanned).lower()
        for banned in ("accepted", "rejected", '"pass"', '"fail"', "certain"):
            self.assertNotIn(banned, blob)

    def test_sample_raises_on_temperature_rejection(self):
        class _RejectLLM:
            provider = "stubprovider"
            def invoke(self, messages, **kwargs):
                raise ValueError("Unsupported parameter: 'temperature' is not supported")
        svc = ObserverUncertaintyService(llm=_RejectLLM(), clusterer=_ExactMatchClusterer(),
                                         cfg=_cfg(), prompt_hash="x")
        with self.assertRaises(TemperatureRejectedError):
            svc.sample([("system", "x"), ("human", "y")])

    def test_manifest_has_explanation_key_none_when_no_disagreement(self):
        svc = ObserverUncertaintyService(llm=None, clusterer=_ExactMatchClusterer(),
                                         cfg=_cfg(), prompt_hash="x")
        with tempfile.TemporaryDirectory() as d:
            manifest = svc.measure_from_samples(["[1]: Button - Login"] * 5, WIDGETS, "s", d)
        self.assertIn("explanation", manifest)
        self.assertIsNone(manifest["explanation"])

    def test_manifest_explanation_is_none_when_llm_is_none_even_with_disagreement(self):
        # llm=None -> explainer call raises internally -> caught -> None.
        # This must not raise, even though there IS real disagreement.
        svc = ObserverUncertaintyService(llm=None, clusterer=_ExactMatchClusterer(),
                                         cfg=_cfg(), prompt_hash="x")
        samples = (["[1]: Primary Button - Login"] * 3) + (["[1]: Text Link - Login"] * 2)
        with tempfile.TemporaryDirectory() as d:
            manifest = svc.measure_from_samples(samples, WIDGETS, "Login screen", d)
        self.assertIsNone(manifest["explanation"])

    def test_manifest_explanation_populated_when_llm_provided(self):
        class _ExplainerLLM:
            def invoke(self, messages):
                from unittest.mock import MagicMock
                return MagicMock(content="3 of 5 said Primary Button, 2 said Text Link.")
        svc = ObserverUncertaintyService(llm=_ExplainerLLM(), clusterer=_ExactMatchClusterer(),
                                         cfg=_cfg(), prompt_hash="x")
        samples = (["[1]: Primary Button - Login"] * 3) + (["[1]: Text Link - Login"] * 2)
        with tempfile.TemporaryDirectory() as d:
            manifest = svc.measure_from_samples(samples, WIDGETS, "Login screen", d)
        self.assertIsNotNone(manifest["explanation"])
        self.assertIn("Primary Button", manifest["explanation"])

    def test_per_widget_entries_carry_text_and_role(self):
        svc = ObserverUncertaintyService(llm=None, clusterer=_ExactMatchClusterer(),
                                         cfg=_cfg(), prompt_hash="x")
        with tempfile.TemporaryDirectory() as d:
            manifest = svc.measure_from_samples(["[1]: Button - Login"] * 5, WIDGETS, "s", d)
        w = manifest["widgets"][0]
        self.assertEqual(w["text"], "Login")
        self.assertEqual(w["role"], "button")

    def test_widget_cap_skips_widgets_beyond_max_widgets(self):
        cfg = UncertaintyConfig(enabled=True, samples=5, temperature=1.0,
                                provider="stub", model="m", judge_model="m",
                                max_widgets=1)
        svc = ObserverUncertaintyService(llm=None, clusterer=_ExactMatchClusterer(),
                                         cfg=cfg, prompt_hash="x")
        widgets = [
            {"id": 1, "text": "Login", "xml_role": "button"},
            {"id": 2, "text": "Cancel", "xml_role": "button"},
            {"id": 3, "text": "Help", "xml_role": "link"},
        ]
        samples = ["[1]: Button - Login"] * 5
        with tempfile.TemporaryDirectory() as d:
            manifest = svc.measure_from_samples(samples, widgets, "s", d)

        self.assertEqual(manifest["widgets_measured"], 1)
        self.assertEqual(manifest["widgets_skipped"], 2)

        by_id = {w["element_id"]: w for w in manifest["widgets"]}
        self.assertEqual(by_id[1]["measurement_status"], "ok")
        self.assertEqual(by_id[2]["measurement_status"], "skipped_widget_cap")
        self.assertEqual(by_id[3]["measurement_status"], "skipped_widget_cap")
        self.assertNotIn("text", by_id[2])
        self.assertNotIn("role", by_id[3])

    def test_widget_cap_uses_position_not_value_equality(self):
        # Two widgets that are equal by value (same id/text/role) — an artificial,
        # adversarial construction to prove the cap classification is positional,
        # not a `w in skipped_widgets` value-equality membership check. If it were
        # value-based, the first (measured) widget would be misclassified as
        # skipped too, since it's equal-by-value to the second (actually skipped)
        # widget.
        cfg = UncertaintyConfig(enabled=True, samples=5, temperature=1.0,
                                provider="stub", model="m", judge_model="m",
                                max_widgets=1)
        svc = ObserverUncertaintyService(llm=None, clusterer=_ExactMatchClusterer(),
                                         cfg=cfg, prompt_hash="x")
        widgets = [
            {"id": 1, "text": "Login", "xml_role": "button"},
            {"id": 1, "text": "Login", "xml_role": "button"},
        ]
        samples = ["[1]: Button - Login"] * 5
        with tempfile.TemporaryDirectory() as d:
            manifest = svc.measure_from_samples(samples, widgets, "s", d)

        self.assertEqual(manifest["widgets_measured"], 1)
        self.assertEqual(manifest["widgets_skipped"], 1)

        entries = manifest["widgets"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["measurement_status"], "ok")
        self.assertEqual(entries[1]["measurement_status"], "skipped_widget_cap")


if __name__ == "__main__":
    unittest.main()
