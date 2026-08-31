"""Writable app-data locations for the desktop app's own local state.

Never write here QA-facing test data (scenario.xlsx, outputs/) — that
continues to live wherever the existing codebase already puts it
(shared.config.OUTPUT_DIR, the picked scenario.xlsx's own path). This module
is only for the app's own config (.env) and small local-only state.
"""

from __future__ import annotations

import os
from pathlib import Path


def app_data_dir() -> Path:
    """Return (and create) the per-user writable directory for this app."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        directory = Path(local_app_data) / "MASAIOrchestrator"
    else:
        directory = Path.home() / ".mas_ai_orchestrator"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def env_file_path() -> Path:
    """Return the path to the desktop app's managed .env file."""
    return app_data_dir() / ".env"
