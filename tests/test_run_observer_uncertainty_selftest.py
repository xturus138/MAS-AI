import os
import sys
import unittest

# Repo root must precede site-packages so `import tests.*` resolves to this
# project's tests package (some installed packages also expose a top-level
# `tests` package that would otherwise shadow it).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
sys.path.append(".")


class TestRunnerSelfTest(unittest.TestCase):
    def test_self_test_passes_and_uses_shared_service(self):
        from tests.run_observer_uncertainty import run_self_test
        # run_self_test returns 0 on success and internally uses
        # ObserverUncertaintyService (the production class).
        self.assertEqual(run_self_test(), 0)

    def test_runner_imports_production_service(self):
        import tests.run_observer_uncertainty as r
        from core.uncertainty.service import ObserverUncertaintyService
        self.assertIs(r.ObserverUncertaintyService, ObserverUncertaintyService)


if __name__ == "__main__":
    unittest.main()
