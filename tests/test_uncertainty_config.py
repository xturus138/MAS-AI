import sys
import unittest

sys.path.append(".")


class TestUncertaintyConfig(unittest.TestCase):
    def test_defaults_present_and_typed(self):
        from shared import config
        self.assertIsInstance(config.OBSERVER_UNCERTAINTY_ENABLED, bool)
        self.assertIsInstance(config.OBSERVER_UNCERTAINTY_SAMPLES, int)
        self.assertIsInstance(config.OBSERVER_UNCERTAINTY_TEMPERATURE, float)

    def test_default_disabled(self):
        from shared import config
        # default must be OFF so the workflow is unchanged out of the box
        self.assertFalse(config.OBSERVER_UNCERTAINTY_ENABLED)


if __name__ == "__main__":
    unittest.main()
