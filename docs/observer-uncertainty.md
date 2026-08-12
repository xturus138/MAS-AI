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

## 3. DSE formula

Pure math lives in `core/uncertainty/dse.py` (single source of truth, natural log). Matches
Farquhar et al. 2024's discrete semantic entropy formula exactly, with no added rescaling:

- **Raw DSE:** `raw = -Σ p_k · ln(p_k)` where `p_k = count_k / effective_M`.
- **`effective_M`** is the number of **successfully-parsed samples** — the sum of the
  cluster counts — **not** the configured sample count `M`. A sample that failed to
  produce or parse a SEMANTIC_MAP for a widget does not contribute.

An earlier version of this code also computed a "normalized DSE" (`raw / ln(effective_M)`,
rescaled to 0-1) as a secondary, MAS-AI-invented convenience value. This was **removed on
2026-07-24** because the paper does not do this rescaling anywhere — keeping only `raw_dse`
means MAS AI's entropy number is exactly, not approximately, Farquhar et al. 2024's formula.

The service (`core/uncertainty/service.py`) marks `measurement_status="insufficient_samples"`
when `effective_M <= 1`, distinguishing a "could not measure" `0.0` from a genuine
single-cluster `0.0` (`measurement_status="ok"`).

Reference values (raw DSE only): `[5]` → `0.0`; `[3,2]` → `≈0.6730`; `[1,1,1,1,1]` → `ln 5 ≈ 1.6094`.

### 3.1 Independent literature confirmation

MAS AI's implementation is cross-checked against a second, independent source: *A Survey of
Uncertainty Estimation Methods on Large Language Models* (`Dokumen Kepake/Referensi Jurnal
Proksi/Riset Jepang/`). This paper is a survey, not the methodological reference — it does not
replace Farquhar et al. 2024 above — but it independently reproduces the same method under the
category "Semantic Clustering Methods" (its Figure 7, Section 3.5, and formula Appendix A.4),
and its own equation for discrete semantic entropy, `U = -Σ p(R_k) log p(R_k)` with `p(R_k) =
|R_k| / M`, is the same shape as `raw_dse()` above: entropy over per-cluster sample-frequency
counts, no normalization added.

Three points worth keeping straight when discussing this against both sources:

- **Figure 7's four steps (generate → cluster → cluster-probability → entropy) are the shared
  shape** of the whole "semantic clustering methods" family. They are not specific to DSE; Kuhn
  et al. 2023's plain semantic entropy uses the same four steps.
- **The two methods differ only in step 3** (how cluster probability is computed): Kuhn 2023
  averages the model's real length-normalized token probabilities per cluster; Farquhar 2024
  (MAS AI's method) uses plain frequency, `count_k / M`, disregarding token probabilities
  entirely — this is the actual meaning of "discrete" in the name.
- **Step 4's entropy formula is identical in both** methods; only its inputs differ, which is
  why the two produce different numbers from the same samples.
- The survey's own formulas use unsubscripted `log`, consistent with the natural-log convention
  `dse.py` and Farquhar 2024 both use — no unit conflict between the two sources.
- Neither the survey's main text nor its appendix documents the greedy
  representative-only comparison in the clustering step (Section 7 above / Section 2 of this
  file) — that implementation detail traces to Kuhn et al. 2023's original clustering algorithm
  specifically, not to this survey.

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
- **Sample-count (M) evaluation — PENDING.** `M=10` is adopted verbatim from Farquhar, Kossen,
  Kuhn, Gal, *Detecting hallucinations in large language models using semantic entropy* (Nature
  630:625-630, 2024) — "We use ten generations to compute entropy" — not derived from this
  project's own data. Still provisional for this domain until validated empirically.
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
OBSERVER_TEMPERATURE=0.1                # production-call temperature, see below
OBSERVER_UNCERTAINTY_ENABLED=false      # default OFF
OBSERVER_UNCERTAINTY_SAMPLES=10         # M, literature-grounded (see below), not domain-validated
OBSERVER_UNCERTAINTY_TEMPERATURE=1.0    # literature-grounded, NOT domain-validated
OBSERVER_UNCERTAINTY_MAX_WIDGETS=20     # cost cap; widgets beyond this are skipped and recorded
```

`M=10` and the `OBSERVER_TEMPERATURE=0.1` / `OBSERVER_UNCERTAINTY_TEMPERATURE=1.0` split both
follow Farquhar, Kossen, Kuhn, Gal, *Detecting hallucinations in large language models using
semantic entropy* (Nature 630:625-630, 2024) — their own protocol samples one low-temperature
(T=0.1) "best generation" production answer, plus ten additional samples at T=1.0 ("We use ten
generations to compute entropy, selected using analysis in Supplementary Fig. 2") for the
entropy estimate. This paper is MAS AI's single fixed methodological reference for the entire
DSE feature (consolidated 2026-07-23 — it independently contains the generation protocol, the
entailment-clustering algorithm, the DSE formula itself, the correctness-check prompt, and the
AUROC/rejection-accuracy/AURAC threshold metrics, so no other paper is needed for any step).
Chosen over sweeping the values on MAS AI's own data, since a full per-parameter sweep was
judged too costly for the scope of this work; see the Dokumen Kepake checklist for the citations
that justify why a sweep would normally be expected, and why adopting this paper's numbers
directly was chosen instead. Adopting the literature's values is not the same as validating them
for this Observer/Android-GUI domain — see section 5. Note: the paper's protocol also specifies
nucleus sampling (P=0.9) and top-K sampling (K=50) alongside T=1.0; MAS AI does not currently
configure these two (not all providers expose top-K), a documented gap, not a blocker.

When enabled, `M` fresh independent samples are always generated after the normal Observer
response — even on a cache hit. The cached/normal response is preserved for the workflow but
is never counted as a DSE sample.

Entailment clustering issues up to 2 judge LLM calls per (sample, existing cluster) per widget,
so cost scales with widget count. `OBSERVER_UNCERTAINTY_MAX_WIDGETS` caps how many widgets on a
screen get measured per step; any widget beyond the cap gets a `measurement_status:
"skipped_widget_cap"` entry instead of silently being dropped, and the manifest records
`max_widgets`, `widgets_measured`, and `widgets_skipped`.

**Raw DSE is the primary result** — it follows the paper directly (natural-log entropy over
cluster probabilities, unbounded, in nats). **Normalized DSE is a secondary, derived
presentation** (0-1, divided by `ln(effective_M)`) meant for dashboards/thresholds, not the
measurement of record.

## 8. Where artifacts are written

Per step, under `{step_dir}/uncertainty/` (`core/uncertainty/artifacts.py`):

- **`manifest.json`** — run-level: enabled flag, prompt hash, provider/model, judge model,
  configured + effective sample counts, provisional temperature and its status, `threshold`
  (null), `calibration_status`, raw sampled outputs, sampling failures, and the per-widget
  results.
- **`widgets.json`** — the per-widget results array: responses, clusters, cluster
  probabilities, pairwise entailment decisions, raw DSE, effective sample count, parse
  failures, and status fields. (No normalized/rescaled DSE — removed 2026-07-24 to match
  Farquhar et al. 2024's formula exactly; see section 3 above.)

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

The self-test verifies one cluster → raw `0.0`; `[3,2]` → raw ≈ `0.673`; five distinct
clusters → raw = `ln(5) ≈ 1.609`; and that no threshold-based or accepted/rejected/pass/fail
decision is produced.

## 10. Uncertainty Explanations (XAI layer)

When at least one widget in a step has `raw_dse > 0`, one additional LLM call
(reusing the Observer's own LLM client — no new provider config) generates a
plain-English explanation of what disagreed, using the existing cluster data.
This is a **reporting layer only** — it never affects DSE measurement, never
gates the workflow, and is subject to the same measurement-only guarantees as
DSE itself.

The explanation is:
- Printed to the CLI as `[Uncertainty] <explanation>` (or
  `[Uncertainty] No disagreement detected across N widgets.` when nothing
  needed explaining — this line requires no LLM call).
- Written to `{step_dir}/uncertainty/explanation.txt`, only when an
  explanation was successfully generated (absence signals either "nothing
  uncertain" or "generation failed" — both are non-fatal to the run).
- Collected into a `## Observer Uncertainty` section in the run's
  `run_overview.md`, listing every step that produced one, in step order.

The explanation is prohibited from using judgment/decision language
(uncertain, unreliable, failed, correct, pass, fail, accepted, rejected,
etc. — see `core/uncertainty/banned_words.py` for the exact list). If the
LLM's response uses a banned word, it is retried once with a stricter
reminder; if the retry still violates the rule, the explanation is discarded
entirely (same as any other generation failure) rather than shown with the
violation. See `docs/observer-uncertainty-explanations-design.md` for the
full design.
