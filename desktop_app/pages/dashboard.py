"""Dashboard screen — device/config summary, live mirror, progress, trace.

Task 17 wires Start/Stop/Resume and live push updates; this task lays out
the static structure and shows the last known progress from disk so the
screen is never blank even before a batch has run in this app session.
"""

from __future__ import annotations

import time
from typing import Any

from nicegui import ui

from desktop_app.data.manifest import BatchProgress, compute_progress, find_latest_run_root, read_manifest
from desktop_app.execution import BatchRunner
from desktop_app.shell import render_shell
from desktop_app.state import APP_STATE


def batch_progress_text(progress: BatchProgress | None) -> str:
    if progress is None:
        return "0 / 0 Scenarios"
    completed = progress.passed + progress.failed + progress.stalled + progress.technical_error
    return f"{completed} / {progress.total} Scenarios"


class DashboardLiveState:
    """Drop-in substitute for visual.monitor.TkDashboard's push API.

    Passed into core/workflow/predefined/runner.py's runtime factory in
    place of VisualMonitor, so _DashboardWrappedExecutor's existing
    monitor.push_progress(...)/monitor.push_log(...) calls
    (runner.py:322-330, 337-345) land here instead of spawning a second web
    server (spec: Architecture, "retires visual/monitor.py's standalone
    web-server mode").
    """

    def __init__(self) -> None:
        self.scenario_title: str = "Idle"
        self.log_lines: list[tuple[str, str, str]] = []

    def push_progress(self, scenario_idx: int = 0, scenario_total: int = 0,
                       step_idx: int = 0, step_total: int = 0,
                       tcs_id: str = "", status: str = "") -> None:
        self.scenario_title = tcs_id or "Running Batch..."

    def push_log(self, component: str, message: str, detail: str = "") -> None:
        timestamp = time.strftime("%H:%M:%S")
        text = f"{message} {detail}".strip()
        self.log_lines.append((timestamp, component.upper(), text))
        if len(self.log_lines) > 200:
            self.log_lines.pop(0)


LIVE_STATE = DashboardLiveState()


def _run_predefined_with_live_state(xlsx_path: str, **kwargs) -> Any:
    from core.workflow.predefined.runner import run_predefined

    return run_predefined(xlsx_path, dashboard=LIVE_STATE, **kwargs)


BATCH_RUNNER = BatchRunner(run_predefined_fn=_run_predefined_with_live_state)


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
                # Toast-spam guard for _refresh_trace's ui.timer below: a
                # batch failure (exception or silent preflight failure) must
                # notify exactly once, not on every 1s timer tick. Armed
                # (False) whenever a new batch is actually started; flipped
                # to True the first time _refresh_trace reports on it.
                notification_state = {"notified_this_run": True}

                with ui.card().classes("w-full p-5"):
                    ui.label("Action Controls").classes("font-semibold text-slate-800")

                    def _start() -> None:
                        if not APP_STATE.xlsx_path:
                            ui.notify("Load a scenario workbook on Test Suites first.", type="warning")
                            return
                        notification_state["notified_this_run"] = False
                        BATCH_RUNNER.start(APP_STATE.xlsx_path)

                    def _resume() -> None:
                        run_root = find_latest_run_root("predefined")
                        if not APP_STATE.xlsx_path or not run_root:
                            ui.notify("Nothing to resume yet.", type="warning")
                            return
                        notification_state["notified_this_run"] = False
                        BATCH_RUNNER.start(APP_STATE.xlsx_path, resume=run_root)

                    with ui.column().classes("w-full gap-2 mt-3"):
                        ui.button("Start Batch", on_click=_start).props("color=primary").classes("w-full")
                        ui.button(
                            "Stop",
                            on_click=lambda: ui.notify(
                                "Stop takes effect after the current case finishes."
                            ),
                        ).props("outline color=red").classes("w-full")
                        ui.button("Resume", on_click=_resume).props("outline").classes("w-full")

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
                    trace_column = ui.column().classes("w-full h-[400px] overflow-y-auto mt-3 gap-1")

        def _is_preflight_failure(result: Any) -> bool:
            """True when run_predefined_fn returned something other than a
            normal batch-completion manifest.

            run_predefined() returns None or a PreflightReport object (not an
            exception) when preflight fails -- e.g. no device connected, a
            bad workbook, or a config validation failure. A successful batch
            completion is a dict with a "cases" key, so anything else after a
            run has actually finished counts as a silent preflight failure
            that must be surfaced.
            """
            if not isinstance(result, dict) or "cases" not in result:
                return True
            return False

        def _refresh_trace() -> None:
            if not BATCH_RUNNER.is_running() and not notification_state["notified_this_run"]:
                notification_state["notified_this_run"] = True
                error = BATCH_RUNNER.last_error()
                if error is not None:
                    ui.notify(f"Batch run failed: {error}", type="negative")
                elif _is_preflight_failure(BATCH_RUNNER.last_result()):
                    ui.notify(
                        "Batch did not start: preflight failed (check device connection, "
                        "workbook, and configuration).",
                        type="negative",
                    )

            trace_column.clear()
            with trace_column:
                for timestamp, component, message in LIVE_STATE.log_lines[-40:]:
                    ui.label(f"[{timestamp}] [{component}] {message}").classes("text-xs text-slate-600")

        ui.timer(1.0, _refresh_trace)
