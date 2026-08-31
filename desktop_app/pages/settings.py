"""Settings screen — the only place QA edits provider/device/Figma config.

Writes to the desktop app's own managed .env (desktop_app/data/settings.py),
never to the repo's own .env. Every field here requires an app restart to
take effect, since shared/config.py reads environment variables once at
import time — this screen must not claim a value is live before restart.
"""

from __future__ import annotations

from nicegui import ui

from desktop_app.data.settings import SETTINGS_FIELDS, read_settings, write_settings
from desktop_app.shell import render_shell

RESTART_REQUIRED_FIELDS: frozenset[str] = frozenset(SETTINGS_FIELDS)


def render_settings_page() -> None:
    with render_shell("/settings"):
        ui.label("Settings").classes("text-2xl font-bold text-slate-800")
        ui.label(
            "Changes here are saved immediately but require restarting the app to take effect."
        ).classes("text-sm text-amber-700 bg-amber-50 px-3 py-2 rounded-lg")

        current = read_settings()
        inputs: dict[str, ui.input] = {}

        with ui.card().classes("w-full p-6 mt-4"):
            for field in SETTINGS_FIELDS:
                inputs[field] = ui.input(label=field, value=current.get(field, "")).classes("w-full")

        def _save() -> None:
            write_settings({field: widget.value for field, widget in inputs.items()})
            ui.notify("Settings saved. Restart the app for changes to take effect.", type="positive")

        ui.button("Save Settings", on_click=_save).props("color=primary")
