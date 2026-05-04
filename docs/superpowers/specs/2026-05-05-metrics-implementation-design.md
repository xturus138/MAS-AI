# Metrics Implementation Design
**Date:** 2026-05-05
**Branch:** feature/modular-workflow

---

## Goal

Implement five research metrics into both the predefined and autonomous workflows to enable a consistent, fair, comparative analysis between the two orchestration strategies.

---

## Metrics & Formulas

All five metrics are emitted under a `"research_metrics"` key inside `final_metrics.json` at the end of each run.

| Metric | Formula | Unit |
|---|---|---|
| Coverage Rate (C) | `steps_completed_count / len(sub_steps) × 100` | % |
| Decision Accuracy Initial (Acc_1) | `reflector_first_pass_count / total_first_verify_calls × 100` | % |
| Decision Accuracy Final (Acc_f) | `steps_completed_count / total_first_verify_calls × 100` | % |
| Verification Pass Rate | `reflector_pass_count / total_reflector_calls × 100` | % |
| Widget Localization Effectiveness | `widget_lookup_success / (widget_lookup_success + widget_lookup_fail) × 100` | % |
| Time Overhead | `end_time − start_time` | seconds |
| Token Consumption | summed from LLM session log files | tokens |

All seven metrics are emitted together under `"research_metrics"` in `final_metrics.json`.

---

## New State Fields (`core/models/state.py`)

Eight new fields added to `AgentState`:

```python
# Coverage & decision accuracy
steps_completed_count: int        # sub-steps passed; incremented whenever reflector passed=True
total_reflector_calls: int        # total ReflectorAgent.evaluate() invocations
reflector_pass_count: int         # total passes (passed=True)
total_first_verify_calls: int     # reflector calls flagged as first-attempt (not recovery)
reflector_first_pass_count: int   # first-attempt passes

# First-attempt flag — set by ORCHESTRATOR before each reflector dispatch
is_first_verify_attempt: bool

# Widget localization
widget_lookup_success: int        # widget ID resolved to coordinates
widget_lookup_fail: int           # widget ID not found in current widget list
```

**Initial values in both runners:** all int fields = `0`, `is_first_verify_attempt = True`.

---

## Changes Per File

### `core/models/state.py`
Add the 8 fields above.

---

### `agents/executor_agent.py`

In `execute()`, after widget resolution for `click`, `long_click`, `input` actions only:

```python
if target_widget:
    widget_lookup_success = state.get("widget_lookup_success", 0) + 1
else:
    widget_lookup_fail = state.get("widget_lookup_fail", 0) + 1
```

`scroll`, `press_back`, `press_home`, `press_enter`, `start_app` do not use widget IDs — excluded from localization counting.

Include `widget_lookup_success` and `widget_lookup_fail` in the return dict.

---

### `agents/reflector_agent.py`

At the end of `evaluate()`, before the return dict:

```python
total_reflector_calls = state.get("total_reflector_calls", 0) + 1
reflector_pass_count = state.get("reflector_pass_count", 0) + (1 if passed else 0)
is_first = state.get("is_first_verify_attempt", True)
total_first_verify_calls = state.get("total_first_verify_calls", 0) + (1 if is_first else 0)
reflector_first_pass_count = state.get("reflector_first_pass_count", 0) + (1 if is_first and passed else 0)
```

Include all four counters in the return dict.

---

### `core/workflow/predefined/orchestrator.py`

In `orchestrate()`, when `sender in ["reflector", "recorder"]`:

```python
is_first_verify_attempt = (retry_count == 0)   # True before any retry on this step

if last_passed:
    steps_completed_count = state.get("steps_completed_count", 0) + 1
```

Include `is_first_verify_attempt` and `steps_completed_count` in `update_data`.

---

### `core/workflow/autonomous/orchestrator.py`

In `orchestrate()`:

**Set `is_first_verify_attempt`** when dispatching `VERIFY`:
```python
# Recovery: sender is reflector AND last attempt failed
is_first_verify = not (sender == "reflector" and not last_reflector_passed)
```
Pass `is_first_verify_attempt = is_first_verify` in the Command update whenever `target_node == "reflector_node"`.

**Increment `steps_completed_count`** when reflector has just passed:
```python
if sender == "reflector" and last_reflector_passed:
    steps_completed_count = state.get("steps_completed_count", 0) + 1
```
Include `steps_completed_count` in the Command update.

---

### `agents/recorder_agent.py`

In `finalize_run_metrics()`, compute and append a `"research_metrics"` block:

```python
sub_steps_total = len(state.get("sub_steps", []))
steps_completed = state.get("steps_completed_count", 0)
total_reflector = state.get("total_reflector_calls", 0)
reflector_passes = state.get("reflector_pass_count", 0)
first_verify_total = state.get("total_first_verify_calls", 0)
first_verify_passes = state.get("reflector_first_pass_count", 0)
lookup_ok = state.get("widget_lookup_success", 0)
lookup_fail = state.get("widget_lookup_fail", 0)
start_time = state.get("start_time", 0)
end_time = state.get("end_time", 0)
duration = round(end_time - start_time, 2) if end_time > start_time else 0

# Token consumption: reuse the existing session-log summation logic
total_tokens = 0
total_cost_usd = 0.0
# (same log-scanning loop already in finalize_run_metrics)

def pct(num, den):
    return round((num / den) * 100, 1) if den > 0 else None

research_metrics = {
    "coverage_rate":                     pct(steps_completed, sub_steps_total),
    "decision_accuracy_initial_acc1":    pct(first_verify_passes, first_verify_total),
    "decision_accuracy_final_accf":      pct(steps_completed, first_verify_total),
    "verification_pass_rate":            pct(reflector_passes, total_reflector),
    "widget_localization_effectiveness": pct(lookup_ok, lookup_ok + lookup_fail),
    "time_overhead_seconds":             duration,
    "token_consumption":                 total_tokens,
}
```

`None` is emitted when denominator is zero (e.g., no widget-ID actions taken), making missing data explicit rather than a misleading 0%.

Token and duration values are the same computed values already used at the top-level of `final_metrics.json` — no double-computation, just referenced together in the `research_metrics` block.

---

### `core/workflow/predefined/runner.py` & `core/workflow/autonomous/runner.py`

Add to `initial_state`:
```python
"steps_completed_count":      0,
"total_reflector_calls":      0,
"reflector_pass_count":       0,
"total_first_verify_calls":   0,
"reflector_first_pass_count": 0,
"is_first_verify_attempt":    True,
"widget_lookup_success":      0,
"widget_lookup_fail":         0,
```

---

## Interpretation Guide

**Coverage Rate (C)**
Both modes use `len(sub_steps)` as the denominator — the same fixed yardstick from `scenario.xlsx`. A value < 100% on a SUCCESS run is impossible. Values below 100% on STAGNATED/FAILED runs show how far the agent progressed before stopping.

**Acc_1 vs Acc_f**
`Acc_f − Acc_1` quantifies the contribution of self-correction. A large gap (e.g., Acc_1=50%, Acc_f=80%) means the recovery loop is doing significant work. A gap near zero means first decisions were already reliable.

**Verification Pass Rate**
Sanity check: monitors raw reflector reliability across all calls including retries. Very low values (< 30%) suggest the reflector model is poorly calibrated, which would skew Acc_1 and Acc_f.

**Widget Localization Effectiveness**
Only `click`, `long_click`, `input` actions contribute. A lower value in autonomous mode indicates the planner is referencing widget IDs that the Observer didn't detect — a cross-agent coordination failure specific to LLM-driven planning.

**Time Overhead**
Wall-clock seconds from `start_time` to `end_time`. Direct proxy for tester productivity impact. Compare against the 3.82-hour manual QA baseline cited in the research context.

**Token Consumption**
Summed from all per-agent LLM session log files under `outputs/llm_logs/{session_id}/`. Measures the API cost of one full scenario run. Expected to be substantially higher in autonomous mode due to the additional orchestrator planning calls.

---

## Consistency Guarantees

- `steps_completed_count <= total_first_verify_calls` always (a step can only complete once).
- `Acc_1 <= Acc_f` always (first-pass subset ≤ eventual completions).
- No counter increments for actions that bypass widget resolution (`scroll`, back/home/enter, `start_app`).
- `is_first_verify_attempt` is set by the orchestrator — the agent that controls step advancement — not by the reflector, avoiding self-reporting bias.
