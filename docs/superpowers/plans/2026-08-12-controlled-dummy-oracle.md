# Controlled dummy oracle implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the closed-loop notebook evaluate a documented, learnable synthetic fault pattern and compare BO against a distribution of random runs.

**Architecture:** The notebook replaces its unstructured ID list with a two-theme `DUMMY_FAULT_THEMES` mapping. The feature-balanced initial seed remains label-independent and becomes the warm-start history. BO runs remain independent for One-Hot, TF-IDF with SVD, and E5. A 200-run random simulation provides the baseline mean and interval.

**Tech Stack:** Python 3.12, Jupyter Notebook v4, NumPy, pandas, matplotlib, pytest.

## Global Constraints

- Keep one fixed synthetic oracle with 13 documented dummy bugs.
- Keep the warm start at one first TCS ID per Menu, selected without oracle labels.
- Keep `kappa = 1.5`, `gamma = 0.5`, and cost-aware UCB.
- Run all three BO representations independently.
- Use 200 reproducible Random baselines with the same warm start.
- Do not claim a synthetic label is a real defect.

---

### Task 1: Add a failing controlled-oracle contract

**Files:**
- Modify: `tests/bayesian/test_dummy_closed_loop_notebook.py`

**Interfaces:**
- Consumes: notebook source.
- Produces: checks for documented themes, the warm-start assertion, and repeated Random comparison.

- [ ] **Step 1: Add the expected contract**

Assert the notebook defines `DUMMY_FAULT_THEMES`, `RANDOM_BASELINE_RUNS = 200`, checks `warm_start_bug_count >= 1`, and creates a `random_baseline_summary` using repeated calls to `run_random_baseline`.

- [ ] **Step 2: Run the test to confirm it fails**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/bayesian/test_dummy_closed_loop_notebook.py -q`

Expected: FAIL because the notebook still has a single arbitrary bug-ID list and one Random order.

### Task 2: Implement the controlled oracle and baseline

**Files:**
- Modify: `experiment/bayesian/bayesian_dummy_closed_loop.ipynb`
- Modify: `tests/bayesian/test_dummy_closed_loop_notebook.py`

**Interfaces:**
- Consumes: `DUMMY_FAULT_THEMES`, `initial_indices`, and the existing `run_random_baseline` helper.
- Produces: `oracle`, `fault_theme_by_id`, `random_baseline_summary`, and a convergence plot with a Random interval.

- [ ] **Step 1: Replace the undocumented list with two explicit fault themes**

Use the 13 TCS IDs in the controlled-oracle design. Flatten only this mapping into `DUMMY_BUG_IDS`, validate every ID against the workbook, and display the resulting fault-theme table.

- [ ] **Step 2: Validate the warm-start outcome after the oracle is built**

Compute `warm_start_bug_count = int(oracle[initial_indices].sum())`. Assert it is at least one and print that the warm start contains known historical outcomes.

- [ ] **Step 3: Generate 200 Random orders**

Build a list using `run_random_baseline(..., random_state=RANDOM_STATE + run_number)` for `run_number` from 0 through 199. Stack their `cumulative_bugs` series and calculate mean, fifth percentile, and ninety-fifth percentile by execution position.

- [ ] **Step 4: Update the convergence plot and summary**

Plot each BO curve separately. Add the Random mean as a dashed gray line and fill its fifth to ninety-fifth percentile interval. Export `random_baseline_summary.csv`; do not export one lucky random ordering as the baseline result.

- [ ] **Step 5: Clip only the displayed posterior signal to binary bounds**

Use `display_mean = np.clip(mean, 0.0, 1.0)` and clip the displayed 95 percent interval. Keep the existing acquisition calculation unchanged.

### Task 3: Execute, inspect, and report the new result

**Files:**
- Verify: `experiment/bayesian/bayesian_dummy_closed_loop.ipynb`
- Create at runtime: `experiment/bayesian/results/random_baseline_summary.csv`

**Interfaces:**
- Consumes: real Firebase Chat workbook with E5 disabled for local smoke testing.
- Produces: 69-case independent BO runs, Random distribution, and a concise experiment report.

- [ ] **Step 1: Run all cells with `BAYESIAN_NOTEBOOK_RUN_E5=0`**

Verify 69 cases, 13 dummy bugs, and at least one warm-start bug.

- [ ] **Step 2: Inspect `convergence.png` and both local snapshot figures**

Confirm Random is a mean-plus-interval baseline and the snapshot posterior stays inside the binary display range.

- [ ] **Step 3: Verify the notebook and full test suite**

Parse notebook JSON, compile code cells, check 69 unique IDs in each BO ordering, validate the 200-run baseline file, then run `.\\venv\\Scripts\\python.exe -m pytest -q`.

- [ ] **Step 4: Commit only the notebook and test change**

Stage `experiment/bayesian/bayesian_dummy_closed_loop.ipynb` and `tests/bayesian/test_dummy_closed_loop_notebook.py`, then commit with message `feat: control Bayesian dummy oracle`.
