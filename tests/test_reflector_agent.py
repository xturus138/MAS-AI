import json
import os
import sys
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.reflector_agent import (
    ReflectorAgent,
    LoadingCheckResult,
    UIChangeCheckResult,
    ValidityCheckResult,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_agent():
    """Build a ReflectorAgent with three individually-mocked LLM clients."""
    base_llm = MagicMock()
    llm_loading  = MagicMock(name="llm_loading")
    llm_change   = MagicMock(name="llm_change")
    llm_validity = MagicMock(name="llm_validity")
    base_llm.with_structured_output.side_effect = [llm_loading, llm_change, llm_validity]
    agent = ReflectorAgent(llm=base_llm)
    return agent


def _base_state(**overrides):
    state = {
        "screenshot_path":          "/fake/pre.png",
        "current_step":             1,
        "tcs_id":                   "TCS01",
        "step_dir":                 "",
        "output_dir":               "",
        "action_plan":              {"action_type": "click"},
        "current_sub_step_index":   0,
        "orchestrator_instruction": "Tap Login button",
        "is_final_step":            False,
        "is_first_verify_attempt":  True,
        "recovery_attempts":        0,
        "total_reflector_calls":    0,
        "reflector_pass_count":     0,
        "total_first_verify_calls": 0,
        "reflector_first_pass_count": 0,
        "memory_context":           "",
    }
    state.update(overrides)
    return state


# ── Test 1: Loading check short-circuit ───────────────────────────────────────

def test_loading_short_circuit_returns_fail_without_calling_change_or_validity():
    agent = _make_agent()
    agent._llm_loading.invoke.return_value = LoadingCheckResult(
        loading_done=False, reasoning="Spinner visible"
    )

    result = agent.evaluate(_base_state())

    assert result["last_reflector_passed"] is False
    agent._llm_change.invoke.assert_not_called()
    agent._llm_validity.invoke.assert_not_called()


# ── Test 2: UI change short-circuit ───────────────────────────────────────────

def test_ui_change_short_circuit_returns_fail_without_calling_validity():
    agent = _make_agent()
    agent._llm_loading.invoke.return_value = LoadingCheckResult(
        loading_done=True, reasoning="Page fully rendered"
    )
    agent._llm_change.invoke.return_value = UIChangeCheckResult(
        ui_changed=False, reasoning="Screens are identical"
    )

    result = agent.evaluate(_base_state())

    assert result["last_reflector_passed"] is False
    agent._llm_validity.invoke.assert_not_called()


# ── Test 3: Full chain — all pass ─────────────────────────────────────────────

def test_full_chain_pass_all_three_calls_invoked():
    agent = _make_agent()
    agent._llm_loading.invoke.return_value = LoadingCheckResult(
        loading_done=True, reasoning="Page fully rendered"
    )
    agent._llm_change.invoke.return_value = UIChangeCheckResult(
        ui_changed=True, reasoning="New screen visible"
    )
    agent._llm_validity.invoke.return_value = ValidityCheckResult(
        passed=True, reasoning="Login screen appeared as expected", figma_discrepancies=""
    )

    result = agent.evaluate(_base_state())

    assert result["last_reflector_passed"] is True
    agent._llm_loading.invoke.assert_called_once()
    agent._llm_change.invoke.assert_called_once()
    agent._llm_validity.invoke.assert_called_once()


# ── Test 4: Full chain — validity fails ───────────────────────────────────────

def test_full_chain_validity_fail_returns_false():
    agent = _make_agent()
    agent._llm_loading.invoke.return_value = LoadingCheckResult(
        loading_done=True, reasoning="Page rendered"
    )
    agent._llm_change.invoke.return_value = UIChangeCheckResult(
        ui_changed=True, reasoning="Screen changed"
    )
    agent._llm_validity.invoke.return_value = ValidityCheckResult(
        passed=False, reasoning="Wrong screen shown", figma_discrepancies=""
    )

    result = agent.evaluate(_base_state())

    assert result["last_reflector_passed"] is False


# ── Test 5: start_app bypasses all 3 LLM calls ────────────────────────────────

def test_start_app_bypasses_llm_chain():
    agent = _make_agent()
    mock_device = MagicMock()
    mock_device.get_current_app.return_value = "com.example.app"
    agent.device = mock_device

    state = _base_state(
        action_plan={"action_type": "start_app", "app_package": "com.example.app"}
    )
    result = agent.evaluate(state)

    agent._llm_loading.invoke.assert_not_called()
    agent._llm_change.invoke.assert_not_called()
    agent._llm_validity.invoke.assert_not_called()
    assert result["last_reflector_passed"] is True


# ── Test 6: report JSON contains chain metadata ────────────────────────────────

def test_report_json_contains_chain_metadata(tmp_path):
    agent = _make_agent()
    agent._llm_loading.invoke.return_value = LoadingCheckResult(
        loading_done=True, reasoning="Loaded"
    )
    agent._llm_change.invoke.return_value = UIChangeCheckResult(
        ui_changed=True, reasoning="Changed"
    )
    agent._llm_validity.invoke.return_value = ValidityCheckResult(
        passed=True, reasoning="Valid", figma_discrepancies=""
    )

    state = _base_state(step_dir=str(tmp_path))
    agent.evaluate(state)

    report_path = tmp_path / "reflector_report.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text())
    assert "verification_chain" in data
    chain = data["verification_chain"]
    assert chain["loading_done"] is True
    assert chain["ui_changed"] is True
    assert chain["short_circuit"] is None


# ── Test 7: input action — no UI change should NOT short-circuit ──────────────

def test_input_action_no_ui_change_proceeds_to_call3():
    agent = _make_agent()
    agent._llm_loading.invoke.return_value = LoadingCheckResult(
        loading_done=True, reasoning="Page loaded"
    )
    agent._llm_change.invoke.return_value = UIChangeCheckResult(
        ui_changed=False, reasoning="Text entered but screen identical"
    )
    agent._llm_validity.invoke.return_value = ValidityCheckResult(
        passed=True, reasoning="Text correctly entered in field", figma_discrepancies=""
    )

    state = _base_state(action_plan={"action_type": "input"})
    result = agent.evaluate(state)

    agent._llm_validity.invoke.assert_called_once()   # must NOT short-circuit
    assert result["last_reflector_passed"] is True


# ── Test 8: scroll action — no UI change should NOT short-circuit ─────────────

def test_scroll_action_no_ui_change_proceeds_to_call3():
    agent = _make_agent()
    agent._llm_loading.invoke.return_value = LoadingCheckResult(
        loading_done=True, reasoning="Page loaded"
    )
    agent._llm_change.invoke.return_value = UIChangeCheckResult(
        ui_changed=False, reasoning="Scroll had no visible effect"
    )
    agent._llm_validity.invoke.return_value = ValidityCheckResult(
        passed=False, reasoning="Expected scroll to reveal element", figma_discrepancies=""
    )

    state = _base_state(action_plan={"action_type": "scroll"})
    result = agent.evaluate(state)

    agent._llm_validity.invoke.assert_called_once()   # must NOT short-circuit
    assert result["last_reflector_passed"] is False   # validity result propagated


# ── Test 9: click action — no UI change STILL short-circuits (regression) ─────

def test_click_action_no_ui_change_still_short_circuits():
    agent = _make_agent()
    agent._llm_loading.invoke.return_value = LoadingCheckResult(
        loading_done=True, reasoning="Page loaded"
    )
    agent._llm_change.invoke.return_value = UIChangeCheckResult(
        ui_changed=False, reasoning="Click had no effect"
    )

    state = _base_state(action_plan={"action_type": "click"})
    result = agent.evaluate(state)

    agent._llm_validity.invoke.assert_not_called()    # must short-circuit
    assert result["last_reflector_passed"] is False
