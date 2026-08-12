"""Behavior checks for the Windows launcher of the Bayesian notebook."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = REPOSITORY_ROOT / "run_bayesian_notebook.cmd"


def run_launcher(*arguments: str) -> subprocess.CompletedProcess[str]:
    command = f'call "{LAUNCHER}" {" ".join(arguments)}'

    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
        shell=True,
    )


def test_help_describes_the_available_notebook_modes() -> None:
    result = run_launcher("help")

    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "fast" in result.stdout
    assert "BAYESIAN_NOTEBOOK_RUN_E5" in result.stdout


def test_unknown_mode_is_rejected_without_starting_jupyter() -> None:
    result = run_launcher("unexpected")

    assert result.returncode == 2
    assert "Unknown mode: unexpected" in result.stdout


def test_launcher_does_not_pass_notebook_dir_with_a_notebook_path() -> None:
    launcher_source = LAUNCHER.read_text(encoding="utf-8")

    assert "--notebook-dir" not in launcher_source
    assert 'set "NOTEBOOK_PATH=%PROJECT_ROOT%experiment\\bayesian\\bayesian_dummy_closed_loop.ipynb"' in launcher_source
    assert '"%PYTHON%" -m jupyter lab "%NOTEBOOK_PATH%"' in launcher_source
