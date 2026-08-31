"""Install/launch/clear/wake/readiness ADB actions for Device Configuration.

check_readiness() re-implements the keyboard-shown check inline
(dumpsys input_method / "mInputShown=true") rather than calling
ADBAdapter.check_keyboard_state() directly, because that method takes no
device argument (it reads self.d on an ADBAdapter instance) while every
other function in this module takes a bare uiautomator2 device object for
independent testability with a fake — introducing an ADBAdapter dependency
here just for one boolean would couple this module to a class it does not
otherwise need. The underlying shell command and truthy string are
identical, so the two never disagree in practice.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from desktop_app.data.adb_binary import resolve_adb_path


def install_apk(serial: str, apk_path: str, run_fn: Callable[..., Any] = subprocess.run) -> bool:
    adb_path = resolve_adb_path()
    result = run_fn(
        [adb_path, "-s", serial, "install", "-r", apk_path],
        capture_output=True, text=True, timeout=120,
    )
    return "Success" in result.stdout


def is_package_installed(device: Any, package_name: str) -> bool:
    output = device.shell(f"pm list packages {package_name}").output
    return f"package:{package_name}" in output


def clear_app_data(device: Any, package_name: str) -> bool:
    output = device.shell(f"pm clear {package_name}").output
    return "Success" in output


def wake_screen(device: Any) -> None:
    device.shell("input keyevent KEYCODE_WAKEUP")


@dataclass(frozen=True)
class ReadinessChecklist:
    adb_connected: bool
    screen_awake: bool
    keyboard_dismissed: bool
    service_ready: bool


def check_readiness(device: Any) -> ReadinessChecklist:
    if device is None:
        return ReadinessChecklist(
            adb_connected=False, screen_awake=False, keyboard_dismissed=False, service_ready=False
        )
    power_output = device.shell("dumpsys power").output
    input_method_output = device.shell("dumpsys input_method").output
    return ReadinessChecklist(
        adb_connected=True,
        screen_awake="mWakefulness=Awake" in power_output,
        keyboard_dismissed="mInputShown=true" not in input_method_output,
        service_ready=True,
    )
