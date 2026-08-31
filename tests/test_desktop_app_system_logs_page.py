from __future__ import annotations

from desktop_app.pages.system_logs import COMPONENT_FILTER_OPTIONS


def test_component_filter_options_include_all_agents_and_all_option():
    assert COMPONENT_FILTER_OPTIONS == [
        "All", "ORCHESTRATOR", "OBSERVER", "DECIDER", "EXECUTOR", "SYSTEM",
    ]
