from __future__ import annotations

from desktop_app.state import APP_STATE, AppState


def test_app_state_starts_with_no_workbook_loaded():
    state = AppState()
    assert state.xlsx_path is None


def test_set_xlsx_path_updates_state():
    state = AppState()
    state.set_xlsx_path("/some/path/scenario.xlsx")
    assert state.xlsx_path == "/some/path/scenario.xlsx"


def test_app_state_singleton_is_shared():
    APP_STATE.set_xlsx_path("/shared/scenario.xlsx")
    from desktop_app.state import APP_STATE as reimported

    assert reimported.xlsx_path == "/shared/scenario.xlsx"
