from shared import config
from predefined.runner import run_predefined
from autonomous.runner import run_autonomous

if __name__ == "__main__":
    if config.WORKFLOW_STRATEGY == "autonomous":
        run_autonomous()
    else:
        run_predefined()