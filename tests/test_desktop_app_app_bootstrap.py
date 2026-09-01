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


def test_settings_value_reaches_shared_config_after_app_bootstrap(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    from desktop_app.data.settings import write_settings

    write_settings({"TARGET_DEVICE": "TEST123"})

    # Simulate a fresh process import of both desktop_app.app AND
    # shared.config: drop both from the module cache. Popping only
    # desktop_app.app is not enough to prove import ordering -- if
    # shared.config is already cached from an earlier import (as it would be
    # in a real run, since something always imports it first), re-importing
    # desktop_app.app would not re-execute shared.config's own load_dotenv()
    # call, and this test would pass even if app.py's load_dotenv(...) ran
    # too late to matter.
    sys.modules.pop("desktop_app.app", None)
    sys.modules.pop("shared.config", None)

    monkeypatch.delenv("TARGET_DEVICE", raising=False)

    importlib.import_module("desktop_app.app")

    # Assert on the actual module-level constant, not just os.environ.
    # shared/config.py:12 reads TARGET_DEVICE = os.getenv(...) once at
    # import time; core/workflow/predefined/runner.py harvests config via
    # vars(config), so this baked constant -- not os.environ itself -- is
    # what the rest of the app actually consumes. A fix that reorders
    # load_dotenv() calls without winning this race would leave os.environ
    # correct while shared.config.TARGET_DEVICE stays stale, and only
    # asserting on os.environ would miss that entirely.
    shared_config = importlib.import_module("shared.config")
    assert shared_config.TARGET_DEVICE == "TEST123"
    assert os.environ["TARGET_DEVICE"] == "TEST123"
