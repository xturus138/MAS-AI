from __future__ import annotations

from desktop_app.data.settings import read_settings, write_settings


def test_write_then_read_settings_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    write_settings({"OBSERVER_PROVIDER": "openrouter", "TARGET_DEVICE": "ABC123"})
    result = read_settings()

    assert result["OBSERVER_PROVIDER"] == "openrouter"
    assert result["TARGET_DEVICE"] == "ABC123"


def test_write_settings_preserves_unrelated_existing_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    from desktop_app.paths import env_file_path

    env_file_path().write_text("CUSTOM_UNRELATED_KEY=keep-me\n", encoding="utf-8")

    write_settings({"TARGET_DEVICE": "ABC123"})

    content = env_file_path().read_text(encoding="utf-8")
    assert "CUSTOM_UNRELATED_KEY=keep-me" in content
    assert "TARGET_DEVICE=ABC123" in content


def test_read_settings_returns_empty_dict_when_no_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert read_settings() == {}


def test_write_settings_overwrites_existing_managed_key(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    write_settings({"TARGET_DEVICE": "OLD"})
    write_settings({"TARGET_DEVICE": "NEW"})

    assert read_settings()["TARGET_DEVICE"] == "NEW"
