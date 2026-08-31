from __future__ import annotations

from desktop_app.pages.test_suites import STATUS_LABELS, run_selected_is_unlocked


def test_status_labels_cover_all_five_statuses():
    assert STATUS_LABELS == {
        "untested": "Untested",
        "success": "Pass",
        "functional_anomaly": "Fail",
        "stagnated": "Stalled",
        "technical_error": "Technical Error",
    }


def test_run_selected_locked_when_no_manifest_exists():
    assert run_selected_is_unlocked(manifest=None, total_workbook_cases=5) is False


def test_run_selected_locked_when_manifest_is_partial():
    manifest = {"cases": [{"status": "success"}, {"status": "not_started"}]}

    assert run_selected_is_unlocked(manifest=manifest, total_workbook_cases=2) is False


def test_run_selected_unlocked_when_manifest_fully_terminal_and_matches_case_count():
    manifest = {
        "cases": [
            {"status": "success"},
            {"status": "functional_anomaly"},
            {"status": "technical_error"},
        ]
    }

    assert run_selected_is_unlocked(manifest=manifest, total_workbook_cases=3) is True


def test_run_selected_locked_when_case_count_no_longer_matches_workbook():
    # Workbook was edited after the last full run — case count differs.
    manifest = {"cases": [{"status": "success"}, {"status": "success"}]}

    assert run_selected_is_unlocked(manifest=manifest, total_workbook_cases=5) is False
