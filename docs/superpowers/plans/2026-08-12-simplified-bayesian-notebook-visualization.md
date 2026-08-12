# Simplified Bayesian notebook visualization implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the Bayesian experiment notebook in clear English and limit its charts to one convergence figure plus one reference-style posterior and acquisition figure per Bayesian representation.

**Architecture:** Keep the data preparation, independent representation matrices, closed-loop runs, summary table, and exports unchanged. Replace the plotting section so One-Hot, TF-IDF with SVD, and Multilingual E5 each render their own repeated two-column snapshot figure, while Random appears only in the shared convergence plot.

**Tech Stack:** Jupyter Notebook v4, Python 3.12, NumPy, pandas, matplotlib, pytest.

## Global Constraints

- Use English for every markdown cell, chart title, axis label, legend, print message, and code comment.
- Keep One-Hot, TF-IDF with SVD, and Multilingual E5 as independent experiments.
- Keep Random as an independent baseline with no posterior or acquisition plot.
- Plot only convergence and per-representation iteration snapshots.
- Treat lines over fixed Excel order as visual guides for discrete candidates.
- Keep CSV and ZIP exports.
- Keep E5 enabled by default in Google Colab and allow `BAYESIAN_NOTEBOOK_RUN_E5=0` for local smoke testing.

---

### Task 1: Define the simplified visualization contract

**Files:**
- Modify: `tests/bayesian/test_dummy_closed_loop_notebook.py`
- Test: `tests/bayesian/test_dummy_closed_loop_notebook.py`

**Interfaces:**
- Consumes: notebook JSON cells and their source text.
- Produces: tests that reject removed plot types and require independent snapshot export for each Bayesian representation.

- [ ] **Step 1: Add a failing structural test**

Assert that the notebook contains `Convergence plot` and `Posterior and acquisition snapshots`, contains the output pattern `iteration_snapshots_{safe_name}.png`, and no longer contains the plot sections `True dummy oracle`, `Cost-Aware Convergence`, `Dummy Bug Discovery Position`, or `Feature Coverage by Execution Position`.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `.\venv\Scripts\python.exe -m pytest tests/bayesian/test_dummy_closed_loop_notebook.py -q`

Expected: FAIL because the existing notebook still contains the removed plot types and only exports one snapshot figure.

### Task 2: Rewrite and simplify the notebook

**Files:**
- Modify: `experiment/bayesian/bayesian_dummy_closed_loop.ipynb`
- Test: `tests/bayesian/test_dummy_closed_loop_notebook.py`

**Interfaces:**
- Consumes: `runs: dict[str, DataFrame]`, `snapshots_by_method: dict[str, list[dict]]`, fixed `oracle`, `ids`, and `x_display`.
- Produces: `convergence.png` and one `iteration_snapshots_<method>.png` for every representation present in `snapshots_by_method`.

- [ ] **Step 1: Rewrite all notebook prose in plain English**

Use short paragraphs that explain what enters a step, what happens, and what the reader should learn. Remove Indonesian text, promotional phrasing, em dashes, and unnecessary headings.

- [ ] **Step 2: Remove extra plot cells**

Delete the standalone true-oracle plot, cost convergence plot, bug-position plot, and feature-coverage plot. Keep the oracle construction because it supplies the hidden dummy outcomes used by the experiment.

- [ ] **Step 3: Build the shared convergence plot**

Plot cumulative dummy bugs against execution position for every item in `runs`. Use a step line and include Random. Save only `convergence.png`.

- [ ] **Step 4: Build one reference-style figure per Bayesian method**

Loop over `snapshots_by_method.items()`. For each method, create four rows and two columns. On the left, plot dummy truth, GP mean, a 95 percent uncertainty band, and observations. On the right, plot display acquisition values with tested candidates set to zero, fill the area, and mark the next test. Save with:

```python
safe_name = re.sub(r"[^a-z0-9]+", "_", method_name.lower()).strip("_")
fig.savefig(RESULT_DIR / f"iteration_snapshots_{safe_name}.png", dpi=180, bbox_inches="tight")
```

- [ ] **Step 5: Keep summary and export cells nonvisual**

Continue writing ordering CSVs, `summary.csv`, `experiment_config.json`, and `bayesian_dummy_results.zip`. Display the summary as plain text or a DataFrame without adding plots.

- [ ] **Step 6: Run the focused tests**

Run: `.\venv\Scripts\python.exe -m pytest tests/bayesian/test_dummy_closed_loop_notebook.py -q`

Expected: PASS.

### Task 3: Execute and inspect the result

**Files:**
- Verify: `experiment/bayesian/bayesian_dummy_closed_loop.ipynb`
- Create at runtime: `experiment/bayesian/results/convergence.png`
- Create at runtime: `experiment/bayesian/results/iteration_snapshots_one_hot.png`
- Create at runtime: `experiment/bayesian/results/iteration_snapshots_tf_idf_svd.png`

**Interfaces:**
- Consumes: the real 69-case workbook with E5 disabled for the local smoke run.
- Produces: valid notebook execution, readable reference-style figures, and verified experiment artifacts.

- [ ] **Step 1: Run every code cell with E5 disabled**

Set `BAYESIAN_NOTEBOOK_RUN_E5=0` and execute all code cells in order against `scenarios/firebase_chat/scenario.xlsx`.

- [ ] **Step 2: Inspect the figures**

Open `convergence.png`, `iteration_snapshots_one_hot.png`, and `iteration_snapshots_tf_idf_svd.png`. Confirm that each snapshot figure has a left posterior and right acquisition panel, and that no unrelated plots are generated by the current notebook.

- [ ] **Step 3: Run full verification**

Run JSON parsing, compile every notebook code cell, verify each ordering has 69 unique IDs, then run `.\venv\Scripts\python.exe -m pytest -q`.

Expected: all checks pass.

- [ ] **Step 4: Commit only the notebook and test changes**

```powershell
git add -- experiment/bayesian/bayesian_dummy_closed_loop.ipynb tests/bayesian/test_dummy_closed_loop_notebook.py
git commit -m "feat: simplify Bayesian notebook visualizations"
```
