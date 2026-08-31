"""Aggregates batch_manifest.json into Reports & Evidence screen data."""

from __future__ import annotations

from dataclasses import dataclass

from desktop_app.data.manifest import BatchProgress, compute_progress, read_manifest


@dataclass(frozen=True)
class RunSummary:
    pass_rate: float
    duration_seconds: float
    total_cases: int
    progress: BatchProgress


@dataclass(frozen=True)
class ReportRow:
    tcs_id: str
    status: str
    duration_seconds: float
    attempt_number: int | None
    recovery_used: bool
    evidence_path: str | None


def summarize_run(run_root: str) -> RunSummary | None:
    manifest = read_manifest(run_root)
    if manifest is None:
        return None
    progress = compute_progress(manifest)
    total_duration = sum(
        float(case.get("duration_seconds") or 0.0) for case in manifest.get("cases", [])
    )
    pass_rate = (progress.passed / progress.total * 100) if progress.total else 0.0
    return RunSummary(
        pass_rate=pass_rate,
        duration_seconds=total_duration,
        total_cases=progress.total,
        progress=progress,
    )


def list_report_rows(run_root: str) -> list[ReportRow]:
    manifest = read_manifest(run_root)
    if manifest is None:
        return []
    rows: list[ReportRow] = []
    for case in manifest.get("cases", []):
        attempts = case.get("attempts") or []
        last_attempt = attempts[-1] if attempts else {}
        rows.append(
            ReportRow(
                tcs_id=str(case.get("tcs_id", "")),
                status=str(case.get("status", "")),
                duration_seconds=float(case.get("duration_seconds") or 0.0),
                attempt_number=case.get("attempt_number"),
                recovery_used=bool(last_attempt.get("recovery_artifact")),
                evidence_path=case.get("evidence_path"),
            )
        )
    return rows
