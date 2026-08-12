import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = REPO_ROOT / "experiment" / "bayesian" / "bayesian_dummy_closed_loop.ipynb"


def load_notebook() -> dict:
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))


def test_notebook_exposes_executable_helper_contracts():
    """Catch a missing notebook or helper cells that cannot be tested independently."""
    notebook = load_notebook()
    tags = {
        tag
        for cell in notebook["cells"]
        for tag in cell.get("metadata", {}).get("tags", [])
    }

    assert {"data_helpers", "bo_helpers"}.issubset(tags)


def test_notebook_contains_the_requested_experiment_outputs():
    """Catch accidental removal of a required experiment stage or visualization."""
    notebook = load_notebook()
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )

    for required_section in (
        "True dummy oracle",
        "Representation matrices",
        "Closed-loop Bayesian selection",
        "Convergence plots",
        "Iteration snapshots",
    ):
        assert required_section in source
