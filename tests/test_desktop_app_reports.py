from __future__ import annotations

import json
from pathlib import Path

from desktop_app.data.reports import ReportRow, RunSummary, list_report_rows, summarize_run
from desktop_app.data.manifest import BatchProgress


def _write_manifest(run_root: Path, cases: list[dict]) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "batch_manifest.json").write_text(json.dumps({"cases": cases}), encoding="utf-8")


def test_summarize_run_computes_pass_rate_and_duration(tmp_path):
    _write_manifest(
        tmp_path,
        [
            {"tcs_id": "TCS-001", "status": "success", "duration_seconds": 90.0, "attempts": []},
            {"tcs_id": "TCS-002", "status": "functional_anomaly", "duration_seconds": 135.0, "attempts": []},
        ],
    )

    summary = summarize_run(str(tmp_path))

    assert summary == RunSummary(
        pass_rate=50.0,
        duration_seconds=225.0,
        total_cases=2,
        progress=BatchProgress(total=2, passed=1, failed=1, stalled=0, technical_error=0, pending=0),
    )


def test_summarize_run_returns_none_when_no_manifest(tmp_path):
    assert summarize_run(str(tmp_path)) is None


def test_list_report_rows_flags_recovery_used_from_last_attempt(tmp_path):
    _write_manifest(
        tmp_path,
        [
            {
                "tcs_id": "TCS-001",
                "status": "success",
                "duration_seconds": 90.0,
                "attempt_number": 1,
                "evidence_path": "/runs/scenario_01/attempt_001",
                "attempts": [
                    {"attempt_number": 1, "recovery_artifact": "/runs/scenario_01/attempt_001/recovery_transition.json"}
                ],
            },
            {
                "tcs_id": "TCS-002",
                "status": "success",
                "duration_seconds": 60.0,
                "attempt_number": 1,
                "evidence_path": "/runs/scenario_02/attempt_001",
                "attempts": [{"attempt_number": 1}],
            },
        ],
    )

    rows = list_report_rows(str(tmp_path))

    assert rows[0] == ReportRow(
        tcs_id="TCS-001",
        status="success",
        duration_seconds=90.0,
        attempt_number=1,
        recovery_used=True,
        evidence_path="/runs/scenario_01/attempt_001",
    )
    assert rows[1].recovery_used is False
