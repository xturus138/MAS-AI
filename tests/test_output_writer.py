import sys
import os
import tempfile
import unittest

sys.path.append(".")
from core.utils.output_writer import write_run_overview


def _make_step_explanation(output_dir, step_num, text):
    step_dir = os.path.join(output_dir, "steps", f"{step_num:03d}", "uncertainty")
    os.makedirs(step_dir, exist_ok=True)
    with open(os.path.join(step_dir, "explanation.txt"), "w", encoding="utf-8") as f:
        f.write(text)


class TestRunOverviewUncertaintySection(unittest.TestCase):
    def _base_kwargs(self, output_dir):
        return dict(
            output_dir=output_dir, tcs_id="TCS-001", status="SUCCESS", mode="predefined",
            steps_completed=1, total_steps=1, duration_seconds=10.0,
            physical_actions=1, figma_enabled=False, tokens=100, cost_usd=0.01,
            reflector_judgment="Looks good.",
        )

    def test_section_omitted_when_no_explanations_exist(self):
        with tempfile.TemporaryDirectory() as d:
            path = write_run_overview(**self._base_kwargs(d))
            with open(path, encoding="utf-8") as f:
                content = f.read()
        self.assertNotIn("Observer Uncertainty", content)

    def test_section_present_with_one_step_explanation(self):
        with tempfile.TemporaryDirectory() as d:
            _make_step_explanation(d, 1, "3 of 5 said A, 2 said B.")
            path = write_run_overview(**self._base_kwargs(d))
            with open(path, encoding="utf-8") as f:
                content = f.read()
        self.assertIn("## Observer Uncertainty", content)
        self.assertIn("Step 1", content)
        self.assertIn("3 of 5 said A, 2 said B.", content)

    def test_section_present_with_multiple_steps_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            _make_step_explanation(d, 2, "Second step explanation.")
            _make_step_explanation(d, 1, "First step explanation.")
            path = write_run_overview(**self._base_kwargs(d))
            with open(path, encoding="utf-8") as f:
                content = f.read()
        first_pos = content.index("First step explanation.")
        second_pos = content.index("Second step explanation.")
        self.assertLess(first_pos, second_pos)


if __name__ == "__main__":
    unittest.main()
