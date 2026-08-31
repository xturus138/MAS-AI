from __future__ import annotations

from pathlib import Path

from desktop_app.data.adb_binary import resolve_adb_path


def test_resolve_adb_path_prefers_bundled_binary_when_present(monkeypatch, tmp_path):
    bundled = tmp_path / "vendor" / "platform-tools" / "adb.exe"
    bundled.parent.mkdir(parents=True)
    bundled.write_text("fake adb binary")
    monkeypatch.setattr("desktop_app.data.adb_binary._VENDOR_ADB_PATH", bundled)

    assert resolve_adb_path() == str(bundled)


def test_resolve_adb_path_falls_back_to_system_path_when_not_bundled(monkeypatch, tmp_path):
    missing = tmp_path / "vendor" / "platform-tools" / "adb.exe"
    monkeypatch.setattr("desktop_app.data.adb_binary._VENDOR_ADB_PATH", missing)

    assert resolve_adb_path() == "adb"
