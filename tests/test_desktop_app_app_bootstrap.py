"""Regression test for Critical #2: Settings writes must actually take effect.

shared/config.py:4 calls a bare load_dotenv() at import time, which knows
nothing about desktop_app.paths.env_file_path() (the per-user app-data .env
that the Settings screen writes to via desktop_app.data.settings.write_settings).
desktop_app/app.py must load that managed .env file, with override=True,
before any of its own imports can transitively trigger shared.config's
module-level load_dotenv() -- otherwise a value saved in Settings never
reaches os.environ, and shared.config's module-level constants (e.g.
TARGET_DEVICE, read once at import time and consumed elsewhere via
vars(config)) stay silently stale.

This test proves the bootstrap ordering end-to-end by running the import
sequence in a FRESH SUBPROCESS, not by mutating sys.modules in-process.
Popping "shared.config" from sys.modules and reimporting it would create a
second, disconnected module object -- every other already-imported module
in this repo that did `from shared import config` (e.g.
desktop_app.data.manifest) keeps its own direct reference to the ORIGINAL
module object, so in-process module-cache tricks cannot actually prove the
real, single-process import order a packaged .exe would use. A subprocess
sidesteps this entirely: it is a genuinely fresh interpreter, so
shared.config is imported at most once, in real import order, exactly as it
would be for a real user launching the app.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


def test_settings_value_reaches_shared_config_after_app_bootstrap(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    from desktop_app.data.settings import write_settings

    write_settings({"TARGET_DEVICE": "TEST123"})

    repo_root = Path(__file__).resolve().parent.parent
    subprocess_env = {**os.environ, "LOCALAPPDATA": str(tmp_path)}
    subprocess_env.pop("TARGET_DEVICE", None)

    probe = textwrap.dedent(
        """
        import desktop_app.app  # noqa: F401 -- triggers the managed-.env bootstrap
        import shared.config as shared_config

        # Assert on the actual module-level constant, not just os.environ.
        # shared/config.py:12 reads TARGET_DEVICE = os.getenv(...) once at
        # import time; core/workflow/predefined/runner.py harvests config via
        # vars(config), so this baked constant -- not os.environ itself -- is
        # what the rest of the app actually consumes. A fix that reorders
        # load_dotenv() calls without winning this race would leave
        # os.environ correct while shared.config.TARGET_DEVICE stays stale,
        # and only asserting on os.environ would miss that entirely.
        assert shared_config.TARGET_DEVICE == "TEST123", (
            f"expected TEST123, got {shared_config.TARGET_DEVICE!r}"
        )
        print("BOOTSTRAP_OK")
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=subprocess_env,
        cwd=str(repo_root),
        timeout=60,
    )

    assert "BOOTSTRAP_OK" in result.stdout, (
        f"subprocess bootstrap check failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
