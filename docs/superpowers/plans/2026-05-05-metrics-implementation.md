# Research Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `"research_metrics"` block to `final_metrics.json` containing 7 metrics (Coverage Rate, Acc_1, Acc_f, Verification Pass Rate, Widget Localization Effectiveness, Time Overhead, Token Consumption) collected consistently across both predefined and autonomous workflows.

**Architecture:** Eight new counter/flag fields are added to `AgentState`. Each agent that owns an event increments its own counter (Executor → widget lookups, Reflector → call/pass counts). Both orchestrators set the `is_first_verify_attempt` flag and increment `steps_completed_count` on pass. The Recorder reads all counters at finalization and emits `research_metrics`.

**Tech Stack:** Python 3.x, LangGraph, TypedDict (`AgentState`), JSON output

---

## File Map

| File | Change |
|---|---|
| `core/models/state.py` | Add 8 new fields to `AgentState` |
| `agents/executor_agent.py` | Track widget lookup hits/misses |
| `agents/reflector_agent.py` | Track reflector call/pass counters |
| `core/workflow/predefined/orchestrator.py` | Set `is_first_verify_attempt`, increment `steps_completed_count` |
| `core/workflow/autonomous/orchestrator.py` | Set `is_first_verify_attempt`, increment `steps_completed_count` |
| `agents/recorder_agent.py` | Compute and emit `research_metrics` block |
| `core/workflow/predefined/runner.py` | Add 8 new fields to `initial_state` |
| `core/workflow/autonomous/runner.py` | Add 8 new fields to `initial_state` |

---

## Task 1: Extend AgentState with metric fields

**Files:**
- Modify: `core/models/state.py`

- [ ] **Step 1: Add 8 new fields to AgentState**

Open `core/models/state.py`. The current last field is `is_final_step: bool`. Add the new fields after it:

```python
    # Autonomous-mode fields
    orchestrator_instruction: str   # Current step instruction set by autonomous orchestrator
    observer_analysis_step: int     # Value of current_step when observer last ran (staleness tracking)
    is_final_step: bool             # Set by orchestrator when dispatching VERIFY for the final goal

    # Research metrics counters
    steps_completed_count: int          # incremented whenever reflector passed=True and system advances
    total_reflector_calls: int          # total ReflectorAgent.evaluate() invocations
    reflector_pass_count: int           # total passes (passed=True)
    total_first_verify_calls: int       # reflector calls flagged as first-attempt (not recovery retries)
    reflector_first_pass_count: int     # first-attempt passes
    is_first_verify_attempt: bool       # set by orchestrator before each reflector dispatch
    widget_lookup_success: int          # executor resolved widget ID to coordinates
    widget_lookup_fail: int             # executor could not find widget ID in widget list
```

- [ ] **Step 2: Verify the file parses cleanly**

```bash
python -c "from core.models.state import AgentState; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/models/state.py
git commit -m "feat: add 8 research metrics fields to AgentState"
```

---

## Task 2: Track widget localization in ExecutorAgent

**Files:**
- Modify: `agents/executor_agent.py`

- [ ] **Step 1: Add hit/miss tracking after widget resolution**

In `execute()`, find the block that resolves widget IDs (lines ~38–51). It currently looks like:

```python
        if action_type in ["click", "long_click", "input"]:
            target_id = plan.get("target_id", -1)
            
            target_widget = next((w for w in widgets if w.get("id") == target_id), None)
            
            if target_widget:
                bounds = target_widget.get("bounds", [0, 0, 0, 0])
                target_x = (bounds[0] + bounds[2]) // 2
                target_y = (bounds[1] + bounds[3]) // 2
                widget_text = target_widget.get("text", "(no text)")
                print(f"[Executor] Resolved ID {target_id} -> click=({target_x},{target_y}) | widget='{widget_text}'")
            else:
                lookup_error = f"ERROR: Target ID {target_id} not found in current UI state"
```

Replace with:

```python
        widget_lookup_success = state.get("widget_lookup_success", 0)
        widget_lookup_fail = state.get("widget_lookup_fail", 0)

        if action_type in ["click", "long_click", "input"]:
            target_id = plan.get("target_id", -1)
            
            target_widget = next((w for w in widgets if w.get("id") == target_id), None)
            
            if target_widget:
                bounds = target_widget.get("bounds", [0, 0, 0, 0])
                target_x = (bounds[0] + bounds[2]) // 2
                target_y = (bounds[1] + bounds[3]) // 2
                widget_text = target_widget.get("text", "(no text)")
                print(f"[Executor] Resolved ID {target_id} -> click=({target_x},{target_y}) | widget='{widget_text}'")
                widget_lookup_success += 1
            else:
                lookup_error = f"ERROR: Target ID {target_id} not found in current UI state"
                widget_lookup_fail += 1
```

- [ ] **Step 2: Include the counters in the return dict**

Find the `return` statement at the end of `execute()`. It currently returns:

```python
        return {
            "execution_result": result,
            "action_history": new_history,
            "previous_screenshot_path": current_screenshot,
            "screenshot_path": new_screenshot,
            "sender": "executor",
        }
```

Replace with:

```python
        return {
            "execution_result": result,
            "action_history": new_history,
            "previous_screenshot_path": current_screenshot,
            "screenshot_path": new_screenshot,
            "sender": "executor",
            "widget_lookup_success": widget_lookup_success,
            "widget_lookup_fail": widget_lookup_fail,
        }
```

Note: The early-return path for `plan.get("is_completed")` (no-action case) does not perform a widget lookup, so those counters should not change. That early return does not need modification.

- [ ] **Step 3: Verify the file parses cleanly**

```bash
python -c "from agents.executor_agent import ExecutorAgent; print('OK')"
```

Expected output: `OK`

- [ ] **Step 4: Commit**

```bash
git add agents/executor_agent.py
git commit -m "feat: track widget lookup hits/misses in ExecutorAgent"
```

---

## Task 3: Track reflector call and pass counters in ReflectorAgent

**Files:**
- Modify: `agents/reflector_agent.py`

- [ ] **Step 1: Add counter increments before the return dict**

In `evaluate()`, find the section after the `try/except` block that resolves `passed`, `reasoning`, and `figma_discrepancies` (around line 127–131). It currently ends with:

```python
        return {
            "reflector_reasoning": reasoning,
            "last_reflector_passed": passed,
            "sender": "reflector",
            "chat_logs": new_chat_logs,
            "recovery_attempts": recovery_attempts,
        }
```

Replace with:

```python
        total_reflector_calls = state.get("total_reflector_calls", 0) + 1
        reflector_pass_count = state.get("reflector_pass_count", 0) + (1 if passed else 0)
        is_first = state.get("is_first_verify_attempt", True)
        total_first_verify_calls = state.get("total_first_verify_calls", 0) + (1 if is_first else 0)
        reflector_first_pass_count = state.get("reflector_first_pass_count", 0) + (1 if is_first and passed else 0)

        return {
            "reflector_reasoning": reasoning,
            "last_reflector_passed": passed,
            "sender": "reflector",
            "chat_logs": new_chat_logs,
            "recovery_attempts": recovery_attempts,
            "total_reflector_calls": total_reflector_calls,
            "reflector_pass_count": reflector_pass_count,
            "total_first_verify_calls": total_first_verify_calls,
            "reflector_first_pass_count": reflector_first_pass_count,
        }
```

- [ ] **Step 2: Verify the file parses cleanly**

```bash
python -c "from agents.reflector_agent import ReflectorAgent; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add agents/reflector_agent.py
git commit -m "feat: track reflector call/pass counters for Acc_1 and Acc_f metrics"
```

---

## Task 4: Set metrics flags in PredefinedOrchestrator

**Files:**
- Modify: `core/workflow/predefined/orchestrator.py`

- [ ] **Step 1: Set `is_first_verify_attempt` and increment `steps_completed_count`**

In `orchestrate()`, find the block that handles `sender in ["reflector", "recorder"]` (around line 190–196):

```python
        if sender in ["reflector", "recorder"]:
            if last_passed:
                current_idx += 1
                retry_count = 0
            else:
                retry_count += 1
                print(f"[Predefined] Step failure. Retry attempt {retry_count}/3 for index {current_idx}")
```

Replace with:

```python
        if sender in ["reflector", "recorder"]:
            if last_passed:
                current_idx += 1
                retry_count = 0
            else:
                retry_count += 1
                print(f"[Predefined] Step failure. Retry attempt {retry_count}/3 for index {current_idx}")
```

(No change to this block itself.)

- [ ] **Step 2: Add flag and counter to `update_data`**

Find where `update_data` is built (around line 206–211):

```python
        update_data = {
            "current_sub_step_index": current_idx,
            "current_step": global_step + 1,
            "step_retry_count": retry_count,
            "sender": "orchestrator",
        }
```

Replace with:

```python
        steps_completed_count = state.get("steps_completed_count", 0)
        if sender in ["reflector", "recorder"] and last_passed:
            steps_completed_count += 1

        update_data = {
            "current_sub_step_index": current_idx,
            "current_step": global_step + 1,
            "step_retry_count": retry_count,
            "sender": "orchestrator",
            "is_first_verify_attempt": (retry_count == 0),
            "steps_completed_count": steps_completed_count,
        }
```

Note: `retry_count` at this point already reflects the updated value (incremented on failure, reset on pass). When the step just passed, `retry_count` was reset to `0`, so `is_first_verify_attempt = True` for the NEXT step. When a retry just occurred, `retry_count > 0`, so the next reflector call on this step is flagged as a retry. This is the correct forward-looking semantics.

- [ ] **Step 3: Verify the file parses cleanly**

```bash
python -c "from core.workflow.predefined.orchestrator import PredefinedOrchestrator; print('OK')"
```

Expected output: `OK`

- [ ] **Step 4: Commit**

```bash
git add core/workflow/predefined/orchestrator.py
git commit -m "feat: set is_first_verify_attempt and steps_completed_count in PredefinedOrchestrator"
```

---

## Task 5: Set metrics flags in AutonomousOrchestrator

**Files:**
- Modify: `core/workflow/autonomous/orchestrator.py`

- [ ] **Step 1: Increment `steps_completed_count` when reflector passed**

In `orchestrate()`, find the section that reads sender and last_reflector_passed (around line 207–218):

```python
        task_goal         = state.get("task_goal", "")
        expected_result   = state.get("expected_result", "")
        raw_observer_analysis = state.get("observer_analysis", "No analysis yet.")
        observer_analysis_step = state.get("observer_analysis_step", -1)
        history           = state.get("action_history", [])
        global_step       = state.get("current_step", 0)
        output_dir        = state.get("output_dir", "outputs")
        sender            = state.get("sender", "START")
        last_reflector_passed = state.get("last_reflector_passed", True)
        reflector_reasoning   = state.get("reflector_reasoning", "")
```

Add two lines immediately after:

```python
        task_goal         = state.get("task_goal", "")
        expected_result   = state.get("expected_result", "")
        raw_observer_analysis = state.get("observer_analysis", "No analysis yet.")
        observer_analysis_step = state.get("observer_analysis_step", -1)
        history           = state.get("action_history", [])
        global_step       = state.get("current_step", 0)
        output_dir        = state.get("output_dir", "outputs")
        sender            = state.get("sender", "START")
        last_reflector_passed = state.get("last_reflector_passed", True)
        reflector_reasoning   = state.get("reflector_reasoning", "")

        steps_completed_count = state.get("steps_completed_count", 0)
        if sender == "reflector" and last_reflector_passed:
            steps_completed_count += 1
```

- [ ] **Step 2: Set `is_first_verify_attempt` when dispatching VERIFY**

In the same `orchestrate()`, find the `node_map` and `target_node` resolution block (around line 281–289):

```python
            node_map = {
                "OBSERVE": "observer_node",
                "DECIDE":  "decider_node",
                "EXECUTE": "executor_node",
                "ACT":     "executor_node",
                "VERIFY":  "reflector_node",
                "RECORD":  "recorder_node",
            }
            target_node = node_map.get(plan.action_type.upper(), "observer_node")
```

Add the flag computation immediately after `target_node` is resolved:

```python
            node_map = {
                "OBSERVE": "observer_node",
                "DECIDE":  "decider_node",
                "EXECUTE": "executor_node",
                "ACT":     "executor_node",
                "VERIFY":  "reflector_node",
                "RECORD":  "recorder_node",
            }
            target_node = node_map.get(plan.action_type.upper(), "observer_node")

            # First attempt: True unless this is a recovery VERIFY after a failed reflector
            is_first_verify = not (sender == "reflector" and not last_reflector_passed)
```

- [ ] **Step 3: Include both values in the Command update**

Find the `return Command(...)` block that builds the normal (non-kill-switch) update (around line 333–346):

```python
            return Command(
                goto=target_node,
                update={
                    "orchestrator_instruction": plan.next_step_instruction,
                    "current_sub_step_index": 0,
                    "current_step":          global_step + 1,
                    "is_completed":          is_final,
                    "is_final_step":         is_final,
                    "orchestrator_reasoning": plan.reasoning,
                    "next_agent":            plan.action_type.upper(),
                    "last_agent_calls":      last_calls,
                    "step_dir":              step_dir,
                    "sender":                "orchestrator",
                }
            )
```

Replace with:

```python
            return Command(
                goto=target_node,
                update={
                    "orchestrator_instruction": plan.next_step_instruction,
                    "current_sub_step_index": 0,
                    "current_step":          global_step + 1,
                    "is_completed":          is_final,
                    "is_final_step":         is_final,
                    "orchestrator_reasoning": plan.reasoning,
                    "next_agent":            plan.action_type.upper(),
                    "last_agent_calls":      last_calls,
                    "step_dir":              step_dir,
                    "sender":                "orchestrator",
                    "is_first_verify_attempt": is_first_verify,
                    "steps_completed_count": steps_completed_count,
                }
            )
```

- [ ] **Step 4: Verify the file parses cleanly**

```bash
python -c "from core.workflow.autonomous.orchestrator import AutonomousOrchestrator; print('OK')"
```

Expected output: `OK`

- [ ] **Step 5: Commit**

```bash
git add core/workflow/autonomous/orchestrator.py
git commit -m "feat: set is_first_verify_attempt and steps_completed_count in AutonomousOrchestrator"
```

---

## Task 6: Emit research_metrics block in RecorderAgent

**Files:**
- Modify: `agents/recorder_agent.py`

- [ ] **Step 1: Add the research_metrics computation to `finalize_run_metrics()`**

In `finalize_run_metrics()`, find the existing `metrics` dict build (around line 106–126). It currently ends with:

```python
        metrics = {
            "tcs_id": state.get("tcs_id", "Unknown"),
            ...
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
```

After that closing brace (before the `try` block that writes the file), add:

```python
        # Research metrics block — all 7 comparable metrics in one place
        sub_steps_total = len(state.get("sub_steps", []))
        steps_completed = state.get("steps_completed_count", 0)
        total_ref_calls = state.get("total_reflector_calls", 0)
        ref_passes = state.get("reflector_pass_count", 0)
        first_verify_total = state.get("total_first_verify_calls", 0)
        first_verify_passes = state.get("reflector_first_pass_count", 0)
        lookup_ok = state.get("widget_lookup_success", 0)
        lookup_fail = state.get("widget_lookup_fail", 0)

        def _pct(num, den):
            return round((num / den) * 100, 1) if den > 0 else None

        metrics["research_metrics"] = {
            "coverage_rate":                     _pct(steps_completed, sub_steps_total),
            "decision_accuracy_initial_acc1":    _pct(first_verify_passes, first_verify_total),
            "decision_accuracy_final_accf":      _pct(steps_completed, first_verify_total),
            "verification_pass_rate":            _pct(ref_passes, total_ref_calls),
            "widget_localization_effectiveness": _pct(lookup_ok, lookup_ok + lookup_fail),
            "time_overhead_seconds":             round(duration, 2),
            "token_consumption":                 total_tokens,
        }
```

Note: `duration` and `total_tokens` are already computed earlier in `finalize_run_metrics()` — reference those existing local variables directly. Do not recompute them.

- [ ] **Step 2: Verify the file parses cleanly**

```bash
python -c "from agents.recorder_agent import RecorderAgent; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Verify research_metrics output with a dry-run unit check**

Create a temporary inline check (run in terminal, do not save as a file):

```python
python -c "
from agents.recorder_agent import RecorderAgent
import time

r = RecorderAgent()
fake_state = {
    'tcs_id': 'TEST-001',
    'output_dir': 'outputs/test_metrics_check',
    'session_id': '',
    'sub_steps': ['step1', 'step2', 'step3'],
    'steps_completed_count': 2,
    'total_reflector_calls': 4,
    'reflector_pass_count': 3,
    'total_first_verify_calls': 3,
    'reflector_first_pass_count': 2,
    'widget_lookup_success': 5,
    'widget_lookup_fail': 1,
    'is_completed': False,
    'stagnation_count': 0,
    'start_time': time.time() - 30,
    'end_time': time.time(),
    'recovery_attempts': 1,
    'task_goal': '',
    'orchestrator_reasoning': '',
    'reflector_reasoning': '',
    'figma_enabled': False,
    'last_reflector_passed': False,
    'action_history': [],
}
import os; os.makedirs('outputs/test_metrics_check', exist_ok=True)
r.finalize_run_metrics(fake_state)
import json
data = json.load(open('outputs/test_metrics_check/final_metrics.json'))
rm = data['research_metrics']
assert rm['coverage_rate'] == 66.7,       f'coverage_rate wrong: {rm[\"coverage_rate\"]}'
assert rm['decision_accuracy_initial_acc1'] == 66.7, f'acc1 wrong: {rm[\"decision_accuracy_initial_acc1\"]}'
assert rm['decision_accuracy_final_accf'] == 66.7,   f'accf wrong: {rm[\"decision_accuracy_final_accf\"]}'
assert rm['verification_pass_rate'] == 75.0,         f'vpr wrong: {rm[\"verification_pass_rate\"]}'
assert rm['widget_localization_effectiveness'] == 83.3, f'wle wrong: {rm[\"widget_localization_effectiveness\"]}'
assert rm['time_overhead_seconds'] > 0
assert rm['token_consumption'] == 0
print('All assertions passed')
import shutil; shutil.rmtree('outputs/test_metrics_check')
"
```

Expected output: `All assertions passed`

- [ ] **Step 4: Commit**

```bash
git add agents/recorder_agent.py
git commit -m "feat: emit research_metrics block with all 7 metrics in final_metrics.json"
```

---

## Task 7: Initialize new fields in both runners

**Files:**
- Modify: `core/workflow/predefined/runner.py`
- Modify: `core/workflow/autonomous/runner.py`

- [ ] **Step 1: Add 8 new fields to `initial_state` in predefined runner**

In `core/workflow/predefined/runner.py`, find `initial_state` (around line 85). Add at the end of the dict, before the closing `}`:

```python
            # Research metrics — initialized to zero each scenario run
            "steps_completed_count":      0,
            "total_reflector_calls":      0,
            "reflector_pass_count":       0,
            "total_first_verify_calls":   0,
            "reflector_first_pass_count": 0,
            "is_first_verify_attempt":    True,
            "widget_lookup_success":      0,
            "widget_lookup_fail":         0,
```

- [ ] **Step 2: Add 8 new fields to `initial_state` in autonomous runner**

In `core/workflow/autonomous/runner.py`, find `initial_state` (around line 86). Add at the end of the dict, before the closing `}`:

```python
            # Research metrics — initialized to zero each scenario run
            "steps_completed_count":      0,
            "total_reflector_calls":      0,
            "reflector_pass_count":       0,
            "total_first_verify_calls":   0,
            "reflector_first_pass_count": 0,
            "is_first_verify_attempt":    True,
            "widget_lookup_success":      0,
            "widget_lookup_fail":         0,
```

- [ ] **Step 3: Verify both runners parse cleanly**

```bash
python -c "from core.workflow.predefined.runner import run_predefined; print('predefined OK')"
python -c "from core.workflow.autonomous.runner import run_autonomous; print('autonomous OK')"
```

Expected output:
```
predefined OK
autonomous OK
```

- [ ] **Step 4: Commit**

```bash
git add core/workflow/predefined/runner.py core/workflow/autonomous/runner.py
git commit -m "feat: initialize research metrics fields in predefined and autonomous runners"
```

---

## Task 8: End-to-end output validation

This task has no device — validate the JSON structure using the dry-run unit check from Task 6 as the baseline, then visually inspect a real output if a device is available.

- [ ] **Step 1: Confirm `final_metrics.json` schema**

After a real or simulated run, open `outputs/{mode}/{tcs_id}_{timestamp}/final_metrics.json` and verify:

```json
{
  "tcs_id": "...",
  "mode": "predefined",
  "status": "SUCCESS",
  ...
  "research_metrics": {
    "coverage_rate": 100.0,
    "decision_accuracy_initial_acc1": 80.0,
    "decision_accuracy_final_accf": 100.0,
    "verification_pass_rate": 87.5,
    "widget_localization_effectiveness": 95.0,
    "time_overhead_seconds": 142.3,
    "token_consumption": 18420
  }
}
```

Check that:
- `coverage_rate` is `100.0` on a SUCCESS run and `< 100.0` on a STAGNATED/FAILED run.
- `decision_accuracy_initial_acc1 <= decision_accuracy_final_accf` always.
- `widget_localization_effectiveness` is `null` only if zero widget-ID actions were taken.
- `time_overhead_seconds > 0`.
- `token_consumption >= 0`.

- [ ] **Step 2: Final commit**

```bash
git add .
git commit -m "feat: complete research metrics implementation across all agents and orchestrators"
```
