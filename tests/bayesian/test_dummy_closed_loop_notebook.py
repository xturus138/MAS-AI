import json
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = REPO_ROOT / "experiment" / "bayesian" / "bayesian_dummy_closed_loop.ipynb"


def load_notebook() -> dict:
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))


def execute_tagged_cell(tag: str) -> dict:
    notebook = load_notebook()
    matching = [
        cell
        for cell in notebook["cells"]
        if tag in cell.get("metadata", {}).get("tags", [])
    ]
    assert len(matching) == 1, f"Expected exactly one cell tagged {tag!r}"
    namespace: dict = {}
    exec("".join(matching[0]["source"]), namespace)
    return namespace


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
    """Catch extra plots or the loss of independent BO snapshot figures."""
    notebook = load_notebook()
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )

    assert "Convergence plot" in source
    assert "Posterior and acquisition snapshots" in source
    assert 'f"iteration_snapshots_{safe_name}.png"' in source
    assert "for method_name, method_snapshots in snapshots_by_method.items()" in source

    for removed_plot in (
        "True dummy oracle",
        "Cost-Aware Convergence",
        "Dummy Bug Discovery Position",
        "Feature Coverage by Execution Position",
    ):
        assert removed_plot not in source


def test_notebook_reader_text_is_in_english():
    """Catch Indonesian reader-facing copy returning to the notebook."""
    notebook = load_notebook()
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )

    for indonesian_phrase in (
        "untuk Firebase",
        "Alur eksperimen",
        "Membaca dan memvalidasi",
        "Pada laptop",
        "Grafik ini",
        "Ketiga metode",
        "Surrogate yang dipakai",
        "Cara membaca hasil",
    ):
        assert indonesian_phrase not in source


def test_notebook_uses_a_controlled_oracle_without_a_random_baseline():
    """Keep the experiment focused on the three requested representations."""
    notebook = load_notebook()
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )

    assert "DUMMY_FAULT_THEMES" in source
    assert "assert warm_start_bug_count >= 1" in source
    assert "Warm-start results before Bayesian selection" in source
    assert "All fixed dummy bugs for researcher inspection" in source
    assert "How each method chooses test #10" in source
    assert "run_random_baseline" not in source
    assert "random_baseline_summary" not in source


def test_summary_measures_only_choices_made_after_warm_start():
    """Avoid crediting the optimizer for a dummy bug already present in the seed."""
    notebook = load_notebook()
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )

    assert "bo_selected_dummy_bugs_by_20_tests" in source
    assert "normalized_auc_after_warm_start" in source
    assert "additional_cost_after_warm_start" in source
    assert "first_dummy_bug_position" not in source


def test_data_helpers_parse_cost_and_choose_one_seed_per_menu():
    """Catch invalid cost parsing or a seed policy that omits/duplicates a feature."""
    helpers = execute_tagged_cell("data_helpers")
    cases = pd.DataFrame(
        {
            "TCS ID": ["B-002", "A-002", "B-001", "A-001"],
            "Menu": ["B", "A", "B", "A"],
        }
    )

    assert helpers["parse_minutes"]("13 mins") == 13.0
    assert helpers["parse_minutes"](7) == 7.0
    seed_indices = helpers["choose_initial_seed"](cases)
    assert seed_indices == [2, 3]
    assert cases.iloc[seed_indices]["Menu"].nunique() == 2


def test_closed_loop_selects_every_case_once_and_audits_revealed_labels():
    """Catch duplicate selection and training on labels not yet revealed."""
    helpers = execute_tagged_cell("bo_helpers")
    ids = np.array(["A-001", "A-002", "B-001", "B-002"])
    matrix = np.array(
        [[0.0, 0.0], [0.2, 0.1], [1.0, 0.9], [0.9, 1.0]], dtype=float
    )
    oracle = np.array([0, 1, 0, 1], dtype=int)

    result, audit, _ = helpers["run_closed_loop"](
        matrix=matrix,
        ids=ids,
        menus=np.array(["A", "A", "B", "B"]),
        costs=np.array([2.0, 3.0, 1.0, 4.0]),
        oracle=oracle,
        initial_indices=[0, 2],
        kappa=1.5,
        cost_exponent=0.5,
        snapshot_counts={2},
        random_state=42,
    )

    assert result["tcs_id"].tolist()[:2] == ["A-001", "B-001"]
    assert set(result["tcs_id"]) == set(ids)
    assert result["tcs_id"].is_unique
    assert result["cumulative_bugs"].tolist()[-1] == 2
    assert all(entry["training_indices"] == entry["revealed_indices"] for entry in audit)
    assert all(entry["train_count"] == entry["revealed_count"] for entry in audit)
