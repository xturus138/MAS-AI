import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK = REPO_ROOT / "experiment" / "bayesian" / "three_method_representation_comparison.ipynb"
LAUNCHER = REPO_ROOT / "run_paper_vectoriser_experiment.cmd"


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

    assert {
        "data_helpers",
        "bo_helpers",
        "fairness_helpers",
        "vectoriser_selection_helpers",
    }.issubset(tags)


def test_vectoriser_selection_defaults_to_a_fast_pair_and_accepts_explicit_methods():
    """Catch Run All silently starting large pretrained-model downloads."""
    helpers = execute_tagged_cell("vectoriser_selection_helpers")

    assert helpers["select_vectorisers"]("quick") == ("TF-IDF", "Feature Hashing")
    assert helpers["select_vectorisers"]("Word2Vec, Flair") == ("Word2Vec", "Flair")
    assert helpers["select_vectorisers"]("all") == helpers["EXPERIMENT_METHODS"]
    assert helpers["EXPERIMENT_METHODS"][-2:] == (
        "One-Hot Encoding",
        "Multilingual E5 Large Instruct",
    )
    assert helpers["build_vectoriser_metadata"]("quick") == {
        "vectoriser_selection": "quick",
        "selected_vectorisers": ["TF-IDF", "Feature Hashing"],
    }
    assert helpers["default_vectoriser_selection"](is_colab=True) == "all"
    assert helpers["default_vectoriser_selection"](is_colab=False) == "quick"
    assert helpers["required_packages_for"](("ELMo",)) == {
        "tensorflow": "tensorflow",
        "tensorflow_hub": "tensorflow-hub",
    }
    assert helpers["required_packages_for"](("Flair",)) == {"flair": "flair"}
    assert helpers["required_packages_for"](("Multilingual E5 Large Instruct",)) == {
        "sentence_transformers": "sentence-transformers",
    }


def test_launcher_check_defaults_to_the_fast_pair():
    """Catch a local launcher that silently starts the full pretrained download set."""
    completed = subprocess.run(
        ["cmd", "/c", str(LAUNCHER), "check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Mode: quick (TF-IDF, Feature Hashing)" in completed.stdout


def test_notebook_contains_the_requested_experiment_outputs():
    """Catch extra plots or the loss of independent BO snapshot figures."""
    notebook = load_notebook()
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )

    assert "Convergence plot" in source
    assert "Model estimate and selection-score snapshots" in source
    assert 'f"iteration_snapshots_{safe_name}.png"' in source
    assert "for method_name, method_snapshots in snapshots_by_method.items()" in source
    assert "PAPER_VECTORISERS" in source

    for vectoriser in (
        "TF-IDF",
        "Feature Hashing",
        "Word2Vec",
        "GloVe",
        "FastText",
        "ELMo",
        "Flair",
    ):
        assert vectoriser in source

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
    """Keep the experiment focused on the seven requested vectorisers."""
    notebook = load_notebook()
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )

    assert "DUMMY_FAULT_THEMES" in source
    assert "assert warm_start_bug_count >= 1" in source
    assert "Warm-start results before sequential selection" in source
    assert "All fixed dummy bugs for researcher inspection" in source
    assert "How each vectoriser chooses test #10" in source
    assert "run_random_baseline" not in source
    assert "random_baseline_summary" not in source
    assert "One-Hot Encoding" in source
    assert "Multilingual E5 Large Instruct" in source
    assert "allennlp" not in source
    assert "tensorflow_hub" in source


def test_final_summary_reports_the_requested_run_milestones():
    """Keep the final reader-facing output to the five requested comparison points."""
    notebook = load_notebook()
    source = "\n".join(
        "".join(cell.get("source", [])) for cell in notebook["cells"]
    )

    assert "Nine-representation visual-demo summary" in source
    assert "Best Method:" in source
    assert "Dummy Bugs Found by Run 20" in source
    assert "Dummy Bugs Found by Run 50" in source
    assert "Run When All Dummy Bugs Were Found" in source
    assert "Total Cost to Find All Dummy Bugs (minutes)" in source
    assert 'RESULT_DIR / "final_summary.csv"' in source
    assert "Non-visual synthetic fairness check" in source
    assert "Neutral random fault instances" in source
    assert "No representation winner is declared" in source
    assert "Mean Bugs Found by Run 20" in source
    assert "Median Run When All 13 Dummy Bugs Were Found" in source
    assert 'RESULT_DIR / "synthetic_fairness_summary.csv"' in source
    assert "convergence_by_scenario" not in source

    for removed_report in (
        "Complete final report",
        "normalized_auc_after_warm_start",
        "remaining_dummy_bugs_after_20_tests",
        "fault_discovery_report",
        "theme_discovery_report",
    ):
        assert removed_report not in source


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


def test_fairness_helpers_create_paired_neutral_instances():
    """Fairness labels and warm starts must not depend on a representation matrix."""
    helpers = execute_tagged_cell("fairness_helpers")
    oracle = helpers["draw_uniform_oracle"](case_count=10, bug_count=3, random_state=7)
    menus = np.array(["B", "A", "B", "A", "C"])
    initial_indices = helpers["choose_paired_initial_indices"](menus, random_state=7)

    assert oracle.tolist() == helpers["draw_uniform_oracle"](10, 3, 7).tolist()
    assert int(oracle.sum()) == 3
    assert len(initial_indices) == 3
    assert len(set(initial_indices)) == 3
    assert set(menus[initial_indices]) == {"A", "B", "C"}


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


def test_final_ranking_prefers_the_earliest_complete_bug_discovery():
    """Catch a Best Method rule that favors early partial discovery over completion."""
    helpers = execute_tagged_cell("bo_helpers")
    summary = pd.DataFrame(
        [
            {"Method": "FastText", "Dummy Bugs Found by Run 20": 9,
             "Dummy Bugs Found by Run 50": 13,
             "Run When All Dummy Bugs Were Found": 32,
             "Total Cost to Find All Dummy Bugs (minutes)": 245.0},
            {"Method": "Word2Vec", "Dummy Bugs Found by Run 20": 8,
             "Dummy Bugs Found by Run 50": 13,
             "Run When All Dummy Bugs Were Found": 28,
             "Total Cost to Find All Dummy Bugs (minutes)": 204.0},
            {"Method": "GloVe", "Dummy Bugs Found by Run 20": 8,
             "Dummy Bugs Found by Run 50": 13,
             "Run When All Dummy Bugs Were Found": 28,
             "Total Cost to Find All Dummy Bugs (minutes)": 239.0},
        ]
    )

    ranked = helpers["rank_final_summary"](summary)

    assert ranked["Method"].tolist() == ["Word2Vec", "GloVe", "FastText"]
