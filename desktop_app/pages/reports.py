"""Reports & Evidence screen."""

from __future__ import annotations

import os

from nicegui import ui

from desktop_app.data.reports import list_report_rows, summarize_run
from desktop_app.pages.test_suites import STATUS_LABELS
from desktop_app.shell import render_shell


def format_duration(total_seconds: float) -> str:
    total_seconds = int(total_seconds)
    minutes, seconds = divmod(total_seconds, 60)
    if minutes == 0:
        return f"{seconds}s"
    return f"{minutes}m {seconds}s"


def render_reports_page(run_root: str | None) -> None:
    with render_shell("/reports"):
        ui.label("MAS AI - Execution Reports & Evidence").classes("text-2xl font-bold text-slate-800")

        if not run_root:
            ui.label("No completed run yet.").classes("text-slate-600")
            return

        summary = summarize_run(run_root)
        if summary is None:
            ui.label("No completed run yet.").classes("text-slate-600")
            return

        with ui.row().classes("gap-4"):
            with ui.card().classes("p-4"):
                ui.label("Pass Rate").classes("text-xs text-slate-500")
                ui.label(f"{summary.pass_rate:.1f}%").classes("text-2xl font-bold")
                ui.label(
                    f"{summary.progress.passed} PASS / {summary.progress.failed} FAIL"
                ).classes("text-xs text-slate-500")
            with ui.card().classes("p-4"):
                ui.label("Duration").classes("text-xs text-slate-500")
                ui.label(format_duration(summary.duration_seconds)).classes("text-2xl font-bold")

        with ui.row().classes("gap-3 mt-4"):
            ui.button(
                "Open Excel Report (.xlsx)",
                on_click=lambda: os.startfile(os.path.join(run_root, "test_report.xlsx")),
            )
            ui.button("Open Evidence Folder", on_click=lambda: os.startfile(run_root))

        columns = [
            {"name": "tcs_id", "label": "TC ID", "field": "tcs_id"},
            {"name": "status_label", "label": "Status", "field": "status_label"},
            {"name": "duration", "label": "Execution Time", "field": "duration"},
            {"name": "recovery_used", "label": "Recovery Used", "field": "recovery_used"},
        ]
        rows = [
            {
                "tcs_id": row.tcs_id,
                "status_label": STATUS_LABELS.get(row.status, row.status),
                "duration": format_duration(row.duration_seconds),
                "recovery_used": "Yes" if row.recovery_used else "No",
            }
            for row in list_report_rows(run_root)
        ]
        ui.table(columns=columns, rows=rows, row_key="tcs_id").classes("w-full mt-4")
