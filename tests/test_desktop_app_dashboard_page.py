from __future__ import annotations

from desktop_app.pages.dashboard import batch_progress_text


def test_batch_progress_text_with_data():
    from desktop_app.data.manifest import BatchProgress

    progress = BatchProgress(total=69, passed=38, failed=4, stalled=2, technical_error=1, pending=24)

    assert batch_progress_text(progress) == "45 / 69 Scenarios"


def test_batch_progress_text_with_no_run_yet():
    assert batch_progress_text(None) == "0 / 0 Scenarios"
