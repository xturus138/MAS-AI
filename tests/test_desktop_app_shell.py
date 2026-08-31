from __future__ import annotations

from desktop_app.shell import FOOTER_SCREENS, SCREENS


def test_screens_are_ordered_and_complete():
    routes = [route for route, _label, _icon in [*SCREENS, *FOOTER_SCREENS]]
    assert routes == [
        "/",
        "/test-suites",
        "/device-config",
        "/reports",
        "/settings",
        "/documentation",
        "/system-logs",
    ]


def test_every_screen_has_a_non_empty_label_and_icon():
    for route, label, icon in [*SCREENS, *FOOTER_SCREENS]:
        assert label.strip(), f"{route} has an empty label"
        assert icon.strip(), f"{route} has an empty icon"
