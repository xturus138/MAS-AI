"""Process-wide UI state shared across screens.

This is intentionally NOT persisted to disk — it is the in-memory "what is
currently selected" state for one running app session (which workbook is
loaded, which device is active). Durable state (batch progress, run
history) always lives in the existing on-disk artifacts read by
desktop_app.data.* modules, never here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppState:
    xlsx_path: str | None = None
    target_device: str | None = None
    aut_package: str | None = None
    active_run_root: str | None = None

    def set_xlsx_path(self, path: str) -> None:
        self.xlsx_path = path


APP_STATE = AppState()
