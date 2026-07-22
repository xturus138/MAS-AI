# Predefined Workflow: Diagram vs. Implementation Gaps

Source: architecture diagram (Figma MCP + Test Case Document → Orchestrator → Observer →
Decider → Executor → Reflector → Recorder, with a shared "Short Term Memory" box) compared
against the actual `predefined` mode implementation as of 2026-07-22.

The diagram is correct at the agent-box level (which agents exist, general loop order). The
gaps below are places where the diagram simplifies or omits real plumbing — worth fixing
either by updating the diagram or by tightening the code to match, depending on which is the
source of truth for the thesis.

## 1. Recorder timing

- **Diagram:** Recorder sits inside the per-cycle loop, checks the result, hands back to
  Orchestrator to continue.
- **Code:** Recorder is NOT a graph node. The 4-agent loop (Observer → Decider → Executor →
  Reflector) runs by itself every cycle. Recorder is only invoked once, after the whole
  scenario's graph finishes, via `recorder.finalize_run_metrics()`.
  - `core/workflow/predefined/runner.py:191`

## 2. Memory box oversimplified

- **Diagram:** one "Short Term Memory" box with 5 items (current screenshot, historical
  screenshot, scenario info, app info, historical operation list).
- **Code:** MIRIX memory system has 6 distinct stores, each with its own backend:
  Core (JSON), Episodic (SQLite+FTS5), Semantic (SQLite+FTS5), Procedural (JSON),
  Resource (JSON+disk), Knowledge Vault (JSON). See `memory/schemas.py`, `memory/stores/`.

## 3. Bridge navigation — missing entirely from the diagram

- Between consecutive scenarios, the app is often left on the wrong screen for the next
  scenario to start from. The orchestrator computes extra navigation steps
  (`compute_bridge`) and injects them ahead of the next scenario's sub-steps.
  - `core/workflow/predefined/orchestrator.py:344` (`compute_bridge`)
  - `core/workflow/predefined/runner.py:234-245` (injection into `next_scenario["sub_steps"]`)
- No box/arrow for this exists in the diagram.

## 4. Retry / failure handling hidden behind the loop-back arrow

- **Diagram:** one plain arrow loops back to Orchestrator.
- **Code:** that loop-back hides real decision logic in `orchestrate()`:
  - Reflector PASS → advance to next step, reset retry count
  - Reflector FAIL → retry, capped at 3 attempts
  - `[SYSTEM_ERROR]` in reflector reasoning → treated as technical failure, NOT counted as
    an app failure, advances anyway
  - Retries exceeded (> 3) → abort the whole scenario (`is_completed=True`,
    `stagnation_count=99`)
  - `core/workflow/predefined/orchestrator.py:409-451`

## Action items (unchecked = still needs a decision)

- [ ] Decide whether the diagram should be updated to show Recorder as post-run-only, or
      whether Recorder should become an actual graph node to match the diagram.
- [ ] Decide whether to expand the memory box in the diagram to show all 6 MIRIX stores.
- [ ] Add a "Bridge Navigation" step/box between scenarios in the diagram.
- [ ] Add retry/error-branch detail near the Reflector → Orchestrator arrow (or note it
      as intentionally abstracted for the thesis diagram).
