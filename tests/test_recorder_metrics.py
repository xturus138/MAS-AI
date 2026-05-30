import os
import json
import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents.recorder_agent import RecorderAgent


def _make_recorder(steps_completed=3, sub_steps_total=3, is_completed=True, mode_hint="predefined"):
    """Build a RecorderAgent with a minimal mock memory for metric calculation."""
    memory = MagicMock()
    memory.core.get.side_effect = lambda key: {
        "task_goal": "Test login" if mode_hint == "autonomous" else "",
        "test_type": "Pos.",
        "figma_enabled": "False",
    }.get(key, "")
    memory.procedural.get_steps.return_value = (
        []  # autonomous: no sub_steps
        if mode_hint == "autonomous"
        else [f"step{i}" for i in range(sub_steps_total)]
    )
    memory.episodic.all_as_dicts.return_value = []
    memory.episodic.last_by_actor.return_value = None
    return RecorderAgent(memory=memory), memory


def _base_final_state(steps_completed=3, is_completed=True):
    return {
        "tcs_id": "TCS01",
        "session_id": "TCS01_20260530",
        "output_dir": "",
        "is_completed": is_completed,
        "stagnation_count": 0,
        "current_step": steps_completed,
        "steps_completed_count": steps_completed,
        "total_reflector_calls": steps_completed,
        "reflector_pass_count": steps_completed,
        "total_first_verify_calls": steps_completed,
        "reflector_first_pass_count": steps_completed,
        "widget_lookup_success": 5,
        "widget_lookup_fail": 0,
        "widget_text_fallback_count": 0,
        "recovery_attempts": 0,
        "start_time": 0.0,
        "end_time": 10.0,
        "last_reflector_passed": True,
        "orchestrator_instruction": "",
    }


# ── Test 1: predefined coverage_rate is steps/total ───────────────────────────

def test_predefined_coverage_rate_is_steps_over_total(tmp_path):
    recorder, _ = _make_recorder(steps_completed=2, sub_steps_total=4, mode_hint="predefined")
    state = _base_final_state(steps_completed=2, is_completed=False)
    state["output_dir"] = str(tmp_path)

    with patch("agents.recorder_agent.RecorderAgent.write_test_report"):
        recorder.finalize_run_metrics(state)

    metrics = json.loads((tmp_path / "final_metrics.json").read_text())
    assert metrics["research_metrics"]["coverage_rate"] == 50.0


# ── Test 2: predefined full completion gives 100% ─────────────────────────────

def test_predefined_full_completion_coverage_rate_100(tmp_path):
    recorder, _ = _make_recorder(steps_completed=3, sub_steps_total=3, mode_hint="predefined")
    state = _base_final_state(steps_completed=3, is_completed=True)
    state["output_dir"] = str(tmp_path)

    with patch("agents.recorder_agent.RecorderAgent.write_test_report"):
        recorder.finalize_run_metrics(state)

    metrics = json.loads((tmp_path / "final_metrics.json").read_text())
    assert metrics["research_metrics"]["coverage_rate"] == 100.0


# ── Test 3: autonomous coverage_rate is None, not a tautology ────────────────

def test_autonomous_coverage_rate_is_none(tmp_path):
    recorder, _ = _make_recorder(mode_hint="autonomous")
    state = _base_final_state(steps_completed=0, is_completed=True)
    state["output_dir"] = str(tmp_path)
    state["orchestrator_instruction"] = "Complete login flow"

    with patch("agents.recorder_agent.RecorderAgent.write_test_report"):
        recorder.finalize_run_metrics(state)

    metrics = json.loads((tmp_path / "final_metrics.json").read_text())
    assert metrics["research_metrics"]["coverage_rate"] is None
