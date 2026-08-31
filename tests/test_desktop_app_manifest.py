from __future__ import annotations

import json
from pathlib import Path

from desktop_app.data.manifest import (
    BatchProgress,
    compute_progress,
    find_latest_run_root,
    read_manifest,
)


def _manifest(statuses: list[str]) -> dict:
    return {
        "cases": [
            {"tcs_id": f"TCS-{i:03d}", "status": status}
            for i, status in enumerate(statuses, start=1)
        ]
    }


def test_compute_progress_counts_each_status():
    manifest = _manifest(
        ["success", "success", "functional_anomaly", "stagnated", "technical_error", "not_started"]
    )

    progress = compute_progress(manifest)

    assert progress == BatchProgress(
        total=6, passed=2, failed=1, stalled=1, technical_error=1, pending=1
    )


def test_read_manifest_returns_none_when_missing(tmp_path):
    assert read_manifest(str(tmp_path)) is None


def test_read_manifest_reads_existing_file(tmp_path):
    payload = _manifest(["success"])
    (tmp_path / "batch_manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    assert read_manifest(str(tmp_path)) == payload


def test_find_latest_run_root_walks_up_to_run_directory(tmp_path, monkeypatch):
    from shared import config

    monkeypatch.setattr(config, "OUTPUT_DIR", str(tmp_path))
    run_root = tmp_path / "runs" / "predefined" / "2026-08-31" / "run_1"
    case_dir = run_root / "scenario_01"
    case_dir.mkdir(parents=True)
    (run_root / "batch_manifest.json").write_text("{}", encoding="utf-8")
    indexes_dir = tmp_path / "indexes"
    indexes_dir.mkdir()
    (indexes_dir / "latest.json").write_text(
        json.dumps({"predefined": str(case_dir)}), encoding="utf-8"
    )

    result = find_latest_run_root("predefined")

    assert result == str(run_root)


def test_find_latest_run_root_returns_none_when_no_index(tmp_path, monkeypatch):
    from shared import config

    monkeypatch.setattr(config, "OUTPUT_DIR", str(tmp_path))

    assert find_latest_run_root("predefined") is None
