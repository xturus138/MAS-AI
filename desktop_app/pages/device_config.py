"""Device Configuration screen, wired to real ADB device data."""

from __future__ import annotations

from typing import Any

from nicegui import ui

from adapters.device.adb_adapter import ADBAdapter
from desktop_app.data.adb_actions import (
    check_readiness,
    clear_app_data,
    # install_apk, is_package_installed: staged for the upcoming Install APK
    # file-picker wiring; not yet called anywhere in this file.
    install_apk,
    is_package_installed,
    wake_screen,
)
from desktop_app.data.adb_devices import list_devices, read_device_specs
from desktop_app.shell import render_shell
from desktop_app.state import APP_STATE

_connected_device: Any = None


def connect_device(serial: str) -> Any:
    """Connect to *serial* via ADBAdapter. Also serves as "Prepare Device":

    ADBAdapter.connect() -> uiautomator2.connect() already performs the
    one-time device-agent install when needed (adb_adapter.py:22-26); there
    is no separate init step to call, so this function is both operations.
    """
    return ADBAdapter(serial).connect()


def render_device_config_page() -> None:
    global _connected_device

    with render_shell("/device-config"):
        with ui.row().classes("w-full justify-between items-center"):
            ui.label("Device Configuration").classes("text-2xl font-bold text-slate-800")
            ui.button("Save Configuration").props("color=primary")

        readiness_labels: dict[str, ui.label] = {}
        specs_container = ui.column()

        def _refresh_specs_and_readiness() -> None:
            specs_container.clear()
            with specs_container:
                if _connected_device is None:
                    ui.label("Connect a device to see specs.").classes("text-sm text-slate-500 mt-2")
                    return
                specs = read_device_specs(_connected_device.d)
                ui.label(f"Resolution: {specs.resolution}").classes("text-sm text-slate-700")
                ui.label(f"DPI: {specs.dpi}").classes("text-sm text-slate-700")
                ui.label(f"OS Version: Android {specs.os_version}").classes("text-sm text-slate-700")
                ui.label(f"API Level: {specs.api_level}").classes("text-sm text-slate-700")

            readiness = check_readiness(_connected_device.d if _connected_device else None)
            for key, value in (
                ("ADB Connection", readiness.adb_connected),
                ("Screen State", readiness.screen_awake),
                ("Keyboard", readiness.keyboard_dismissed),
                ("Service", readiness.service_ready),
            ):
                if key in readiness_labels:
                    readiness_labels[key].set_text("OK" if value else "Not Ready")

        with ui.row().classes("w-full gap-4 mt-4 items-start"):
            with ui.column().classes("gap-4").style("flex: 2;"):
                with ui.card().classes("w-full p-5"):
                    ui.label("Device Selector").classes("font-semibold text-slate-800")
                    device_select = ui.select([], label="Select Active Device").classes("w-full mt-2")

                    def _refresh_devices() -> None:
                        devices = list_devices()
                        device_select.set_options(
                            {d.serial: f"{d.model or d.serial} ({d.state})" for d in devices}
                        )

                    def _on_device_selected(event: Any) -> None:
                        global _connected_device
                        serial = event.value
                        if not serial:
                            return
                        try:
                            _connected_device = connect_device(serial)
                            APP_STATE.target_device = serial
                            ui.notify(f"Connected to {serial}", type="positive")
                        except Exception as error:
                            ui.notify(f"Failed to connect: {error}", type="negative")
                            return
                        _refresh_specs_and_readiness()

                    device_select.on_change(_on_device_selected)
                    ui.button("Refresh Devices", on_click=_refresh_devices)
                    _refresh_devices()

                with ui.card().classes("w-full p-5"):
                    ui.label("Target Application (AUT)").classes("font-semibold text-slate-800")
                    package_input = ui.input(
                        label="Package Name", value=APP_STATE.aut_package or ""
                    ).classes("w-full mt-2")

                    def _current_package() -> str:
                        return package_input.value or ""

                    def _install() -> None:
                        ui.notify("Use the file picker to select an APK first (Install APK dialog not yet wired to a file chooser in this task).")

                    def _launch() -> None:
                        if _connected_device is None:
                            ui.notify("Connect a device first.", type="warning")
                            return
                        _connected_device.app_start(_current_package())
                        ui.notify(f"Launched {_current_package()}")

                    def _clear() -> None:
                        if _connected_device is None:
                            ui.notify("Connect a device first.", type="warning")
                            return
                        success = clear_app_data(_connected_device.d, _current_package())
                        ui.notify("Data cleared" if success else "Clear failed", type="positive" if success else "negative")

                    with ui.row().classes("gap-2 mt-2"):
                        ui.button("Install APK", on_click=_install)
                        ui.button("Launch App", on_click=_launch)
                        ui.button("Clear Data", on_click=_clear)

                    def _prepare_device() -> None:
                        global _connected_device
                        serial = APP_STATE.target_device
                        if not serial:
                            ui.notify("Select a device first.", type="warning")
                            return
                        try:
                            _connected_device = connect_device(serial)
                            ui.notify("Device prepared.", type="positive")
                        except Exception as error:
                            ui.notify(f"Prepare failed: {error}", type="negative")
                            return
                        _refresh_specs_and_readiness()

                    ui.button("Prepare Device", on_click=_prepare_device).props("color=secondary").classes("mt-2")

            with ui.column().classes("gap-4").style("flex: 1;"):
                with ui.card().classes("w-full p-5"):
                    ui.label("Device Specs (Auto-Detected)").classes("font-semibold text-slate-800")
                    specs_container

                with ui.card().classes("w-full p-5"):
                    ui.label("System Readiness Checklist").classes("font-semibold text-slate-800")
                    for item in ("ADB Connection", "Screen State", "Keyboard", "Service"):
                        with ui.row().classes("w-full justify-between mt-1"):
                            ui.label(item).classes("text-sm text-slate-600")
                            readiness_labels[item] = ui.label("—").classes("text-sm text-slate-400")
                    with ui.row().classes("gap-2 mt-3"):
                        ui.button(
                            "Wake Up Screen",
                            on_click=lambda: (
                                wake_screen(_connected_device.d) if _connected_device else ui.notify("Connect a device first.", type="warning")
                            ),
                        )
                        ui.button(
                            "Test Screencap",
                            on_click=lambda: (
                                _connected_device.screenshot("desktop_app_test_screencap.png")
                                if _connected_device
                                else ui.notify("Connect a device first.", type="warning")
                            ),
                        )

        _refresh_specs_and_readiness()
