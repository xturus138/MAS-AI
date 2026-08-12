# Bayesian Dummy Closed-Loop Notebook Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained Colab and local Jupyter notebook that compares three numeric test-case representations in a closed-loop Bayesian simulation using one fixed dummy oracle and produces the requested truth, convergence, cost, and iteration-panel visualizations.

**Architecture:** The notebook owns the prototype pipeline end to end: workbook discovery or upload, validation, fixed dummy-oracle construction, three representation matrices, a shared Gaussian Process and cost-aware UCB loop, plots, and exports. A small pytest contract suite reads the notebook as JSON and executes its tagged helper cells to test the reusable logic without downloading the E5 model.

**Tech Stack:** Python 3, Jupyter Notebook v4, pandas, NumPy, openpyxl, scikit-learn, matplotlib, seaborn, sentence-transformers, pytest.

## Global Constraints

- Store the notebook at `experiment/bayesian/bayesian_dummy_closed_loop.ipynb`.
- Run in Google Colab and on a local laptop without API keys.
- Use the existing `scenarios/firebase_chat/scenario.xlsx` locally and a Colab upload fallback.
- Keep dummy bug locations fixed in one editable `DUMMY_BUG_IDS` cell.
- Do not modify the original workbook or expose unrevealed dummy labels to surrogate training.
- Compare One-Hot, TF-IDF with Truncated SVD, Multilingual E5, and a reproducible random-order baseline.
- Use identical seeds, initial tests, costs, surrogate settings, and acquisition settings across representation methods.
- Treat connecting lines over test IDs as display guides, not a continuous objective.
- Save experiment artifacts under `experiment/bayesian/results`, never `outputs/`.
- Do not describe dummy findings as evidence of real Android defects.

---

### Task 1: Notebook contract tests

**Files:**
- Create: `tests/bayesian/test_dummy_closed_loop_notebook.py`
- Test: `tests/bayesian/test_dummy_closed_loop_notebook.py`

**Interfaces:**
- Consumes: planned notebook path and tagged cells named `data_helpers` and `bo_helpers`.
- Produces: structural and behavioral checks used to drive the notebook implementation.

- [ ] **Step 1: Write failing notebook structure tests**

```python
NOTEBOOK = REPO_ROOT / "experiment" / "bayesian" / "bayesian_dummy_closed_loop.ipynb"

def test_notebook_has_required_sections():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    source = "\n".join("".join(cell.get("source", [])) for cell in notebook["cells"])
    for heading in (
        "True dummy oracle",
        "Representation matrices",
        "Closed-loop Bayesian selection",
        "Convergence plots",
        "Iteration snapshots",
    ):
        assert heading in source
```

- [ ] **Step 2: Run the test and verify it fails because the notebook does not exist**

Run: `pytest tests/bayesian/test_dummy_closed_loop_notebook.py -q`

Expected: FAIL with `FileNotFoundError` for `experiment/bayesian/bayesian_dummy_closed_loop.ipynb`.

- [ ] **Step 3: Add behavioral contracts for helper cells**

```python
def test_parse_minutes_and_initial_seed(helper_namespace, firebase_dataframe):
    assert helper_namespace["parse_minutes"]("13 mins") == 13.0
    seeds = helper_namespace["choose_initial_seed"](firebase_dataframe)
    assert len(seeds) == firebase_dataframe["Menu"].nunique()
    assert firebase_dataframe.iloc[seeds]["Menu"].nunique() == len(seeds)

def test_simulation_reveals_only_selected_labels(bo_namespace, toy_problem):
    result, audit = bo_namespace["run_closed_loop"](**toy_problem)
    assert set(result["tcs_id"]) == set(toy_problem["ids"])
    assert all(entry["train_count"] == entry["revealed_count"] for entry in audit)
```

- [ ] **Step 4: Commit the failing contract tests**

```bash
git add tests/bayesian/test_dummy_closed_loop_notebook.py
git commit -m "test: define Bayesian notebook contract"
```

### Task 2: Self-contained notebook data and representation pipeline

**Files:**
- Create: `experiment/bayesian/bayesian_dummy_closed_loop.ipynb`
- Test: `tests/bayesian/test_dummy_closed_loop_notebook.py`

**Interfaces:**
- Consumes: Firebase Chat workbook and editable `DUMMY_BUG_IDS: list[str]`.
- Produces: validated `cases: pandas.DataFrame`, `oracle: numpy.ndarray`, `costs: numpy.ndarray`, `representations: dict[str, numpy.ndarray]`, and `initial_indices: list[int]`.

- [ ] **Step 1: Add setup, imports, environment detection, and configuration cells**

The configuration cell must define fixed values:

```python
RANDOM_STATE = 42
BETA = 1.5
COST_EXPONENT = 0.5
RUN_E5 = True
E5_MODEL_NAME = "intfloat/multilingual-e5-large-instruct"
DUMMY_BUG_IDS = [
    "FC-LGN-003", "FC-REG-004", "FC-MN-006",
    "FC-NCP-005", "FC-CRP-011", "FC-CRG-004",
    "FC-GPR-003", "FC-MIF-004", "FC-PRF-004",
]
```

- [ ] **Step 2: Implement tagged workbook helpers**

```python
def parse_minutes(value) -> float:
    match = re.search(r"\d+(?:\.\d+)?", str(value))
    if not match:
        raise ValueError(f"Cannot parse Time Testing value: {value!r}")
    return float(match.group())

def choose_initial_seed(cases: pd.DataFrame) -> list[int]:
    ordered = cases.reset_index().sort_values(["Menu", "TCS ID"])
    return sorted(ordered.groupby("Menu", sort=True).head(1)["index"].tolist())
```

The loader must search repository-relative paths first and use `google.colab.files.upload()` only when no local workbook is found.

- [ ] **Step 3: Add the fixed hidden oracle and initial truth plot**

Create `oracle = cases["TCS ID"].isin(DUMMY_BUG_IDS).astype(int).to_numpy()` after validating every configured ID. Plot a binary step or guide line plus markers, label it `True dummy oracle (hidden from BO)`, and state that the x-axis is a display order.

- [ ] **Step 4: Implement three independent encoders**

```python
def build_one_hot(cases): ...
def build_tfidf_svd(cases, random_state=42): ...
def build_e5(cases, model_name, task_instruction): ...
```

One-Hot uses only categorical fields. TF-IDF and E5 use the same labeled text serialization. E5 runs once, normalizes its vectors, and stores `e5_embeddings.npy` under the result directory. Every matrix must have 69 rows and finite values.

- [ ] **Step 5: Run contract tests until data and encoding structure pass**

Run: `pytest tests/bayesian/test_dummy_closed_loop_notebook.py -q`

Expected: structure and helper tests pass; the BO helper test remains failing until Task 3.

- [ ] **Step 6: Commit the notebook data pipeline**

```bash
git add experiment/bayesian/bayesian_dummy_closed_loop.ipynb tests/bayesian/test_dummy_closed_loop_notebook.py
git commit -m "feat: add Bayesian notebook data pipeline"
```

### Task 3: Closed-loop Gaussian Process simulation

**Files:**
- Modify: `experiment/bayesian/bayesian_dummy_closed_loop.ipynb`
- Modify: `tests/bayesian/test_dummy_closed_loop_notebook.py`

**Interfaces:**
- Consumes: one numeric matrix, IDs, menu names, costs, hidden oracle, initial indices, `beta`, and `cost_exponent`.
- Produces: one execution-order DataFrame and an audit list for each method.

- [ ] **Step 1: Add a failing test that detects label leakage and duplicate selection**

```python
assert result["tcs_id"].is_unique
assert len(result) == len(toy_problem["ids"])
assert all(entry["training_indices"] == entry["revealed_indices"] for entry in audit)
```

- [ ] **Step 2: Implement the tagged `run_closed_loop` helper**

Use `GaussianProcessRegressor` with a scalar-length-scale kernel, fit only `X[revealed]` and `oracle[revealed]`, then score remaining candidates with:

```python
utility = np.clip(mean, 0.0, 1.0) + beta * std
acquisition = utility / np.power(np.maximum(costs, 1.0), cost_exponent)
```

Select by maximum acquisition and break ties by sorted `TCS ID`. Store posterior arrays and acquisition arrays at configured snapshot iterations.

- [ ] **Step 3: Implement the random baseline**

Keep the same initial indices, shuffle only the remaining candidates with `np.random.default_rng(RANDOM_STATE)`, and reveal labels in that order.

- [ ] **Step 4: Add invariants inside the notebook**

```python
assert set(run["tcs_id"]) == set(cases["TCS ID"])
assert run["tcs_id"].is_unique
assert run["cumulative_bugs"].is_monotonic_increasing
assert run["cumulative_cost"].is_monotonic_increasing
```

- [ ] **Step 5: Run all contract tests**

Run: `pytest tests/bayesian/test_dummy_closed_loop_notebook.py -q`

Expected: PASS.

- [ ] **Step 6: Commit the closed-loop simulator**

```bash
git add experiment/bayesian/bayesian_dummy_closed_loop.ipynb tests/bayesian/test_dummy_closed_loop_notebook.py
git commit -m "feat: simulate closed-loop Bayesian test selection"
```

### Task 4: Visualizations, export, and execution verification

**Files:**
- Modify: `experiment/bayesian/bayesian_dummy_closed_loop.ipynb`
- Modify: `tests/bayesian/test_dummy_closed_loop_notebook.py`
- Create at runtime: `experiment/bayesian/results/*.csv`
- Create at runtime: `experiment/bayesian/results/*.png`

**Interfaces:**
- Consumes: execution DataFrames, snapshot posterior records, cases, and oracle.
- Produces: inline figures, PNG files, CSV tables, and a Colab ZIP archive.

- [ ] **Step 1: Add convergence and cost plots**

Plot all three representations plus Random on shared axes. Include a horizontal line for total configured dummy bugs. Save `convergence_by_tests.png` and `convergence_by_cost.png`.

- [ ] **Step 2: Add bug-position and feature-coverage plots**

Create a discovery-position heatmap or dot plot and a feature coverage curve based on unique `Menu` values observed by each execution position.

- [ ] **Step 3: Add reference-style iteration snapshots**

For the configurable detailed method, render rows of two panels. The left panel shows dummy truth, GP mean, a 95 percent guide band, and observed points. The right panel shows acquisition over untested candidates and the selected candidate. Use fixed test display order and label connecting lines as guides.

- [ ] **Step 4: Add result tables and exports**

Save one ordering CSV per method plus `summary.csv`. Create `bayesian_dummy_results.zip` in Colab and display a download control without forcing an automatic download locally.

- [ ] **Step 5: Execute the notebook without E5 for a local smoke test**

Run the notebook with `RUN_E5 = False` in a temporary execution copy or an environment-controlled override. Confirm the real workbook loads 69 cases and One-Hot, TF-IDF with SVD, and Random complete.

- [ ] **Step 6: Validate notebook JSON, Python syntax, and outputs**

Run:

```powershell
python -m json.tool experiment/bayesian/bayesian_dummy_closed_loop.ipynb > $null
pytest tests/bayesian/test_dummy_closed_loop_notebook.py -q
```

Expected: valid JSON and all tests PASS. Confirm saved PNG files are nonempty and visually inspect at least the truth, convergence, and snapshot figures.

- [ ] **Step 7: Commit the verified notebook**

```bash
git add experiment/bayesian/bayesian_dummy_closed_loop.ipynb tests/bayesian/test_dummy_closed_loop_notebook.py
git commit -m "feat: visualize Bayesian dummy experiment"
```
