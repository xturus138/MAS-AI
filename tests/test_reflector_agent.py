import json
import os
import sys
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.reflector_agent import (
    ReflectorAgent,
    SinglePassVerdict,
)


def _make_agent():
    """Build a ReflectorAgent with mocked single-pass LLM client."""
    base_llm = MagicMock()
    llm_single_pass = MagicMock(name="llm_single_pass")
    base_llm.with_structured_output.return_value = llm_single_pass
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



def test_single_pass_pass_invoked():
    agent = _make_agent()
    agent._llm_single_pass.invoke.return_value = SinglePassVerdict(
        loading_done=True,
        ui_changed=True,
        passed=True,
        reasoning="Login screen appeared as expected",
        figma_discrepancies="",
    )

    result = agent.evaluate(_base_state())

    assert result["last_reflector_passed"] is True
    agent._llm_single_pass.invoke.assert_called_once()


def test_single_pass_validity_fail_returns_false():
    agent = _make_agent()
    agent._llm_single_pass.invoke.return_value = SinglePassVerdict(
        loading_done=True,
        ui_changed=True,
        passed=False,
        reasoning="Wrong screen shown",
        figma_discrepancies="",
    )

    result = agent.evaluate(_base_state())

    assert result["last_reflector_passed"] is False


def test_start_app_bypasses_llm_chain():
    agent = _make_agent()
    mock_device = MagicMock()
    mock_device.get_current_app.return_value = "com.example.app"
    agent.device = mock_device

    state = _base_state(
        action_plan={"action_type": "start_app", "app_package": "com.example.app"}
    )
    result = agent.evaluate(state)

    agent._llm_single_pass.invoke.assert_not_called()
    assert result["last_reflector_passed"] is True


def test_report_json_contains_chain_metadata(tmp_path):
    agent = _make_agent()
    agent._llm_single_pass.invoke.return_value = SinglePassVerdict(
        loading_done=True,
        ui_changed=True,
        passed=True,
        reasoning="Valid",
        figma_discrepancies="",
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
    assert chain["single_pass"] is True


def test_input_action_no_ui_change_proceeds_to_pass():
    agent = _make_agent()
    agent._llm_single_pass.invoke.return_value = SinglePassVerdict(
        loading_done=True,
        ui_changed=False,
        passed=True,
        reasoning="Text entered correctly",
    )

    state = _base_state(action_plan={"action_type": "input"})
    result = agent.evaluate(state)

    assert result["last_reflector_passed"] is True


def test_click_action_no_ui_change_and_zero_pixel_diff_fails():
    agent = _make_agent()
    agent._check_pixel_difference = MagicMock(return_value=0.0)
    agent._llm_single_pass.invoke.return_value = SinglePassVerdict(
        loading_done=True,
        ui_changed=False,
        passed=True,
        reasoning="Screen didn't change",
    )

    state = _base_state(action_plan={"action_type": "click"})
    result = agent.evaluate(state)

    assert result["last_reflector_passed"] is False
