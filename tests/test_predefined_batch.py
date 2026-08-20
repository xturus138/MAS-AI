import csv
import json
from pathlib import Path

import pytest

from core.workflow.predefined.batch import (
    BatchCompatibilityError,
    PredefinedBatchCoordinator,
)


def scenarios(*tcs_ids: str) -> list[dict]:
    return [{"tcs_id": tcs_id, "scenario_desc": f"Scenario {tcs_id}"} for tcs_id in tcs_ids]


def coordinator(tmp_path: Path, cases: list[dict], executor, fingerprint="fingerprint-a"):
    return PredefinedBatchCoordinator(
        scenarios=cases,
        source_workbook=tmp_path / "firebase-chat.xlsx",
        workbook_fingerprint=fingerprint,
        run_root=tmp_path / "run",
        case_executor=executor,
    )


def load_manifest(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "run" / "batch_manifest.json").read_text(encoding="utf-8"))


def test_executor_error_becomes_technical_error_and_later_case_runs(tmp_path):
    executed = []

    def execute(case, evidence_dir):
        executed.append(case["tcs_id"])
        if case["tcs_id"] == "TCS-2":
            raise RuntimeError("fake executor exploded")
        return {"status": "success", "duration_seconds": 1.5}

    coordinator(tmp_path, scenarios("TCS-1", "TCS-2", "TCS-3"), execute).run()

    manifest = load_manifest(tmp_path)
    assert executed == ["TCS-1", "TCS-2", "TCS-3"]
    assert [case["status"] for case in manifest["cases"]] == [
        "success",
        "technical_error",
        "success",
    ]
    assert all(case["completed_at"] for case in manifest["cases"])
    error_artifact = tmp_path / "run" / "scenario_02" / "attempt_001" / "error.txt"
    assert "RuntimeError: fake executor exploded" in error_artifact.read_text(encoding="utf-8")
    evidence_index = json.loads(
        (tmp_path / "run" / "scenario_02" / "attempt_001" / "evidence_index.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence_index["status"] == "technical_error"
    assert evidence_index["error_or_anomaly_reason"] == str(error_artifact)
    assert evidence_index["process_log_paths"] == []
    assert evidence_index["llm_log_paths"] == []


def test_manifest_and_execution_keep_the_given_workbook_order(tmp_path):
    executed = []

    def execute(case, evidence_dir):
        executed.append(case["tcs_id"])
        return {"status": "success", "duration_seconds": 0}

    coordinator(tmp_path, scenarios("TCS-3", "TCS-1", "TCS-2"), execute).run()

    manifest = load_manifest(tmp_path)
    assert executed == ["TCS-3", "TCS-1", "TCS-2"]
    assert manifest["ordered_tcs_ids"] == ["TCS-3", "TCS-1", "TCS-2"]
    assert [case["tcs_id"] for case in manifest["cases"]] == ["TCS-3", "TCS-1", "TCS-2"]


def test_resume_skips_terminal_cases_and_executes_only_unfinished_cases(tmp_path):
    def interrupted_execute(case, evidence_dir):
        if case["tcs_id"] == "TCS-2":
            raise KeyboardInterrupt()
        return {"status": "success", "duration_seconds": 1}

    with pytest.raises(KeyboardInterrupt):
        coordinator(tmp_path, scenarios("TCS-1", "TCS-2", "TCS-3"), interrupted_execute).run()

    resumed = []

    def resume_execute(case, evidence_dir):
        resumed.append(case["tcs_id"])
        return {"status": "success", "duration_seconds": 2}

    coordinator(tmp_path, scenarios("TCS-1", "TCS-2", "TCS-3"), resume_execute).run()

    assert resumed == ["TCS-2", "TCS-3"]


def test_resume_preserves_running_evidence_and_allocates_the_next_attempt(tmp_path):
    def interrupted_execute(case, evidence_dir):
        (evidence_dir / "captured-before-interrupt.txt").write_bytes(b"immutable evidence")
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        coordinator(tmp_path, scenarios("TCS-1"), interrupted_execute).run()

    first_attempt = tmp_path / "run" / "scenario_01" / "attempt_001"
    before_resume = (first_attempt / "captured-before-interrupt.txt").read_bytes()

    def resume_execute(case, evidence_dir):
        assert evidence_dir.name == "attempt_002"
        return {"status": "success", "duration_seconds": 3}

    coordinator(tmp_path, scenarios("TCS-1"), resume_execute).run()

    manifest = load_manifest(tmp_path)
    assert (first_attempt / "captured-before-interrupt.txt").read_bytes() == before_resume
    assert (tmp_path / "run" / "scenario_01" / "attempt_002").is_dir()
    assert manifest["cases"][0]["attempts"][0]["status"] == "interrupted"
    assert manifest["cases"][0]["attempts"][1]["status"] == "success"


def test_resume_rejects_fingerprint_or_order_mismatch_before_any_execution(tmp_path):
    coordinator(
        tmp_path,
        scenarios("TCS-1", "TCS-2"),
        lambda case, evidence_dir: {"status": "success", "duration_seconds": 0},
    ).run()

    executed = []
    with pytest.raises(BatchCompatibilityError):
        coordinator(
            tmp_path,
            scenarios("TCS-2", "TCS-1"),
            lambda case, evidence_dir: executed.append(case["tcs_id"]),
            fingerprint="changed-fingerprint",
        ).run()

    assert executed == []


def test_summary_json_and_csv_list_all_cases_and_zero_status_counts(tmp_path):
    outcomes = iter(
        [
            {"status": "success", "duration_seconds": 1.25},
            {"status": "functional_anomaly", "duration_seconds": 2.5},
            {"status": "stagnated", "duration_seconds": 3.75},
        ]
    )
    coordinator(tmp_path, scenarios("TCS-1", "TCS-2", "TCS-3"), lambda case, evidence_dir: next(outcomes)).run()

    summary = json.loads((tmp_path / "run" / "batch_summary.json").read_text(encoding="utf-8"))
    with (tmp_path / "run" / "batch_summary.csv").open(newline="", encoding="utf-8") as summary_csv:
        rows = list(csv.DictReader(summary_csv))

    assert summary["counts"] == {
        "success": 1,
        "functional_anomaly": 1,
        "stagnated": 1,
        "technical_error": 0,
    }
    assert [row["tcs_id"] for row in summary["cases"]] == ["TCS-1", "TCS-2", "TCS-3"]
    assert [row["tcs_id"] for row in rows] == ["TCS-1", "TCS-2", "TCS-3"]
    assert [row["attempt"] for row in rows] == ["1", "1", "1"]


def test_arbitrary_executor_status_never_serializes_into_the_manifest(tmp_path):
    coordinator(
        tmp_path,
        scenarios("TCS-1"),
        lambda case, evidence_dir: {"status": "invented_status", "duration_seconds": 0},
    ).run()

    manifest = load_manifest(tmp_path)
    assert manifest["cases"][0]["status"] == "technical_error"
    assert "invented_status" not in json.dumps(manifest)


def test_evidence_index_write_failure_becomes_technical_and_retries_minimal_index(tmp_path):
    batch = coordinator(
        tmp_path,
        scenarios("TCS-1", "TCS-2"),
        lambda case, evidence_dir: {"status": "success", "duration_seconds": 0},
    )
    original_write = batch._atomic_json_write
    failed_once = False

    def fail_first_evidence_write(destination, content):
        nonlocal failed_once
        if destination.name == "evidence_index.json" and not failed_once:
            failed_once = True
            raise OSError("fake evidence index write failure")
        return original_write(destination, content)

    batch._atomic_json_write = fail_first_evidence_write
    manifest = batch.run()

    assert [case["status"] for case in manifest["cases"]] == [
        "technical_error",
        "success",
    ]
    first_index = json.loads(
        (tmp_path / "run" / "scenario_01" / "attempt_001" / "evidence_index.json").read_text(
            encoding="utf-8"
        )
    )
    assert first_index["status"] == "technical_error"
    assert "evidence_index_error.txt" in first_index["error_or_anomaly_reason"]
