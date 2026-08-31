"""System Logs screen — the QA-safe substitute for tailing process.log."""

from __future__ import annotations

import os
from pathlib import Path

from nicegui import ui

from desktop_app.data.process_log import filter_entries, parse_log_lines
from desktop_app.shell import render_shell

COMPONENT_FILTER_OPTIONS: list[str] = [
    "All", "ORCHESTRATOR", "OBSERVER", "DECIDER", "EXECUTOR", "SYSTEM",
]


def _find_process_log(run_root: str) -> Path | None:
    candidates = sorted(Path(run_root).rglob("process.log"))
    return candidates[-1] if candidates else None


def render_system_logs_page(run_root: str | None) -> None:
    with render_shell("/system-logs"):
        ui.label("System Logs").classes("text-2xl font-bold text-slate-800")

        if not run_root:
            ui.label("No run logs available yet.").classes("text-slate-600")
            return

        log_path = _find_process_log(run_root)
        if log_path is None:
            ui.label("No process.log found for the latest run.").classes("text-slate-600")
            return

        entries = parse_log_lines(log_path.read_text(encoding="utf-8"))

        state = {"component": "All"}
        log_column = ui.column().classes(
            "w-full h-[520px] overflow-y-auto gap-1 p-3 rounded-lg bg-slate-950 font-mono text-xs"
        )

        def _render_entries() -> None:
            log_column.clear()
            component = None if state["component"] == "All" else state["component"]
            with log_column:
                for entry in filter_entries(entries, component=component):
                    ui.label(f"[{entry.timestamp}] [{entry.component}] {entry.message}").classes(
                        "text-slate-200"
                    )

        def _on_filter_change(value: str) -> None:
            state["component"] = value
            _render_entries()

        with ui.row().classes("items-center gap-3"):
            ui.select(COMPONENT_FILTER_OPTIONS, value="All", on_change=lambda e: _on_filter_change(e.value))
            ui.button("Open log folder", on_click=lambda: os.startfile(str(log_path.parent)))

        _render_entries()
