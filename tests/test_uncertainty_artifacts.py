import sys
import os
import json
import tempfile
import unittest

sys.path.append(".")
from core.uncertainty.artifacts import write_uncertainty_artifacts


class TestArtifacts(unittest.TestCase):
    def test_writes_manifest_and_widgets(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = {
                "enabled": True,
                "threshold": None,
                "calibration_status": "not_calibrated",
                "temperature_application": "requested_not_verified",
            }
            per_widget = [{"element_id": 1, "normalized_dse": 0.0}]
            out = write_uncertainty_artifacts(d, manifest, per_widget)
            self.assertTrue(os.path.isdir(out))
            with open(os.path.join(out, "manifest.json"), encoding="utf-8") as f:
                m = json.load(f)
            self.assertIsNone(m["threshold"])
            self.assertEqual(m["temperature_application"], "requested_not_verified")
            with open(os.path.join(out, "widgets.json"), encoding="utf-8") as f:
                w = json.load(f)
            self.assertEqual(w[0]["element_id"], 1)

    def test_strips_secret_keys(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = {"enabled": True, "api_key": "SECRET", "token": "SECRET2",
                        "nested": {"authorization": "Bearer x"}}
            out = write_uncertainty_artifacts(d, manifest, [])
            with open(os.path.join(out, "manifest.json"), encoding="utf-8") as f:
                m = json.load(f)
            self.assertNotIn("api_key", m)
            self.assertNotIn("token", m)
            self.assertNotIn("authorization", m.get("nested", {}))

    def test_writes_explanation_txt_when_present(self):
        manifest = {"explanation": "3 of 5 said A, 2 said B.", "widgets": []}
        with tempfile.TemporaryDirectory() as d:
            unc_dir = write_uncertainty_artifacts(d, manifest, [])
            exp_path = os.path.join(unc_dir, "explanation.txt")
            self.assertTrue(os.path.exists(exp_path))
            with open(exp_path, encoding="utf-8") as f:
                content = f.read()
            self.assertEqual(content, "3 of 5 said A, 2 said B.")

    def test_does_not_write_explanation_txt_when_none(self):
        manifest = {"explanation": None, "widgets": []}
        with tempfile.TemporaryDirectory() as d:
            unc_dir = write_uncertainty_artifacts(d, manifest, [])
            exp_path = os.path.join(unc_dir, "explanation.txt")
            self.assertFalse(os.path.exists(exp_path))

    def test_does_not_write_explanation_txt_when_key_missing(self):
        manifest = {"widgets": []}  # no "explanation" key at all
        with tempfile.TemporaryDirectory() as d:
            unc_dir = write_uncertainty_artifacts(d, manifest, [])
            exp_path = os.path.join(unc_dir, "explanation.txt")
            self.assertFalse(os.path.exists(exp_path))


if __name__ == "__main__":
    unittest.main()
