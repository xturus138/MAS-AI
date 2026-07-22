# Observer DSE Uncertainty (Phase 1)

**Status:** Measurement instrumentation only. Disabled by default. Discrete Semantic
Entropy (DSE) MUST NOT influence the Decider, Executor, Reflector, workflow routing, or
the final test verdict. See the full design in
[`docs/observer-dse-uncertainty-design.md`](observer-dse-uncertainty-design.md).

## 1. What DSE measures

DSE quantifies the Observer's **semantic self-consistency** on a single screen. The
Observer's semantic map is sampled `M` times, and per widget the resulting semantic
descriptions are clustered by meaning. DSE is the entropy over those clusters: it is high
when the Observer describes the same widget in many semantically different ways across
samples, and low when it converges on one meaning.

This is a **consistency/uncertainty signal, not a correctness signal** (see section 4).

## 2. Semantic clustering

Clustering (`core/uncertainty/clusterer.py`, `EntailmentClusterer`) is
**context-aware bidirectional entailment** decided by an LLM judge:

- **Greedy against representatives.** The first response seeds cluster 1 and becomes its
  representative (`members[0]`). Each later response is tested against each existing
  cluster's representative; it joins the first cluster it mutually entails, otherwise it
  opens a new cluster.
- **Bidirectional requirement.** Two strings merge only if `entails(A, rep)` **and**
  `entails(rep, A)` both return `entailment`. A `neutral` or `contradiction` in either
  direction keeps them in separate clusters.
- **Context-aware.** The judge receives the screen description plus the widget's
  `element_id`, `text`, and `role` — not just the two strings being compared.
- **Judge prompt is separate.** The entailment judge uses its own prompt in
  `shared/prompts/entailment_prompts.py` (`ENTAILMENT_SYSTEM_PROMPT`,
  `ENTAILMENT_HUMAN_TEMPLATE`), fully separate from the Observer prompt in
  `shared/prompts/observer_prompts.py`.
- **Raw pairwise decisions saved.** Every pairwise judgement (`a`, `b`, `a_entails_b`,
  `b_entails_a`, `merged`, `context`) is recorded in the artifacts for audit.

## 3. DSE formulas

Pure math lives in `core/uncertainty/dse.py` (single source of truth, natural log):

- **Raw DSE:** `raw = -Σ p_k · ln(p_k)` where `p_k = count_k / effective_M`.
- **Normalized DSE:** `normalized = raw / ln(effective_M)`, returning `0.0` when
  `effective_M <= 1`.
- **`effective_M`** is the number of **successfully-parsed samples** — the sum of the
  cluster counts — **not** the configured sample count `M`. A sample that failed to
  produce or parse a SEMANTIC_MAP for a widget does not contribute.

The service (`core/uncertainty/service.py`) marks `measurement_status="insufficient_samples"`
when `effective_M <= 1`, distinguishing a "could not measure" `0.0` from a genuine
single-cluster `0.0` (`measurement_status="ok"`).

Reference values: `[5]` → raw `0.0`, normalized `0.0`; `[3,2]` → raw ≈ `0.6730`,
normalized ≈ `0.4182`; `[1,1,1,1,1]` → raw `ln 5 ≈ 1.6094`, normalized `1.0`.

## 4. Low DSE means consistency, NOT correctness

**Low DSE means the Observer produced semantically consistent descriptions across
samples. It does NOT mean the description is correct.** The Observer can be confidently and
consistently wrong — describing a widget the same way every time while still
misidentifying it. DSE measures agreement of the model with itself, never agreement with
ground truth. Do not read low DSE as reliability, accuracy, or a pass signal.

## 5. Experimental status

All of the following are **PENDING** research work and are out of scope for Phase 1
(each depends on the measurement instrumentation built here):

- **Prompt selection — PENDING.** The Observer prompt is the current unvalidated baseline;
  it is not rewritten or optimized. A `prompt_hash` is recorded with every result so future
  prompt experiments can be compared.
- **Temperature evaluation — PENDING.** The sampling temperature value is unvalidated
  (`temperature_status="provisional_not_evaluated"`).
- **Sample-count (M) evaluation — PENDING.** The number of samples is provisional.
- **Threshold calibration — PENDING.** No threshold is ever hardcoded. Artifacts store
  `threshold: null` and `calibration_status: "not_calibrated"`. Outputs are never
  classified as certain/uncertain, accepted/rejected, or pass/fail.

## 6. Temperature enforcement limitation

Enforcement is **rejection-only**. Providers do not echo the effective temperature in their
responses, so it is impossible to confirm via the API that a provider actually honored the
requested temperature.

- If the provider **rejects or errors** on the temperature parameter, the sampling run
  aborts with a clear `TemperatureRejectedError` naming the provider.
- **Silent ignoring by a provider is undetectable via the API.** Because of this, provider,
  model, and temperature are recorded in every artifact for auditability.
- Every artifact records `temperature_application="requested_not_verified"` (never
  `"successfully_applied"`), because rejection-only enforcement cannot confirm the provider
  honored the value. This is distinct from `temperature_status`
  (`"provisional_not_evaluated"`), which concerns the *value* being unvalidated rather than
  whether it was applied.

## 7. How to enable

Configured via three env vars in `shared/config.py` (disabled by default; disabled means
zero behavior change to the existing Observer workflow):

```
OBSERVER_UNCERTAINTY_ENABLED=false     # default OFF
OBSERVER_UNCERTAINTY_SAMPLES=5         # M, provisional
OBSERVER_UNCERTAINTY_TEMPERATURE=1.0   # provisional, literature-inspired, NOT validated
```

When enabled, `M` fresh independent samples are always generated after the normal Observer
response — even on a cache hit. The cached/normal response is preserved for the workflow but
is never counted as a DSE sample.

## 8. Where artifacts are written

Per step, under `{step_dir}/uncertainty/` (`core/uncertainty/artifacts.py`):

- **`manifest.json`** — run-level: enabled flag, prompt hash, provider/model, judge model,
  configured + effective sample counts, provisional temperature and its status, `threshold`
  (null), `calibration_status`, raw sampled outputs, sampling failures, and the per-widget
  results.
- **`widgets.json`** — the per-widget results array: responses, clusters, cluster
  probabilities, pairwise entailment decisions, raw and normalized DSE, effective sample
  count, parse failures, and status fields.

Secrets (`api_key`, `token`, `authorization`, `apikey`, `access_token`) are stripped before
writing. No API keys, tokens, or `.env` contents are ever written.

## 9. How to run standalone

`tests/run_observer_uncertainty.py` is the single entry point; it constructs the same
production `ObserverUncertaintyService` and `ObserverSemanticRequestBuilder` (no duplicate
DSE implementation). It never prints secrets and always shows that prompt, temperature,
sample count, and threshold are not validated.

```bash
# Offline self-test — injected samples + MockClusterer, no real API calls
python tests/run_observer_uncertainty.py --self-test

# Real sampling from an existing step's artifacts (annotated.png + merged.json)
python tests/run_observer_uncertainty.py --step-dir "outputs\runs\predefined\...\steps\001"

# Real sampling from explicit inputs
python tests/run_observer_uncertainty.py --image "path\annotated.png" --elements "path\merged.json" --output-dir "outputs\uncertainty_test"
```

The self-test verifies one cluster → normalized `0.0`; `[3,2]` → raw ≈ `0.673`,
normalized ≈ `0.418`; five clusters → normalized ≈ `1.0`; and that no threshold-based or
accepted/rejected/pass/fail decision is produced.
