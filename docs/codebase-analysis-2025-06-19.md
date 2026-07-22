# MAS AI Codebase Analysis — June 19, 2025

> Comprehensive review of the multi-agent Android GUI testing framework.
> Covers: architecture, bugs, code quality, and risks — without breaking the existing workflow.

---

## 🔴 Critical (Will Break or Degrade the Workflow)

### 1. `scenario.xlsx` Deleted from Root — Runner May Crash

The root `scenario.xlsx` was deleted (shown in git diff). The new `SCENARIO_DIR=scenarios/notes` is set in `.env`, and `scenarios/notes/scenario.xlsx` exists. However, the `.env` comments say each scenario folder must contain a `config.json` — but **no code reads `config.json` anywhere**. This is a documentation-vs-reality mismatch.

**Impact:** If `SCENARIO_DIR` points to a folder without `scenario.xlsx`, the runner prints an error and exits. Currently `scenarios/notes/` has the xlsx, so it works — but the `config.json` expectation is misleading.

### 2. Observer Cache Bug: Stagnation Counter Increments on Cache Hit

In `observer_agent.py:459`:

```python
if cache_hit:
    raw_res = cached_analysis
    new_stagnation_count = state.get("stagnation_count", 0) + 1  # <-- BUG
```

Every cache hit looks like **stagnation** to the system. The orchestrator may abort the scenario thinking the UI is stuck, when really the observer is just correctly reusing analysis for an unchanged screen.

**Impact:** False-positive scenario aborts when the UI is legitimately stable across steps.

### 3. Observer Cache Misses on Most Sub-Step Transitions

The cache key now includes `observer_analysis_sub_step == current_sub_step_index` (line 454). But the observer runs once per cycle, and the sub-step index advances between cycles. The cache only hits during **retries of the same sub-step**, not across different sub-steps — even if the UI is identical.

**Impact:** The `OBSERVER_CACHE_ENABLED` feature is far less useful than intended.

### 4. `"input"` in `_NO_UI_CHANGE_REQUIRED` — Skips Verification

In `reflector_agent.py:21`:

```python
_NO_UI_CHANGE_REQUIRED = frozenset({"input", "scroll", "none"})
```

Typing text into a field **does change the UI** (text appears). The reflector skips the UI change check for input actions, potentially missing that the input didn't actually register.

**Impact:** Input actions may be marked PASSED without confirming the text actually appeared.

---

## 🟠 Medium Severity (Inefficiency or Incorrect Behavior)

### 5. Duplicated JSON Extraction Code Across 4 Files

The exact same `_extract_json_from_llm_output()` method (brace-matching, thinking-tag parsing, etc.) is copy-pasted in:

| File | Lines |
|------|-------|
| `agents/decider_agent.py` | 76–129 |
| `agents/reflector_agent.py` | 225–313 |
| `core/workflow/predefined/orchestrator.py` | 76–150 |

Any bug fix must be applied in 3+ places.

### 6. `_invoke_with_recovery` Also Duplicated

The JSON recovery retry logic is duplicated across:

| File | Lines |
|------|-------|
| `agents/decider_agent.py` | 248–324 |
| `agents/reflector_agent.py` | 321–400 |
| `core/workflow/predefined/orchestrator.py` | 152–237 |

### 7. `_encode_image` Duplicated

Both `observer_agent.py:30-47` and `reflector_agent.py:75-92` have identical image encoding (resize → WebP → JPEG fallback → base64).

### 8. Autonomous Mode Has No Retry Context for Decider

The `decider_agent.py` now injects retry context (lines 352–360), but this only works in **predefined mode**. In autonomous mode, `step_retry_count` is never incremented — the autonomous orchestrator uses `stagnation_count` instead. The decider never learns from past failures.

### 9. Recovery Rate Metric Is Always 0% or 100%

In `recorder_agent.py:239-243`:

```python
successful_recoveries = recovery_attempts - (0 if is_completed else recovery_attempts)
```

If completed → `recovery_attempts - 0 = 100%`. If not → `recovery_attempts - recovery_attempts = 0%`. Never a meaningful intermediate value.

### 10. Autonomous Orchestrator Has No JSON Recovery

The predefined orchestrator has `_invoke_with_recovery` and `_extract_json_from_llm_output`. The autonomous orchestrator doesn't. If the LLM returns malformed JSON for `AutonomousPlan`, the entire run crashes with an unhandled exception.

---

## 🟡 Low Severity (Code Quality / Maintainability)

### 11. Hardcoded Magic Numbers Throughout

| Value | Location | Purpose |
|-------|----------|---------|
| `720` / `480` | observer/reflector | Image max height |
| `25` | `observer_agent.py:153` | `boxes_nearby` threshold |
| `40` | `observer_agent.py:69` | OCR merge distance |
| `0.65` | `observer_agent.py:88` | Keyboard detection ratio |
| `0.4` | `observer_tools.py:47` | OCR confidence threshold |
| `50` | `observer_tools.py:92` | Min contour area |
| `0.80` | `observer_tools.py:94` | Max contour area ratio |

### 12. `FigmaAdapter._extract_transitions` Uses Regex on Raw JSON

In `figma_adapter.py:207-212`:

```python
raw = json.dumps(context)
pattern = r'"name"\s*:\s*"([^"]+)"[^}]*?"transitionNodeID"\s*:\s*"([^"]+)"'
```

This regex-parses a JSON dump instead of traversing the parsed structure. Fragile — will break if Figma's API response format changes.

### 13. `save_composite_gold_standard` Hardcodes `arial.ttf`

In `figma_adapter.py:297-298`, it tries `arial.ttf` and falls back to `ImageFont.load_default()`. On Linux (CI/CD), Arial won't be available, and the default font is tiny.

### 14. ActiveRetrieval Doesn't Search Knowledge Vault

In `active_retrieval.py:90-96`, the `tasks` dict includes core, episodic, semantic, procedural, and resource — but **not the Knowledge Vault**. The vault store exists but is never queried.

### 15. Semantic Memory Is Never Written (Dead Feature)

In `observer_agent.py:560`:

```python
if semantic_entries and getattr(self.memory, "write_semantic_widgets", False):
```

`write_semantic_widgets` is never set to `True` anywhere. The entire Semantic Memory Store is never populated.

### 16. `FigmaAdapter.find_flow_start_node` Always Returns `None`

Marked as deprecated and always returns `None` (line 129-131). Still called in `runner.py:252` for bridge navigation — the bridge falls back to `compute_bridge()`, but the dead code is misleading.

### 17. `scenarios/notes/` Has No `config.json`

The `.env` comments say each scenario folder must contain `config.json`, but `scenarios/notes/` only has `scenario.xlsx`. No code reads `config.json`.

### 18. MIRIX Stores Not Fully Closed

`memory.close()` only closes episodic and semantic (SQLite). The JSON-based stores (core, procedural, resource, vault) hold file handles but are never explicitly closed.

---

## Summary: Suggested Fix Order

| Priority | What | Why |
|----------|------|------|
| **P0** | Fix stagnation counter on cache hit (#2) | Prevents false scenario aborts |
| **P0** | Verify `scenarios/notes/` works end-to-end (#1) | Runner won't start otherwise |
| **P1** | Add JSON recovery to autonomous orchestrator (#10) | Autonomous mode crashes on bad LLM output |
| **P1** | Extract shared `_extract_json_from_llm_output` (#5) | 3 copies, maintenance burden |
| **P1** | Extract shared `_invoke_with_recovery` (#6) | 3 copies, maintenance burden |
| **P2** | Remove `"input"` from `_NO_UI_CHANGE_REQUIRED` (#4) | Missed input verification |
| **P2** | Enable semantic memory writes (#15) | Feature is dead code |
| **P2** | Add Knowledge Vault to ActiveRetrieval (#14) | Missing feature |
| **P3** | Extract `_encode_image` to shared utility (#7) | Cleanup |
| **P3** | Fix recovery rate metric (#9) | Meaningless metric |

---

*Generated by Claude Code — June 19, 2025*
