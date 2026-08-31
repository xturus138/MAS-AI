"""Documentation screen — a static, QA-audience user guide.

Not a rendering of CLAUDE.md/README.md (those are developer-facing). This
content is authored for a QA tester with no source-code access.
"""

from __future__ import annotations

from nicegui import ui

from desktop_app.shell import render_shell

DOC_SECTIONS: list[tuple[str, str]] = [
    (
        "Preparing a Device",
        "Go to **Device Config**, select your connected Android device, and "
        "click **Prepare Device**. This installs a small helper agent on the "
        "device the first time you use it — you only need to do this once "
        "per device. Once the System Readiness Checklist shows all items OK, "
        "the device is ready to test with.",
    ),
    (
        "Loading a Scenario Workbook",
        "Go to **Test Suites**, click **Browse for scenario.xlsx...**, and "
        "pick the workbook containing the test cases you want to run. Any "
        "workbook in the expected format works — you are not limited to one "
        "specific app or test set.",
    ),
    (
        "Running a Batch",
        "From the **Dashboard**, click **Start Batch** to run every case in "
        "the loaded workbook in order. Click **Stop** to halt safely after "
        "the case currently running finishes. If a run was stopped or "
        "interrupted, **Resume** continues from where it left off without "
        "re-running cases that already finished.",
    ),
    (
        "Understanding Test Statuses",
        "Every test case ends in one of five states: **Untested** (not run "
        "yet), **Pass** (worked as expected), **Fail** (the app behaved "
        "incorrectly — a real defect), **Stalled** (the test could not "
        "make progress and needs investigation), or **Technical Error** "
        "(a tooling/infrastructure problem, not a defect in the app being "
        "tested).",
    ),
    (
        "Reading Reports & Evidence",
        "Go to **Reports** to see the pass rate, duration, and a full list "
        "of every case's outcome for the most recent run. Click a row's "
        "evidence link, or use **Open Evidence Folder** / **Open Excel "
        "Report (.xlsx)**, to see the exact screenshots and details behind "
        "any result.",
    ),
]


def render_documentation_page() -> None:
    with render_shell("/documentation"):
        ui.label("Documentation").classes("text-2xl font-bold text-slate-800")
        for heading, body in DOC_SECTIONS:
            with ui.card().classes("w-full p-5 mt-3"):
                ui.label(heading).classes("text-lg font-semibold text-slate-800")
                ui.markdown(body).classes("text-sm text-slate-600 mt-2")
