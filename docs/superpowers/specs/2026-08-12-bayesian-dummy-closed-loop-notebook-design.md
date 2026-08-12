# Bayesian dummy closed-loop notebook design

Date: 2026-08-12

## Purpose

Create one Jupyter notebook that runs in Google Colab and on a local laptop. It will use the 69 Firebase Chat QA test cases to simulate sequential Bayesian test selection against one fixed, hidden dummy oracle.

The notebook is a pipeline and algorithm experiment. It may demonstrate that encoding, sequential selection, cost handling, and visual reporting work. It must not claim that dummy outcomes prove real defect-detection effectiveness.

## Deliverable

The notebook will be stored at:

`experiment/bayesian/bayesian_dummy_closed_loop.ipynb`

The notebook will contain explanatory Markdown cells, executable Python cells, validation messages, result tables, and plots. It will follow the progressive style of the supplied Colab reference while replacing its continuous toy function with the finite set of QA test cases.

## Runtime environments

The notebook will support two input paths:

1. Local execution searches for `scenarios/firebase_chat/scenario.xlsx` relative to the repository and notebook.
2. Google Colab displays a file-upload control when the workbook is not found locally.

Dependencies will be installed from an explicit setup cell. The notebook will not require API keys. Multilingual E5 will run through a public pretrained model and cache its embeddings after the first encoding pass.

## Workbook loading and validation

The loader will locate the header by finding the row whose first cell is `TCS ID`. It will read these fields:

- `TCS ID`
- `Menu`
- `Submenu 1`
- `Submenu 2`
- `Test Case Scenario`
- `Test Step`
- `Expected Result`
- `Test Type`
- `User`
- `Time Testing`

The notebook will validate that identifiers are unique, the required columns exist, dummy bug identifiers are present in the workbook, and time values can be converted to minutes. `TCS ID` remains a join key and is never a predictive feature.

## Fixed dummy oracle

One configuration cell will expose an editable list:

```python
DUMMY_BUG_IDS = [
    # valid TCS IDs selected before running the experiment
]
```

The list is fixed for a run and shared by every encoding method. It is converted internally to a hidden `confirmed_bug_dummy` label for all 69 test cases. The selector receives a label only after it selects the corresponding test case.

Dummy bug placement is not randomized. The random baseline randomizes only the order of the remaining test cases. A fixed seed makes that baseline reproducible.

## Representations under comparison

The notebook will create three independent representations:

1. One-hot encoding of `Menu`, `Submenu 1`, `Submenu 2`, `Test Type`, and `User`.
2. TF-IDF over a labeled text serialization of the scenario, steps, expected result, and contextual fields, followed by Truncated SVD. The component count will be bounded by the available rows and vocabulary.
3. `intfloat/multilingual-e5-large-instruct` embedding of the same labeled text serialization. The task instruction will be fixed. Embeddings will be normalized and computed once.

All representations will be converted to finite numeric matrices with one row per test case. The notebook will print their shapes and check for NaN or infinite values.

## Sequential Bayesian simulation

The initial observations will contain one deterministic test case from every `Menu`, selected by sorted `TCS ID`. This satisfies the agreed minimum of one test per feature before adaptive selection begins. Every encoding method and the random baseline receive the same initial test cases.

For the first notebook experiment, a Gaussian Process regressor will serve as a transparent surrogate over dummy labels `0` and `1`. This is a practical BO simulation aligned with the supplied `skopt` example. The notebook will clearly label it as a Gaussian approximation to a binary outcome, not the final validated statistical model.

At each iteration:

1. Fit the surrogate only on labels revealed so far.
2. Predict posterior mean and standard deviation for untested candidates.
3. Compute a cost-aware upper-confidence-bound acquisition score.
4. Select the highest-scoring candidate with deterministic tie breaking.
5. Read that candidate's dummy label from the hidden oracle.
6. Append the revealed observation and repeat.

The notebook will generate a complete ordering of all candidates. This avoids choosing an arbitrary stopping time during the representation comparison. Stopping rules can be evaluated later against prefixes of the saved ordering.

## Fair-comparison controls

The following remain identical across methods:

- workbook and row set
- fixed dummy oracle
- initial test cases
- Gaussian Process configuration
- acquisition function and exploration parameter
- cost values
- deterministic tie breaking
- random seed

Only the numeric representation changes.

## Results and plots

The notebook will produce:

1. An initial true-dummy-oracle plot over the 69 test cases. Values are binary, with `1` marking a configured dummy bug and `0` marking no dummy bug. The plot is visible to the human but is explicitly isolated from surrogate training.
2. A table containing execution position, test ID, menu, estimated cost, acquisition value, predicted mean, predicted uncertainty, revealed dummy label, cumulative bug count, and cumulative cost.
3. A custom bug-discovery convergence plot showing the fraction or count of dummy bugs found against the number of executed tests.
4. Cumulative dummy bugs found against cumulative testing minutes.
5. Dummy bug discovery positions for each method.
6. Feature coverage progress by execution position.
7. A compact summary comparing early bug discovery at selected prefixes and total cost required to reveal the fixed dummy bugs.
8. Iteration snapshots modeled after the supplied Colab example. The left panel will show the hidden dummy truth, surrogate posterior mean, uncertainty band, and observations revealed so far. The right panel will show acquisition scores over the remaining candidates and mark the next selected candidate.

The snapshot panels will use a configurable method, defaulting to Multilingual E5, and several representative iterations beginning after the initial seed. Because the candidates occupy a multidimensional discrete space, the horizontal axis will be a fixed display order of test cases rather than a continuous optimization coordinate. Connecting lines are visual guides only. The notebook will state this directly and will not imply that values between adjacent test cases exist.

Plots will compare One-Hot, TF-IDF with SVD, Multilingual E5, and the random baseline. The notebook will display figures inline and save reproducible CSV and PNG artifacts under `experiment/bayesian/results` during local execution. In Colab it will create the same result directory under the session workspace and offer a ZIP download.

## Error handling

The notebook will stop with a clear message when the workbook is missing, required columns are absent, a dummy ID is invalid, no dummy bugs are configured, or a representation cannot be created. Failure to load the E5 model will identify the failed step without silently substituting another model.

## Verification

Verification will include:

- JSON and notebook-format validation
- execution of the non-E5 path with the real workbook
- validation of all 69 unique identifiers and editable dummy IDs
- assertions that unrevealed labels never enter surrogate training
- assertions that each method produces a permutation of all test IDs
- checks that cumulative bugs and cumulative costs never decrease
- confirmation that expected tables and figures are produced

Full E5 execution depends on downloading the pretrained model and available memory. If it cannot be executed in the local verification environment, the notebook cell will still be syntax checked and the limitation will be reported explicitly.

## Out of scope

This notebook will not execute Android tests, call MAS AI agents, modify the original workbook, train a new embedding model, or treat dummy findings as empirical evidence of real Android defects.
