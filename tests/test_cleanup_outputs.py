import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "cleanup_outputs.py"


def test_apply_archives_flat_llm_logs_by_date_without_deleting_them(tmp_path):
    output_root = tmp_path / "outputs"
    legacy_logs = output_root / "llm_logs"
    legacy_logs.mkdir(parents=True)
    source = legacy_logs / "observer_20260729_135013_542385_0.json"
    source.write_text('{"agent": "observer"}', encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(output_root), "--apply"],
        capture_output=True,
        text=True,
        check=False,
    )

    destination = (
        output_root
        / "archive"
        / "llm_logs"
        / "2026-07-29"
        / source.name
    )
    assert result.returncode == 0, result.stderr
    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == '{"agent": "observer"}'


def test_dry_run_reports_flat_llm_log_but_leaves_it_in_place(tmp_path):
    output_root = tmp_path / "outputs"
    legacy_logs = output_root / "llm_logs"
    legacy_logs.mkdir(parents=True)
    source = legacy_logs / "unknown_agent_without_timestamp.json"
    source.write_text("{}", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(output_root), "--dry-run"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert source.exists()
    assert "archive" in result.stdout
    assert "unknown-date" in result.stdout
