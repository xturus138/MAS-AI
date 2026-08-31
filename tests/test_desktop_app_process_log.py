from __future__ import annotations

from desktop_app.data.process_log import LogEntry, filter_entries, parse_log_lines

SAMPLE_LOG = (
    "================================================================================\n"
    "  MAS AI — Process Log\n"
    "  Output: /tmp/run\n"
    "  Started: 2026-08-31 10:00:00.000\n"
    "================================================================================\n"
    "\n"
    "2026-08-31 10:42:01.233  [ORCHESTRATOR  ]  Initiating Scenario 42\n"
    "2026-08-31 10:42:03.401  [OBSERVER      ]  Screen state captured.\n"
    "2026-08-31 10:42:04.112  [DECIDER       ]  Action: CLICK.\n"
)


def test_parse_log_lines_skips_banner_and_blank_lines():
    entries = parse_log_lines(SAMPLE_LOG)

    assert entries == [
        LogEntry(timestamp="2026-08-31 10:42:01.233", component="ORCHESTRATOR", message="Initiating Scenario 42"),
        LogEntry(timestamp="2026-08-31 10:42:03.401", component="OBSERVER", message="Screen state captured."),
        LogEntry(timestamp="2026-08-31 10:42:04.112", component="DECIDER", message="Action: CLICK."),
    ]


def test_filter_entries_by_component_is_case_insensitive():
    entries = parse_log_lines(SAMPLE_LOG)

    result = filter_entries(entries, component="observer")

    assert len(result) == 1
    assert result[0].component == "OBSERVER"


def test_filter_entries_with_no_component_returns_everything():
    entries = parse_log_lines(SAMPLE_LOG)

    assert filter_entries(entries, component=None) == entries
