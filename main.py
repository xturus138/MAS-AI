from shared import config
from core.workflow.predefined.runner import run_predefined
from core.workflow.autonomous.runner import run_autonomous

if __name__ == "__main__":
    if config.WORKFLOW_STRATEGY == "autonomous":
        run_autonomous()
    else:
        run_predefined()