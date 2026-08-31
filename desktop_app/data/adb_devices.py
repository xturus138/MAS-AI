"""ADB device enumeration and spec reading.

list_devices() shells out to the bundled/system adb binary directly (there is
no existing multi-device enumeration anywhere in ADBAdapter/shared.config,
which only ever addresses a single TARGET_DEVICE serial). read_device_specs()
instead takes an already-connected uiautomator2 device object and reuses the
exact d.info/d.shell calls ADBAdapter already wraps, rather than introducing
a second device abstraction.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from desktop_app.data.adb_binary import resolve_adb_path

_DEVICE_LINE_RE = re.compile(
    r"^(?P<serial>\S+)\s+(?P<state>\S+)(?P<rest>.*)$"
)
_MODEL_RE = re.compile(r"model:(\S+)")


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    state: str
    model: str | None


@dataclass(frozen=True)
class DeviceSpecs:
    resolution: str
    dpi: int | None
    os_version: str | None
    api_level: int | None


def list_devices(run_fn: Callable[..., Any] = subprocess.run) -> list[DeviceInfo]:
    adb_path = resolve_adb_path()
    result = run_fn([adb_path, "devices", "-l"], capture_output=True, text=True, timeout=10)
    devices: list[DeviceInfo] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("List of devices"):
            continue
        match = _DEVICE_LINE_RE.match(line)
        if not match:
            continue
        model_match = _MODEL_RE.search(match.group("rest"))
        devices.append(
            DeviceInfo(
                serial=match.group("serial"),
                state=match.group("state"),
                model=model_match.group(1) if model_match else None,
            )
        )
    return devices


def _extract_int(text: str) -> int | None:
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


def read_device_specs(device: Any) -> DeviceSpecs:
    width = device.info.get("displayWidth")
    height = device.info.get("displayHeight")
    resolution = f"{width}x{height}" if width and height else ""

    density_output = device.shell("wm density").output
    os_version_output = device.shell("getprop ro.build.version.release").output
    api_level_output = device.shell("getprop ro.build.version.sdk").output

    return DeviceSpecs(
        resolution=resolution,
        dpi=_extract_int(density_output),
        os_version=os_version_output.strip() or None,
        api_level=_extract_int(api_level_output),
    )
