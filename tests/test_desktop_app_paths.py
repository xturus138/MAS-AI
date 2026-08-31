from __future__ import annotations

import os
from pathlib import Path

from desktop_app.paths import app_data_dir, env_file_path


def test_app_data_dir_is_under_localappdata_on_windows(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    result = app_data_dir()
    assert result == tmp_path / "MASAIOrchestrator"
    assert result.is_dir()


def test_env_file_path_lives_inside_app_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert env_file_path() == app_data_dir() / ".env"


def test_app_data_dir_falls_back_to_home_when_localappdata_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    result = app_data_dir()
    assert result == tmp_path / ".mas_ai_orchestrator"
    assert result.is_dir()
