from __future__ import annotations

import threading
import time

from desktop_app.execution import BatchRunner


def test_batch_runner_runs_target_function_on_background_thread():
    calls = []
    ready = threading.Event()

    def fake_run_predefined(xlsx_path, **kwargs):
        calls.append(xlsx_path)
        ready.set()
        return {"cases": []}

    runner = BatchRunner(run_predefined_fn=fake_run_predefined)
    runner.start("fake.xlsx")

    assert ready.wait(timeout=2.0)
    assert calls == ["fake.xlsx"]


def test_batch_runner_is_running_reflects_thread_state():
    started = threading.Event()
    finish = threading.Event()

    def fake_run_predefined(xlsx_path, **kwargs):
        started.set()
        finish.wait(timeout=2.0)
        return {}

    runner = BatchRunner(run_predefined_fn=fake_run_predefined)
    assert runner.is_running() is False

    runner.start("fake.xlsx")
    started.wait(timeout=2.0)
    assert runner.is_running() is True

    finish.set()
    time.sleep(0.2)
    assert runner.is_running() is False


def test_batch_runner_captures_exception_instead_of_crashing():
    def failing_run_predefined(xlsx_path, **kwargs):
        raise RuntimeError("device disconnected")

    runner = BatchRunner(run_predefined_fn=failing_run_predefined)
    runner.start("fake.xlsx")

    for _ in range(20):
        if runner.last_error() is not None:
            break
        time.sleep(0.1)

    assert isinstance(runner.last_error(), RuntimeError)
    assert runner.is_running() is False


def test_batch_runner_last_result_returns_successful_manifest():
    manifest = {"cases": [{"tcs_id": "TC-1", "status": "passed"}]}

    def fake_run_predefined(xlsx_path, **kwargs):
        return manifest

    runner = BatchRunner(run_predefined_fn=fake_run_predefined)
    assert runner.last_result() is None

    runner.start("fake.xlsx")

    for _ in range(20):
        if runner.last_result() is not None:
            break
        time.sleep(0.1)

    assert runner.last_result() is manifest


def test_batch_runner_last_result_reflects_preflight_failure_returning_none():
    def fake_run_predefined(xlsx_path, **kwargs):
        return None  # preflight failure: e.g. no device connected

    runner = BatchRunner(run_predefined_fn=fake_run_predefined)
    runner.start("fake.xlsx")

    for _ in range(20):
        if not runner.is_running():
            break
        time.sleep(0.1)

    assert runner.last_result() is None
    assert runner.last_error() is None


def test_batch_runner_last_result_reflects_preflight_report_object():
    class FakePreflightReport:
        def __init__(self) -> None:
            self.ok = False

    report = FakePreflightReport()

    def fake_run_predefined(xlsx_path, **kwargs):
        return report

    runner = BatchRunner(run_predefined_fn=fake_run_predefined)
    runner.start("fake.xlsx")

    for _ in range(20):
        if runner.last_result() is not None:
            break
        time.sleep(0.1)

    assert runner.last_result() is report


def test_batch_runner_last_result_resets_to_none_on_new_start():
    def fake_run_predefined(xlsx_path, **kwargs):
        return {"cases": []}

    runner = BatchRunner(run_predefined_fn=fake_run_predefined)
    runner.start("first.xlsx")
    for _ in range(20):
        if runner.last_result() is not None:
            break
        time.sleep(0.1)
    assert runner.last_result() == {"cases": []}

    finish = threading.Event()

    def slow_run_predefined(xlsx_path, **kwargs):
        finish.wait(timeout=2.0)
        return {"cases": ["still running"]}

    runner._run_predefined_fn = slow_run_predefined  # swap target for this run
    runner.start("second.xlsx")
    time.sleep(0.1)

    assert runner.last_result() is None  # cleared for the new in-flight run

    finish.set()


def test_batch_runner_start_is_a_noop_while_already_running():
    calls = []
    finish = threading.Event()

    def fake_run_predefined(xlsx_path, **kwargs):
        calls.append(xlsx_path)
        finish.wait(timeout=2.0)
        return {}

    runner = BatchRunner(run_predefined_fn=fake_run_predefined)
    runner.start("first.xlsx")
    time.sleep(0.1)
    runner.start("second.xlsx")  # ignored: a run is already in progress
    finish.set()
    time.sleep(0.2)

    assert calls == ["first.xlsx"]
