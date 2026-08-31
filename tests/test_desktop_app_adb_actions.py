from __future__ import annotations

from types import SimpleNamespace

from desktop_app.data.adb_actions import (
    ReadinessChecklist,
    check_readiness,
    clear_app_data,
    install_apk,
    is_package_installed,
    wake_screen,
)


def _fake_device(shell_responses: dict[str, str]):
    return SimpleNamespace(
        shell=lambda cmd: SimpleNamespace(output=shell_responses.get(cmd, ""))
    )


def test_install_apk_returns_true_on_success(monkeypatch):
    def fake_run(args, capture_output, text, timeout):
        assert "install" in args
        return SimpleNamespace(stdout="Success\n", returncode=0)

    assert install_apk("SERIAL123", "app.apk", run_fn=fake_run) is True


def test_install_apk_returns_false_on_failure():
    def fake_run(args, capture_output, text, timeout):
        return SimpleNamespace(stdout="Failure [INSTALL_FAILED_INVALID_APK]\n", returncode=1)

    assert install_apk("SERIAL123", "bad.apk", run_fn=fake_run) is False


def test_is_package_installed_true_when_listed():
    device = _fake_device({"pm list packages com.example.app": "package:com.example.app\n"})
    assert is_package_installed(device, "com.example.app") is True


def test_is_package_installed_false_when_not_listed():
    device = _fake_device({"pm list packages com.example.app": ""})
    assert is_package_installed(device, "com.example.app") is False


def test_clear_app_data_true_on_success():
    device = _fake_device({"pm clear com.example.app": "Success\n"})
    assert clear_app_data(device, "com.example.app") is True


def test_wake_screen_sends_wakeup_keyevent():
    calls = []
    device = SimpleNamespace(shell=lambda cmd: calls.append(cmd))

    wake_screen(device)

    assert calls == ["input keyevent KEYCODE_WAKEUP"]


def test_check_readiness_reports_awake_and_keyboard_dismissed():
    device = _fake_device({
        "dumpsys power": "mWakefulness=Awake\n",
        "dumpsys input_method": "mInputShown=false\n",
    })

    result = check_readiness(device)

    assert result == ReadinessChecklist(
        adb_connected=True, screen_awake=True, keyboard_dismissed=True, service_ready=True
    )


def test_check_readiness_reports_asleep_and_keyboard_shown():
    device = _fake_device({
        "dumpsys power": "mWakefulness=Asleep\n",
        "dumpsys input_method": "mInputShown=true\n",
    })

    result = check_readiness(device)

    assert result.screen_awake is False
    assert result.keyboard_dismissed is False


def test_check_readiness_reports_disconnected_when_device_is_none():
    result = check_readiness(None)
    assert result == ReadinessChecklist(
        adb_connected=False, screen_awake=False, keyboard_dismissed=False, service_ready=False
    )
