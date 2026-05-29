import sys
from shared import config
from core.workflow.predefined.runner import run_predefined
from core.workflow.autonomous.runner import run_autonomous

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    if config.WORKFLOW_STRATEGY == "autonomous":
        run_autonomous()
    else:
        run_predefined()