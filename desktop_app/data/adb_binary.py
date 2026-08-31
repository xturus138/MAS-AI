"""Resolves which adb binary to invoke: bundled (packaged .exe) or system PATH.

The bundled binary is placed at desktop_app/vendor/platform-tools/adb.exe by
Task 23's PyInstaller packaging step (Android platform-tools is
redistributable). Falls back to a bare "adb" (relies on the caller's PATH)
for local development where the vendored binary hasn't been placed yet.
"""

from __future__ import annotations

from pathlib import Path

_VENDOR_ADB_PATH = Path(__file__).parent.parent / "vendor" / "platform-tools" / "adb.exe"


def resolve_adb_path() -> str:
    if _VENDOR_ADB_PATH.is_file():
        return str(_VENDOR_ADB_PATH)
    return "adb"
