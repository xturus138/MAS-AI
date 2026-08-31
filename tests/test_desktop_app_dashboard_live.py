from __future__ import annotations

from desktop_app.pages.dashboard import DashboardLiveState


def test_push_progress_updates_scenario_title():
    state = DashboardLiveState()

    state.push_progress(scenario_idx=3, scenario_total=10, tcs_id="TCS-003", status="Running")

    assert state.scenario_title == "TCS-003"


def test_push_log_appends_and_caps_at_200_lines():
    state = DashboardLiveState()

    for i in range(250):
        state.push_log("OBSERVER", f"line {i}")

    assert len(state.log_lines) == 200
    assert state.log_lines[-1][2] == "line 249"


def test_push_log_records_component_and_message():
    state = DashboardLiveState()

    state.push_log("DECIDER", "Action: CLICK.", "extra detail")

    timestamp, component, message = state.log_lines[-1]
    assert component == "DECIDER"
    assert "Action: CLICK." in message
    assert "extra detail" in message
