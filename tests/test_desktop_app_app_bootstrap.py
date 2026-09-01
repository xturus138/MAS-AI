"""Regression test for Critical #2: Settings writes must actually take effect.

shared/config.py:4 calls a bare load_dotenv() at import time, which knows
nothing about desktop_app.paths.env_file_path() (the per-user app-data .env
that the Settings screen writes to via desktop_app.data.settings.write_settings).
desktop_app/app.py must load that managed .env file, with override=True,
before any of its own imports can transitively trigger shared.config's
module-level load_dotenv() -- otherwise a value saved in Settings never
reaches os.environ and the app silently keeps using stale/default config.

This test proves the bootstrap ordering end-to-end: write a value through the
real Settings persistence helper, force desktop_app.app's module-level code
to re-run, and assert the value landed in os.environ.
"""

from __future__ import annotations

import importlib
import os
import sys


def test_settings_value_reaches_os_environ_after_app_bootstrap(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    from desktop_app.data.settings import write_settings

    write_settings({"TARGET_DEVICE": "TEST123"})

    # Simulate a fresh process import of desktop_app.app: drop it from the
    # module cache so its top-level load_dotenv(..., override=True) call
    # actually executes again in this test (a plain import is a no-op once
    # the module is already cached).
    sys.modules.pop("desktop_app.app", None)

    monkeypatch.delenv("TARGET_DEVICE", raising=False)

    importlib.import_module("desktop_app.app")

    assert os.environ["TARGET_DEVICE"] == "TEST123"
