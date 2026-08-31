"""Test Suites Management screen.

Workbook-agnostic: the loaded scenario.xlsx is picked via a native file
dialog (Step 6), never a hardcoded scenarios/firebase_chat/ path.
"""

from __future__ import annotations

from nicegui import ui

from core.workflow.predefined.batch import TERMINAL_STATUSES
from desktop_app.data.manifest import find_latest_run_root, read_manifest
from desktop_app.data.workbook import UNTESTED, load_workbook_cases
from desktop_app.shell import render_shell

STATUS_LABELS: dict[str, str] = {
    UNTESTED: "Untested",
    "success": "Pass",
    "functional_anomaly": "Fail",
    "stagnated": "Stalled",
    "technical_error": "Technical Error",
}

STATUS_COLOR_CLASSES: dict[str, str] = {
    UNTESTED: "bg-slate-100 text-slate-600",
    "success": "bg-emerald-100 text-emerald-700",
    "functional_anomaly": "bg-red-100 text-red-700",
    "stagnated": "bg-amber-100 text-amber-700",
    "technical_error": "bg-purple-100 text-purple-700",
}


def run_selected_is_unlocked(manifest: dict | None, total_workbook_cases: int) -> bool:
    """True only when a full run against THIS exact workbook has completed.

    Rationale (spec: Test Suites Management "Run Selected"): bridge/recovery
    navigation needs each case's starting-screen data from a prior full run
    before a partial subset run can compute a correct recovery path. A
    manifest whose case count no longer matches the currently loaded
    workbook (edited since the last run) does not count as "this workbook's"
    full run, and re-locks the control.
    """
    if manifest is None:
        return False
    cases = manifest.get("cases", [])
    if len(cases) != total_workbook_cases or total_workbook_cases == 0:
        return False
    return all(case.get("status") in TERMINAL_STATUSES for case in cases)


def render_test_suites_page(xlsx_path: str | None) -> None:
    with render_shell("/test-suites"):
        ui.label("Test Suites Management").classes("text-2xl font-bold text-slate-800")

        if not xlsx_path:
            with ui.card().classes("w-full p-6"):
                ui.label("No scenario workbook loaded yet.").classes("text-slate-600")
                ui.button("Browse for scenario.xlsx...", on_click=lambda: ui.notify(
                    "File picker wiring lands with the OS-native dialog in Task 10."
                ))
            return

        run_root = find_latest_run_root("predefined")
        manifest = read_manifest(run_root) if run_root else None
        cases = load_workbook_cases(xlsx_path, manifest)

        with ui.row().classes("items-center gap-3"):
            ui.label(f"Path: {xlsx_path}").classes("text-sm text-slate-500 font-mono")
            ui.label(f"Total Cases: {len(cases)}").classes(
                "text-xs bg-slate-100 px-2 py-1 rounded-full text-slate-600"
            )

        unlocked = run_selected_is_unlocked(manifest, len(cases))
        with ui.row().classes("items-center gap-3"):
            ui.button(f"Run All {len(cases)}").props("color=primary")
            run_selected_button = ui.button(f"Run Selected (0)")
            run_selected_button.set_enabled(unlocked)
            if not unlocked:
                run_selected_button.tooltip(
                    "Run the full suite once first — partial re-runs need a completed "
                    "full run of this exact workbook to compute recovery paths."
                )

        columns = [
            {"name": "tcs_id", "label": "TC ID", "field": "tcs_id"},
            {"name": "module", "label": "Module", "field": "module"},
            {"name": "scenario_title", "label": "Scenario Title", "field": "scenario_title"},
            {"name": "steps", "label": "Steps", "field": "steps"},
            {"name": "precondition", "label": "Precondition", "field": "precondition"},
            {"name": "status_label", "label": "Last Verdict", "field": "status_label"},
        ]
        rows = [
            {
                "tcs_id": case.tcs_id,
                "module": case.module,
                "scenario_title": case.scenario_title,
                "steps": case.steps,
                "precondition": case.precondition,
                "status_label": STATUS_LABELS.get(case.status, case.status),
            }
            for case in cases
        ]
        ui.table(columns=columns, rows=rows, row_key="tcs_id").classes("w-full")
