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
