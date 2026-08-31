"""Device Configuration screen.

Real device enumeration/specs/install/prepare wiring lands in Tasks 19-22
(desktop_app/data/adb.py); this task only establishes the screen structure.
"""

from __future__ import annotations

from nicegui import ui

from desktop_app.shell import render_shell
from desktop_app.state import APP_STATE


def render_device_config_page() -> None:
    with render_shell("/device-config"):
        with ui.row().classes("w-full justify-between items-center"):
            ui.label("Device Configuration").classes("text-2xl font-bold text-slate-800")
            ui.button("Save Configuration").props("color=primary")

        with ui.row().classes("w-full gap-4 mt-4 items-start"):
            with ui.column().classes("gap-4").style("flex: 2;"):
                with ui.card().classes("w-full p-5"):
                    ui.label("Device Selector").classes("font-semibold text-slate-800")
                    device_select = ui.select([], label="Select Active Device").classes("w-full mt-2")
                    ui.button(
                        "Refresh Devices",
                        on_click=lambda: ui.notify("Device enumeration wiring lands in Task 20."),
                    )

                with ui.card().classes("w-full p-5"):
                    ui.label("Target Application (AUT)").classes("font-semibold text-slate-800")
                    package_input = ui.input(
                        label="Package Name", value=APP_STATE.aut_package or ""
                    ).classes("w-full mt-2")
                    package_input.on(
                        "update:model-value", lambda e: setattr(APP_STATE, "aut_package", e.args)
                    )
                    with ui.row().classes("gap-2 mt-2"):
                        ui.button("Install APK")
                        ui.button("Launch App")
                        ui.button("Clear Data")
                    ui.button("Prepare Device").props("color=secondary").classes("mt-2")

            with ui.column().classes("gap-4").style("flex: 1;"):
                with ui.card().classes("w-full p-5"):
                    ui.label("Device Specs (Auto-Detected)").classes("font-semibold text-slate-800")
                    ui.label("Connect a device to see specs.").classes("text-sm text-slate-500 mt-2")

                with ui.card().classes("w-full p-5"):
                    ui.label("System Readiness Checklist").classes("font-semibold text-slate-800")
                    for item in ("ADB Connection", "Screen State", "Keyboard", "Service"):
                        with ui.row().classes("w-full justify-between mt-1"):
                            ui.label(item).classes("text-sm text-slate-600")
                            ui.label("—").classes("text-sm text-slate-400")
                    with ui.row().classes("gap-2 mt-3"):
                        ui.button("Wake Up Screen")
                        ui.button("Test Screencap")
