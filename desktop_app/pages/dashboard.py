"""Dashboard screen — device/config summary, live mirror, progress, trace.

Task 17 wires Start/Stop/Resume and live push updates; this task lays out
the static structure and shows the last known progress from disk so the
screen is never blank even before a batch has run in this app session.
"""

from __future__ import annotations

from nicegui import ui

from desktop_app.data.manifest import BatchProgress, compute_progress, find_latest_run_root, read_manifest
from desktop_app.shell import render_shell
from desktop_app.state import APP_STATE


def batch_progress_text(progress: BatchProgress | None) -> str:
    if progress is None:
        return "0 / 0 Scenarios"
    completed = progress.passed + progress.failed + progress.stalled + progress.technical_error
    return f"{completed} / {progress.total} Scenarios"


def render_dashboard_page() -> None:
    with render_shell("/"):
        with ui.row().classes("w-full gap-4 items-start no-wrap"):
            with ui.column().classes("gap-4").style("width: 320px;"):
                with ui.card().classes("w-full p-5"):
                    ui.label("Device & Config").classes("font-semibold text-slate-800")
                    ui.label(f"Device: {APP_STATE.target_device or 'Not configured'}").classes(
                        "text-sm text-slate-600 mt-2"
                    )
                    ui.label(f"Workbook: {APP_STATE.xlsx_path or 'Not loaded'}").classes(
                        "text-sm text-slate-600"
                    )
                with ui.card().classes("w-full p-5"):
                    ui.label("Action Controls").classes("font-semibold text-slate-800")
                    with ui.column().classes("w-full gap-2 mt-3"):
                        ui.button("Start Batch").props("color=primary").classes("w-full")
                        ui.button("Stop").props("outline color=red").classes("w-full")
                        ui.button("Resume").props("outline").classes("w-full")

            with ui.card().classes("p-4").style("width: 400px;"):
                ui.label("Live Device Mirror").classes("text-sm font-semibold text-slate-500")
                ui.image("").classes("w-full h-[600px] bg-slate-100 rounded-lg mt-2")

            with ui.column().classes("gap-4 flex-grow"):
                run_root = find_latest_run_root("predefined")
                manifest = read_manifest(run_root) if run_root else None
                progress = compute_progress(manifest) if manifest else None

                with ui.card().classes("w-full p-5"):
                    with ui.row().classes("w-full justify-between items-center"):
                        ui.label("Batch Progress").classes("font-semibold text-slate-800")
                        ui.label(batch_progress_text(progress)).classes("text-sm text-slate-500")
                    if progress:
                        completed = progress.passed + progress.failed + progress.stalled + progress.technical_error
                        ui.linear_progress(
                            value=(completed / progress.total) if progress.total else 0.0
                        ).classes("w-full mt-2")
                        with ui.row().classes("gap-3 mt-3"):
                            ui.label(f"Passed: {progress.passed}").classes("text-emerald-700")
                            ui.label(f"Failed: {progress.failed}").classes("text-red-700")
                            ui.label(f"Pending: {progress.pending}").classes("text-slate-500")

                with ui.card().classes("w-full p-5 flex-grow"):
                    ui.label("Agent Reasoning Trace").classes("font-semibold text-slate-800")
                    ui.column().classes("w-full h-[400px] overflow-y-auto mt-3 gap-1")
