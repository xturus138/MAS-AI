import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _map_coords(phone_x, phone_y, device_w, device_h, win_w, win_h):
    """Pure coordinate mapping logic (extracted for testability)."""
    return (
        int(phone_x / device_w * win_w),
        int(phone_y / device_h * win_h),
    )


def test_map_coords_center():
    ox, oy = _map_coords(540, 1200, 1080, 2400, 540, 1200)
    assert ox == 270
    assert oy == 600


def test_map_coords_origin():
    ox, oy = _map_coords(0, 0, 1080, 2400, 540, 1200)
    assert ox == 0
    assert oy == 0


def test_map_coords_full():
    ox, oy = _map_coords(1080, 2400, 1080, 2400, 540, 1200)
    assert ox == 540
    assert oy == 1200


def test_map_coords_non_square():
    ox, oy = _map_coords(100, 200, 1000, 2000, 500, 800)
    assert ox == 50
    assert oy == 80


def test_monitor_no_crash_when_overlay_none():
    """All public methods must be safe to call when overlay is None (monitor disabled)."""
    from visual.monitor import VisualMonitor
    m = VisualMonitor(device_w=1080, device_h=2400)
    m.on_observer([{"bounds": [0, 0, 100, 100]}])
    m.on_decider({"bounds": [10, 10, 80, 80]})
    m.on_executor(540, 1200)
    m.stop()


def test_monitor_start_scrcpy_not_found():
    """If scrcpy is not on PATH, start() prints a warning and leaves _overlay as None."""
    from visual.monitor import VisualMonitor
    m = VisualMonitor(device_w=1080, device_h=2400)
    with patch("subprocess.Popen", side_effect=FileNotFoundError):
        m.start()
    assert m._overlay is None


def test_filter_overlay_boxes_drops_large_xml_structural_containers():
    """Large non-actionable XML wrappers must not flood the monitor overlay."""
    from visual.monitor import VisualMonitor

    m = VisualMonitor(device_w=720, device_h=1600)
    widgets = [
        {
            "bounds": [0, 0, 720, 1600],
            "source": "xml",
            "actionable": False,
            "role": "view",
            "class": "android.widget.FrameLayout",
            "label": "action_bar_overlay_layout",
        },
        {
            "bounds": [0, 97, 720, 1600],
            "source": "xml",
            "actionable": False,
            "role": "view",
            "class": "android.widget.FrameLayout",
            "label": "nested_header_layout",
        },
        {
            "bounds": [70, 421, 650, 499],
            "source": "xml",
            "actionable": False,
            "role": "text",
            "class": "android.widget.TextView",
            "label": "Rencana Skripsi 2026",
        },
        {
            "bounds": [548, 1310, 655, 1417],
            "source": "xml",
            "actionable": True,
            "role": "icon_button",
            "class": "android.widget.ImageView",
            "label": "Ketuk untuk buat catatan",
        },
    ]

    assert m._filter_overlay_boxes(widgets) == [
        [70, 421, 650, 499],
        [548, 1310, 655, 1417],
    ]


def test_filter_overlay_boxes_keeps_actionable_large_xml_targets():
    """Do not hide real large actionable targets from monitor display."""
    from visual.monitor import VisualMonitor

    m = VisualMonitor(device_w=720, device_h=1600)
    widgets = [
        {
            "bounds": [0, 0, 720, 269],
            "source": "xml",
            "actionable": True,
            "role": "button",
            "class": "android.widget.FrameLayout",
            "label": "action_bar_container",
        }
    ]

    assert m._filter_overlay_boxes(widgets) == [[0, 0, 720, 269]]
