"""Reads batch_manifest.json for live/last-known batch progress.

TERMINAL_STATUSES values (success, functional_anomaly, stagnated,
technical_error) come from core/workflow/predefined/batch.py — this module
must stay in sync with that list rather than redefining its own.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from shared import config


@dataclass(frozen=True)
class BatchProgress:
    total: int
    passed: int
    failed: int
    stalled: int
    technical_error: int
    pending: int


def read_manifest(run_root: str) -> dict | None:
    manifest_path = Path(run_root) / "batch_manifest.json"
    if not manifest_path.is_file():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def compute_progress(manifest: dict) -> BatchProgress:
    cases = manifest.get("cases", [])
    statuses = [str(case.get("status", "")) for case in cases]
    return BatchProgress(
        total=len(statuses),
        passed=statuses.count("success"),
        failed=statuses.count("functional_anomaly"),
        stalled=statuses.count("stagnated"),
        technical_error=statuses.count("technical_error"),
        pending=sum(
            1
            for status in statuses
            if status not in ("success", "functional_anomaly", "stagnated", "technical_error")
        ),
    )


def find_latest_run_root(mode: str = "predefined") -> str | None:
    """Return the run_root directory containing batch_manifest.json, or None.

    write_latest_index() records a per-case run_dir (run_root/scenario_NN);
    this walks up from that recorded path to find the ancestor that actually
    holds batch_manifest.json, since the exact nesting depth is an
    implementation detail of create_run_output(), not something to hardcode.
    """
    latest_path = os.path.join(config.OUTPUT_DIR, "indexes", "latest.json")
    if not os.path.isfile(latest_path):
        return None
    latest = json.loads(Path(latest_path).read_text(encoding="utf-8"))
    recorded_dir = latest.get(mode)
    if not recorded_dir:
        return None

    current = Path(recorded_dir)
    for candidate in (current, *current.parents):
        if (candidate / "batch_manifest.json").is_file():
            return str(candidate)
    return None
