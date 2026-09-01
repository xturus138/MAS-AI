"""Runs run_predefined() on a background thread inside the native app.

Stop semantics: run_predefined()/PredefinedBatchCoordinator have no
in-process cancellation hook -- the coordinator loop (batch.py:87-95) simply
iterates scenarios until done. This BatchRunner's stop() therefore does NOT
interrupt an in-flight run_predefined() call; it only prevents starting a
new one. A genuine "stop after the current case" requires either a future
cooperative-cancellation change to PredefinedBatchCoordinator (out of scope
for this plan) or the user closing the app process entirely, after which
batch_manifest.json is left in a resumable state or resumed
(TERMINAL_STATUSES / _RESUMABLE_STATUSES in core/workflow/predefined/batch.py)
and BatchRunner.start(..., resume=run_root) picks it back up. The Dashboard's
Stop button (Task 18) must be labeled/explained accordingly, not implied to
be instantaneous.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class BatchRunner:
    def __init__(self, run_predefined_fn: Callable[..., Any]) -> None:
        self._run_predefined_fn = run_predefined_fn
        self._thread: threading.Thread | None = None
        self._last_error: Exception | None = None
        self._last_result: Any = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def last_error(self) -> Exception | None:
        with self._lock:
            return self._last_error

    def last_result(self) -> Any:
        """Whatever run_predefined_fn returned on its most recent completed run.

        run_predefined() (core/workflow/predefined/runner.py) signals a
        preflight failure by returning None or a PreflightReport object, not
        by raising -- only a genuine exception goes through last_error().
        Callers (e.g. the Dashboard) must check this to detect a batch that
        "completed" without ever actually running.
        """
        with self._lock:
            return self._last_result

    def start(self, xlsx_path: str, *, resume: str | None = None) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._last_error = None
            self._last_result = None
            self._thread = threading.Thread(
                target=self._run, args=(xlsx_path, resume), daemon=True
            )
            self._thread.start()

    def _run(self, xlsx_path: str, resume: str | None) -> None:
        try:
            result = self._run_predefined_fn(xlsx_path, resume=resume)
        except Exception as error:  # noqa: BLE001 - must never crash the UI thread
            with self._lock:
                self._last_error = error
            return
        with self._lock:
            self._last_result = result
