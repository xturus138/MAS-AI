"""Durable, dependency-injected execution of predefined workbook cases."""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import tempfile
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = (
    "success",
    "functional_anomaly",
    "stagnated",
    "technical_error",
)
_RESUMABLE_STATUSES = {"not_started", "running", "interrupted"}
_MANIFEST_VERSION = 1


class BatchCompatibilityError(ValueError):
    """Raised when an existing run belongs to a different workbook contract."""


def validate_resume_manifest(
    run_root: str | Path,
    *,
    workbook_fingerprint: str,
    ordered_tcs_ids: Sequence[str],
) -> dict[str, Any]:
    """Read and validate a resume manifest without creating any directories."""
    manifest_path = Path(run_root).expanduser().resolve() / "batch_manifest.json"
    if not manifest_path.is_file():
        raise BatchCompatibilityError(
            f"Resume requires an existing batch_manifest.json at {manifest_path}."
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        manifest.get("workbook_fingerprint") != workbook_fingerprint
        or manifest.get("ordered_tcs_ids") != [str(value) for value in ordered_tcs_ids]
    ):
        raise BatchCompatibilityError(
            "Existing batch manifest does not match the workbook fingerprint or ordered TCS IDs."
        )
    return manifest


class PredefinedBatchCoordinator:
    """Execute workbook-order cases without owning live testing dependencies.

    ``case_executor`` and the optional ``recovery_callback`` receive the original
    scenario dict and a newly allocated evidence directory.  The executor must
    return a mapping with one canonical terminal ``status``.
    """

    def __init__(
        self,
        *,
        scenarios: Sequence[dict[str, Any]],
        source_workbook: str | Path,
        workbook_fingerprint: str,
        run_root: str | Path,
        case_executor: Callable[[dict[str, Any], Path], Mapping[str, Any]],
        recovery_callback: Callable[[dict[str, Any], Path], Any] | None = None,
    ) -> None:
        self.scenarios = list(scenarios)
        self.source_workbook = str(Path(source_workbook).expanduser().resolve())
        self.workbook_fingerprint = workbook_fingerprint
        self.run_root = Path(run_root).expanduser().resolve()
        self.case_executor = case_executor
        self.recovery_callback = recovery_callback
        self._ordered_tcs_ids = [str(case["tcs_id"]) for case in self.scenarios]

    def run(self) -> dict[str, Any]:
        """Run or resume the batch and return its final manifest.

        ``KeyboardInterrupt`` and ``SystemExit`` deliberately propagate after the
        persisted ``running`` state, allowing a future invocation to resume.
        """
        manifest = self._load_or_initialize_manifest()
        for index, scenario in enumerate(self.scenarios, start=1):
            case_record = manifest["cases"][index - 1]
            if case_record["status"] in TERMINAL_STATUSES:
                continue
            if case_record["status"] not in _RESUMABLE_STATUSES:
                raise BatchCompatibilityError(
                    f"Case {case_record['tcs_id']} has unknown lifecycle state {case_record['status']!r}."
                )
            self._run_case(manifest, case_record, scenario, index)

        self._write_manifest(manifest)
        self._write_summary(manifest)
        return manifest

    def _load_or_initialize_manifest(self) -> dict[str, Any]:
        manifest_path = self.run_root / "batch_manifest.json"
        if not manifest_path.exists():
            self.run_root.mkdir(parents=True, exist_ok=True)
            manifest = {
                "manifest_version": _MANIFEST_VERSION,
                "source_workbook": self.source_workbook,
                "workbook_fingerprint": self.workbook_fingerprint,
                "ordered_tcs_ids": self._ordered_tcs_ids,
                "cases": [
                    {
                        "tcs_id": tcs_id,
                        "status": "not_started",
                        "attempt_number": None,
                        "duration_seconds": None,
                        "completed_at": None,
                        "evidence_path": None,
                        "reason_ref": None,
                        "observation_ref": None,
                        "attempts": [],
                    }
                    for tcs_id in self._ordered_tcs_ids
                ],
            }
            self._write_manifest(manifest)
            return manifest

        return validate_resume_manifest(
            self.run_root,
            workbook_fingerprint=self.workbook_fingerprint,
            ordered_tcs_ids=self._ordered_tcs_ids,
        )

    def _run_case(
        self,
        manifest: dict[str, Any],
        case_record: dict[str, Any],
        scenario: dict[str, Any],
        scenario_number: int,
    ) -> None:
        self._mark_previous_running_attempt_interrupted(case_record)
        evidence_dir, attempt_number = self._allocate_attempt_directory(case_record, scenario_number)
        attempt = {
            "attempt_number": attempt_number,
            "status": "running",
            "duration_seconds": None,
            "completed_at": None,
            "evidence_path": str(evidence_dir),
            "reason_ref": None,
            "observation_ref": None,
        }
        case_record["attempts"].append(attempt)
        self._copy_attempt_to_case(case_record, attempt)
        self._write_manifest(manifest)

        started_at = time.monotonic()
        result: Mapping[str, Any] = {}
        recovery_artifact = None
        try:
            if self.recovery_callback is not None:
                recovery_artifact = self.recovery_callback(scenario, evidence_dir)
            result = self.case_executor(scenario, evidence_dir)
            self._complete_attempt(
                attempt,
                result,
                elapsed_seconds=time.monotonic() - started_at,
                recovery_artifact=recovery_artifact,
            )
        except Exception:
            error_path = evidence_dir / "error.txt"
            self._write_error_artifact(error_path)
            attempt.update(
                status="technical_error",
                duration_seconds=time.monotonic() - started_at,
                reason_ref=str(error_path),
            )
        attempt["completed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        try:
            evidence_index = self._ensure_evidence_index(
                scenario=scenario,
                attempt=attempt,
                evidence_dir=evidence_dir,
                result=result,
                recovery_artifact=recovery_artifact,
            )
            attempt["observation_ref"] = attempt.get("observation_ref") or str(evidence_index)
        except Exception:
            evidence_error = evidence_dir / "evidence_index_error.txt"
            try:
                self._write_error_artifact(evidence_error)
            except Exception:
                pass
            attempt.update(
                status="technical_error",
                reason_ref=str(evidence_error),
                observation_ref=None,
            )
            # A comprehensive index failure must not leave the attempt without
            # its canonical evidence pointer. Retry with the smallest JSON-safe
            # technical record, then continue the batch even if disk I/O fails
            # a second time.
            minimal_index = evidence_dir / "evidence_index.json"
            try:
                self._atomic_json_write(
                    minimal_index,
                    {
                        "tcs_id": str(scenario.get("tcs_id", "")),
                        "attempt_number": attempt.get("attempt_number"),
                        "actual_observation": "",
                        "status": "technical_error",
                        "duration_seconds": attempt.get("duration_seconds"),
                        "final_screenshot_paths": [],
                        "process_log_paths": [],
                        "llm_log_paths": [],
                        "recovery_artifact": None,
                        "metrics_path": None,
                        "error_or_anomaly_reason": str(evidence_error),
                    },
                )
                attempt["observation_ref"] = str(minimal_index)
            except Exception:
                pass
        self._copy_attempt_to_case(case_record, attempt)
        self._write_manifest(manifest)

    def _ensure_evidence_index(
        self,
        *,
        scenario: Mapping[str, Any],
        attempt: Mapping[str, Any],
        evidence_dir: Path,
        result: Mapping[str, Any],
        recovery_artifact: Any,
    ) -> Path:
        evidence_path = evidence_dir / "evidence_index.json"
        existing: dict[str, Any] = {}
        if evidence_path.is_file():
            try:
                existing = json.loads(evidence_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}
        process_logs = sorted(str(path) for path in evidence_dir.rglob("process.log"))
        llm_logs = sorted(str(path) for path in evidence_dir.rglob("logs/llm/*.json"))
        screenshots = sorted(
            str(path)
            for pattern in ("*.png", "*.jpg", "*.jpeg")
            for path in evidence_dir.rglob(pattern)
        )
        payload = {
            "tcs_id": str(scenario.get("tcs_id", "")),
            "attempt_number": attempt.get("attempt_number"),
            "actual_observation": result.get("actual_observation", ""),
            "status": attempt.get("status"),
            "duration_seconds": attempt.get("duration_seconds"),
            "final_screenshot_paths": result.get("final_screenshot_paths", screenshots),
            "process_log_paths": result.get("process_log_paths", process_logs),
            "llm_log_paths": result.get("llm_log_paths", llm_logs),
            "recovery_artifact": result.get("recovery_artifact", recovery_artifact),
            "metrics_path": result.get("metrics_path"),
            "error_or_anomaly_reason": result.get("error_or_anomaly_reason")
            or attempt.get("reason_ref"),
        }
        payload.update(existing)
        payload["status"] = attempt.get("status")
        payload["duration_seconds"] = attempt.get("duration_seconds")
        if not payload.get("error_or_anomaly_reason"):
            payload["error_or_anomaly_reason"] = attempt.get("reason_ref")
        self._atomic_json_write(evidence_path, payload)
        return evidence_path

    @staticmethod
    def _mark_previous_running_attempt_interrupted(case_record: dict[str, Any]) -> None:
        if case_record["status"] != "running":
            return
        previous_attempt = case_record["attempts"][-1]
        previous_attempt["status"] = "interrupted"
        previous_attempt["reason_ref"] = previous_attempt.get("reason_ref") or "interrupted_before_completion"
        PredefinedBatchCoordinator._copy_attempt_to_case(case_record, previous_attempt)

    def _allocate_attempt_directory(self, case_record: dict[str, Any], scenario_number: int) -> tuple[Path, int]:
        scenario_dir = self.run_root / f"scenario_{scenario_number:02d}"
        scenario_dir.mkdir(parents=True, exist_ok=True)
        recorded_attempts = [attempt.get("attempt_number", 0) for attempt in case_record["attempts"]]
        existing_attempts = [
            int(path.name.removeprefix("attempt_"))
            for path in scenario_dir.glob("attempt_*")
            if path.is_dir() and path.name.removeprefix("attempt_").isdigit()
        ]
        attempt_number = max([0, *recorded_attempts, *existing_attempts]) + 1
        while True:
            evidence_dir = scenario_dir / f"attempt_{attempt_number:03d}"
            try:
                evidence_dir.mkdir()
                return evidence_dir, attempt_number
            except FileExistsError:
                attempt_number += 1

    @staticmethod
    def _complete_attempt(
        attempt: dict[str, Any],
        result: Mapping[str, Any],
        *,
        elapsed_seconds: float,
        recovery_artifact: Any,
    ) -> None:
        if not isinstance(result, Mapping):
            raise ValueError("Case executor must return a structured mapping.")
        status = result.get("status")
        if status not in TERMINAL_STATUSES:
            raise ValueError("Case executor returned a non-canonical terminal status.")
        duration_seconds = result.get("duration_seconds", elapsed_seconds)
        if not isinstance(duration_seconds, (int, float)):
            raise ValueError("duration_seconds must be numeric when supplied.")
        attempt.update(
            status=status,
            duration_seconds=duration_seconds,
            reason_ref=result.get("reason_ref"),
            observation_ref=result.get("observation_ref"),
        )
        if recovery_artifact is not None:
            attempt["recovery_artifact"] = recovery_artifact

    @staticmethod
    def _copy_attempt_to_case(case_record: dict[str, Any], attempt: dict[str, Any]) -> None:
        for field in (
            "status",
            "attempt_number",
            "duration_seconds",
            "completed_at",
            "evidence_path",
            "reason_ref",
            "observation_ref",
        ):
            case_record[field] = attempt.get(field)

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        self._atomic_json_write(self.run_root / "batch_manifest.json", manifest)

    def _write_summary(self, manifest: dict[str, Any]) -> None:
        cases = [
            {
                "tcs_id": case["tcs_id"],
                "status": case["status"],
                "duration_seconds": case["duration_seconds"],
                "evidence_path": case["evidence_path"],
                "attempt": case["attempt_number"],
            }
            for case in manifest["cases"]
        ]
        counts = {status: sum(case["status"] == status for case in cases) for status in TERMINAL_STATUSES}
        self._atomic_json_write(self.run_root / "batch_summary.json", {"counts": counts, "cases": cases})

        summary_path = self.run_root / "batch_summary.csv"
        with tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8", dir=self.run_root, prefix=".batch_summary.", suffix=".tmp", delete=False
        ) as temporary_file:
            writer = csv.DictWriter(
                temporary_file,
                fieldnames=["tcs_id", "status", "duration_seconds", "evidence_path", "attempt"],
            )
            writer.writeheader()
            writer.writerows(cases)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, summary_path)

    @staticmethod
    def _atomic_json_write(destination: Path, content: dict[str, Any]) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False
        ) as temporary_file:
            json.dump(content, temporary_file, indent=2, sort_keys=True, default=str)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, destination)

    @staticmethod
    def _write_error_artifact(error_path: Path) -> None:
        with error_path.open("w", encoding="utf-8") as error_file:
            traceback.print_exc(file=error_file)
            error_file.flush()
            os.fsync(error_file.fileno())
