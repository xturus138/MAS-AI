from __future__ import annotations

from desktop_app.pages.reports import format_duration


def test_format_duration_under_a_minute():
    assert format_duration(45.0) == "45s"


def test_format_duration_minutes_and_seconds():
    assert format_duration(1122.0) == "18m 42s"


def test_format_duration_zero():
    assert format_duration(0.0) == "0s"
