from __future__ import annotations

from types import SimpleNamespace

from desktop_app.data.adb_devices import DeviceInfo, DeviceSpecs, list_devices, read_device_specs

SAMPLE_DEVICES_OUTPUT = (
    "List of devices attached\n"
    "29011FDFH000    device product:panther model:Pixel_7_Pro device:panther transport_id:1\n"
    "emulator-5554   offline\n"
    "\n"
)


def test_list_devices_parses_serial_state_and_model():
    def fake_run(args, capture_output, text, timeout):
        assert args[-2:] == ["devices", "-l"]
        return SimpleNamespace(stdout=SAMPLE_DEVICES_OUTPUT, returncode=0)

    devices = list_devices(run_fn=fake_run)

    assert devices == [
        DeviceInfo(serial="29011FDFH000", state="device", model="Pixel_7_Pro"),
        DeviceInfo(serial="emulator-5554", state="offline", model=None),
    ]


def test_list_devices_returns_empty_list_when_no_devices_attached():
    def fake_run(args, capture_output, text, timeout):
        return SimpleNamespace(stdout="List of devices attached\n\n", returncode=0)

    assert list_devices(run_fn=fake_run) == []


def test_read_device_specs_from_uiautomator2_device():
    fake_device = SimpleNamespace(
        info={"displayWidth": 1440, "displayHeight": 3120},
        shell=lambda cmd: SimpleNamespace(
            output={
                "wm density": "Physical density: 512\n",
                "getprop ro.build.version.release": "14\n",
                "getprop ro.build.version.sdk": "34\n",
            }[cmd]
        ),
    )

    specs = read_device_specs(fake_device)

    assert specs == DeviceSpecs(resolution="1440x3120", dpi=512, os_version="14", api_level=34)
