import pytest


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
