# Observer DSE Uncertainty — Phase 1 Design (Measurement Only)

**Date:** 2026-07-22
**Status:** Approved design, pending implementation
**Scope:** Instrumentation only. DSE MUST NOT control the Decider, Executor, Reflector,
workflow routing, or the final test verdict.

## 1. Research boundaries (hard constraints)

These are non-negotiable and encoded throughout the design:

1. **Prompt not validated.** Do not rewrite or optimize `shared/prompts/observer_prompts.py`.
   Use the existing prompt as the current baseline. Record a **prompt hash** (runtime
   metadata) with every uncertainty result so future prompt experiments can be compared.
2. **Temperature not validated.** Sampling temperature is configurable and provisional.
   `1.0` is a literature-inspired reference starting value, explicitly marked
   `temperature_status="provisional_not_evaluated"`. The normal Observer call's behavior is
   unchanged (its temperature is not set by this feature).
3. **Threshold unknown.** Never hardcode a threshold. Never classify outputs as certain,
   uncertain, accepted, rejected, pass, or fail. Only calculate and record raw and normalized
   DSE. Store `threshold=null`, `calibration_status="not_calibrated"`.

## 2. Goal

Measure the Observer's *semantic self-consistency* on a given screen by sampling its semantic
map M times and computing Discrete Semantic Entropy (DSE) per widget. Low DSE means the
Observer produces semantically consistent descriptions across samples — it does **not** mean
the description is correct. This is a consistency/uncertainty signal, not a correctness signal.

## 3. Architecture

One source of truth for uncertainty behavior, shared by the production Observer and the
standalone runner.

```
core/uncertainty/
├── __init__.py
├── config.py                 # UncertaintyConfig dataclass
├── request_builder.py        # ObserverSemanticRequestBuilder (+ runtime prompt_hash)
├── semantic_parser.py        # parse SEMANTIC_MAP text -> {element_id: semantic_string}
├── clusterer.py              # SemanticClusterer (ABC) + EntailmentClusterer
├── dse.py                    # pure math: raw_dse(counts), normalized_dse(counts)
├── service.py                # ObserverUncertaintyService (orchestrates the pipeline)
└── artifacts.py              # write uncertainty JSON under {step_dir}/uncertainty/

shared/prompts/entailment_prompts.py   # judge prompt, SEPARATE from observer_prompts.py

tests/
├── run_observer_uncertainty.py         # standalone runner + --self-test (single entry point)
├── mock_clusterer.py                   # MockClusterer (test-only, injected in --self-test)
└── test_observer_uncertainty.py        # focused standalone tests (project convention)
```

Relationship (single shared service; no duplicate DSE implementations):

```
ObserverAgent ─┐
               ├─► ObserverUncertaintyService ─► SemanticClusterer (Entailment | Mock[test])
run_observer_  ┘         ▲                     ─► dse.py (pure functions)
uncertainty.py           └─ ObserverSemanticRequestBuilder (also used by the normal Observer call)
```

`ObserverSemanticRequestBuilder` extracts the message-construction logic currently inline in
`agents/observer_agent.py` (~lines 538–567). The Observer's normal call is refactored to use
this builder too, so future prompt/format changes automatically reach both the production path
and the standalone runner. A test asserts both paths construct the service via the same class
with the same builder — enforcing the dynamic-synchronization requirement.

## 4. Configuration

Env-driven, following `shared/config.py` conventions. Added to `shared/config.py` and
`.env.example`:

```
OBSERVER_UNCERTAINTY_ENABLED=false     # default OFF; disabled = zero behavior change
OBSERVER_UNCERTAINTY_SAMPLES=5         # M, provisional
OBSERVER_UNCERTAINTY_TEMPERATURE=1.0   # provisional, literature-inspired, NOT validated
```

- Sample count and temperature are provisional configuration values, not validated research
  conclusions.
- `prompt_hash` is **runtime metadata** produced by `ObserverSemanticRequestBuilder`, NOT a
  configuration value.
- Entailment judge reuses the Observer LLM client/config for Phase 1. The judge model is
  recorded in artifacts so a dedicated judge model can be compared later. The judge **prompt**
  is fully separate from the Observer prompt.

## 5. Data flow

### Disabled (default)
`analyze()` runs exactly as today. The only change: its normal LLM call goes through
`ObserverSemanticRequestBuilder.build()` instead of inline assembly — identical messages,
identical single call, **zero** extra LLM calls, identical return value. Backward-compatible.

### Enabled
After the normal Observer response is available (fresh OR cache hit) and stored:

```
1. builder  = ObserverSemanticRequestBuilder(system_prompt, few_shot, human_template, output_contract)
   messages  = builder.build(scenario_desc, navigation_context, elements_json, img_b64)
   prompt_hash = builder.prompt_hash          # runtime metadata

2. service = ObserverUncertaintyService(llm, clusterer=EntailmentClusterer(llm), cfg)
   result  = service.measure(messages, prompt_hash, widgets, step_dir)
      a. SAMPLE:  M independent llm.invoke(messages, temperature=cfg.temperature)
                  - provider rejects temperature param -> abort with clear error naming provider
                  - each failed sample recorded as a failure; never fabricated
      b. PARSE:   each raw sample's SEMANTIC_MAP -> {element_id: semantic_string}
      c. GATHER:  per widget, collect that widget's semantic strings across successful samples
      d. CLUSTER: greedy context-aware bidirectional-entailment clustering per widget;
                  raw pairwise decisions saved
      e. PROB:    p_k = count_k / effective_M
      f. DSE:     raw = -Σ p_k·ln(p_k);  normalized = raw / ln(effective_M)
      g. STATUS:  threshold=null, calibration_status="not_calibrated",
                  temperature_status="provisional_not_evaluated"

3. artifacts.write(...) -> {step_dir}/uncertainty/*.json
4. Return: normal Observer state unchanged; optional AgentState field
   `uncertainty_artifact_dir` (path only). No downstream agent reads it.
```

**Cache rule:** the cached/normal response is preserved for the workflow but is **never**
counted as a DSE sample. When enabled, M fresh independent samples are always generated, even
on a cache hit.

**Independence:** the normal Observer response and the M DSE samples are strictly separate.
No sample is a copy of the normal response.

## 6. DSE math (`core/uncertainty/dse.py`)

Pure, dependency-free, deterministic. Single source of truth for the formulas.

```python
import math

def raw_dse(cluster_counts: list[int]) -> float:
    effective_m = sum(cluster_counts)
    if effective_m <= 0:
        return 0.0
    entropy = 0.0
    for c in cluster_counts:
        if c <= 0:
            continue
        p = c / effective_m
        entropy -= p * math.log(p)     # natural log
    return entropy

def normalized_dse(cluster_counts: list[int]) -> float:
    effective_m = sum(cluster_counts)
    if effective_m <= 1:
        return 0.0
    return raw_dse(cluster_counts) / math.log(effective_m)
```

- `p_k` and normalization use **`effective_M`** (successfully-parsed samples), NOT configured M.
- `measurement_status` is set by the **service**, not the math:
  - `effective_M <= 1` -> `0.0` numerically AND `measurement_status="insufficient_samples"`
    (distinct from a genuine single-cluster `0.0`, which is `measurement_status="ok"`), so
    "could not measure" is never read as "confidently consistent".

Verified against required values:
- `[5]` -> raw `0.0`, normalized `0.0`
- `[3,2]` (M=5) -> raw ≈ `0.6730`, normalized ≈ `0.4182`
- `[1,1,1,1,1]` -> raw `ln5 ≈ 1.6094`, normalized `1.0`
- `[]` / effective_M<=1 -> `0.0` with `insufficient_samples`

## 7. Semantic clustering

```python
class SemanticClusterer(ABC):
    @abstractmethod
    def cluster(self, responses: list[str], context: WidgetContext) -> ClusterResult: ...

class EntailmentClusterer(SemanticClusterer):
    """Context-aware bidirectional entailment via LLM judge. Greedy against representatives.
    A joins cluster C  <=>  entails(A, rep) AND entails(rep, A), both within widget context."""
```

- **Greedy:** response 1 seeds cluster 1 (representative). Each later response is tested against
  each existing cluster representative; joins the first mutual-entailment match, else opens a
  new cluster.
- **Bidirectional requirement:** both directions must return `entailment` to merge. `neutral` or
  `contradiction` in either direction keeps them separate.
- **Context-aware:** the judge receives screen description + widget id/text/role, not just A and
  B. That context is recorded with each pairwise decision.
- **Judge output contract:** minimal machine-parseable `entailment` | `neutral` | `contradiction`.
- **Audit:** all raw pairwise decisions saved to artifacts.
- **MockClusterer** lives in `tests/`, injected in `--self-test`. It exercises the real `dse.py`
  and the real service flow with no API call.
- **No new dependency.** Exact lexical match is available ONLY as a documented deterministic
  testing helper/fallback — never substituted for the research implementation.

## 8. Output artifacts (`{step_dir}/uncertainty/`)

Run-level manifest + per-widget results. Contains:

- enabled status; timestamp; observer provider + model; judge model; prompt hash/version;
  configured sample count; effective sample count; provisional temperature +
  `temperature_status`; `threshold: null`; `calibration_status`; `measurement_status`;
- raw sampled outputs; parsed response per widget ID; semantic clusters + members; cluster
  probabilities; pairwise entailment decisions (with context); raw DSE; normalized DSE;
  parsing/sampling failures.

No API keys, tokens, or `.env` contents are ever written.

Per-widget result shape:

```json
{
  "element_id": 11,
  "responses": [],
  "clusters": [],
  "raw_dse": 0.0,
  "normalized_dse": 0.0,
  "sample_count": 5,
  "effective_sample_count": 5,
  "temperature": 1.0,
  "temperature_status": "provisional_not_evaluated",
  "temperature_application": "requested_not_verified",
  "threshold": null,
  "calibration_status": "not_calibrated",
  "measurement_status": "ok"
}
```

## 9. AgentState

Add at most an optional `uncertainty_artifact_dir` (path string) to `AgentState`. No downstream
agent depends on it. Do not add uncertainty scores to state in a way that could influence
routing or verdicts.

## 10. Standalone runner (`tests/run_observer_uncertainty.py`)

Single entry point. Contains ONLY: CLI arg handling, loading existing artifacts, constructing
the shared service, invoking it, displaying/saving results. No formulas, prompts, parsers,
clustering, or sampling loops are copied here.

Real modes:
```
python tests/run_observer_uncertainty.py --step-dir "outputs\runs\predefined\...\steps\001"
python tests/run_observer_uncertainty.py --image "path\annotated.png" --elements "path\merged.json" --output-dir "outputs\uncertainty_test"
```
- Loads existing `annotated.png`, `merged.json`, and any screen/scenario context.
- Uses current Observer provider/model config and the shared request builder.
- Runs uncertainty without starting the device or the main workflow.
- Writes the same artifacts as production.
- Clear errors on missing inputs. Never prints secrets. Clearly displays that prompt,
  temperature, sample count, and threshold are not validated.

Offline self-test mode (no real API calls):
```
python tests/run_observer_uncertainty.py --self-test
```
- Injects deterministic sample responses / MockClusterer into the SAME
  `ObserverUncertaintyService`.
- Verifies: one cluster -> normalized `0.0`; `[3,2]` -> raw ≈ `0.673`, normalized ≈ `0.418`;
  five clusters -> normalized ≈ `1.0`; no threshold-based decision produced.
- Tests the shared production calculation code — not a copied formula.

## 11. Temperature enforcement (Phase 1)

Verifying a provider *honored* temperature is impossible via API (responses don't echo
effective temperature). Enforcement level:

- If the API call **rejects/errors** on the temperature param -> abort that sampling run with a
  clear error naming the provider.
- Silent ignoring cannot be detected, so provider + model + temperature are recorded in every
  artifact and this limitation is documented in `docs/observer-uncertainty.md`, keeping results
  auditable.
- Every artifact records `temperature_application="requested_not_verified"` (NOT
  "successfully_applied"), because rejection-only enforcement cannot confirm the provider
  honored the requested temperature. This is distinct from `temperature_status`
  ("provisional_not_evaluated"), which concerns the *value* being unvalidated, not whether it
  was applied.

## 12. Testing requirements

Focused tests (project standalone convention; no assumption of a pytest suite; no live calls):

1. Counts `[5]` -> raw and normalized `0.0`.
2. Counts `[3,2]` (M=5) -> raw ≈ `0.673`, normalized ≈ `0.418`.
3. Counts `[1,1,1,1,1]` -> normalized ≈ `1.0`.
4. `M=1` and empty-input handling (with `insufficient_samples`).
5. Bidirectional entailment required before joining a cluster.
6. Missing widget IDs and malformed Observer outputs.
7. Partial sample failure recorded without fabricating responses; DSE over `effective_M`.
8. Disabled mode preserves existing behavior and LLM call count.
9. Enabled mode produces auditable uncertainty artifacts.
10. No threshold-based decision is made anywhere.
11. Shared-service test: `ObserverAgent` and standalone runner both use the same
    `ObserverUncertaintyService` / builder (no independent DSE implementation).

## 13. Documentation

`docs/observer-uncertainty.md` explaining: semantic clustering; raw DSE; normalized DSE; why
low DSE means semantic consistency, not correctness; current experimental status (prompt
selection pending, temperature evaluation pending, threshold calibration pending); how to
enable; where artifacts are written; the temperature-enforcement limitation.

`IDEA.md` updated with actual implementation status after completion.

## 14. Acceptance criteria

- Uncertainty toggled via config; current Observer workflow backward-compatible; repeated
  outputs preserved; semantic clustering auditable; raw + normalized DSE correct; no threshold
  or reliability decision invented; prompt + temperature explicitly marked unvalidated; focused
  tests pass; docs accurate; no secrets or unrelated user changes modified.

## 15. Remaining research work (out of scope for Phase 1)

Prompt evaluation/selection; temperature evaluation; sample-count (M) evaluation; threshold
calibration. Each depends on the measurement instrumentation built here.
