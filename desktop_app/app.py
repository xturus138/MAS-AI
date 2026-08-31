"""Native-window entry point for the MAS AI Orchestrator desktop app."""

from __future__ import annotations

from nicegui import ui

from desktop_app.shell import FOOTER_SCREENS, SCREENS

_REAL_ROUTES = {
    "/",
    "/test-suites",
    "/reports",
    "/system-logs",
    "/settings",
    "/documentation",
    "/device-config",
}


def _register_stub_pages() -> None:
    """Register a placeholder body for every screen.

    Each of Tasks 9-16 replaces one of these page functions with real
    content; registration order and route strings must not change, since
    desktop_app/shell.py's SCREENS/FOOTER_SCREENS lists are the single
    source of truth other tasks route against.
    """
    for route, label, _icon in [*SCREENS, *FOOTER_SCREENS]:
        if route in _REAL_ROUTES:
            continue
        _register_one_stub(route, label)


def _register_one_stub(route: str, label: str) -> None:
    from desktop_app.shell import render_shell

    @ui.page(route)
    def _page(route=route, label=label) -> None:
        with render_shell(route):
            ui.label(f"{label} (stub)").classes("text-2xl font-bold text-slate-800")


def _register_real_pages() -> None:
    from desktop_app.data.manifest import find_latest_run_root
    from desktop_app.pages.dashboard import render_dashboard_page
    from desktop_app.pages.device_config import render_device_config_page
    from desktop_app.pages.documentation import render_documentation_page
    from desktop_app.pages.reports import render_reports_page
    from desktop_app.pages.settings import render_settings_page
    from desktop_app.pages.system_logs import render_system_logs_page
    from desktop_app.pages.test_suites import render_test_suites_page
    from desktop_app.state import APP_STATE

    @ui.page("/")
    def _dashboard_page() -> None:
        render_dashboard_page()

    @ui.page("/device-config")
    def _device_config_page() -> None:
        render_device_config_page()

    @ui.page("/test-suites")
    def _test_suites_page() -> None:
        render_test_suites_page(xlsx_path=APP_STATE.xlsx_path)

    @ui.page("/reports")
    def _reports_page() -> None:
        render_reports_page(run_root=find_latest_run_root("predefined"))

    @ui.page("/system-logs")
    def _system_logs_page() -> None:
        render_system_logs_page(run_root=find_latest_run_root("predefined"))

    @ui.page("/settings")
    def _settings_page() -> None:
        render_settings_page()

    @ui.page("/documentation")
    def _documentation_page() -> None:
        render_documentation_page()


def create_app() -> None:
    """Configure pages and launch the native NiceGUI window."""
    _register_real_pages()
    _register_stub_pages()
    ui.run(
        title="MAS AI Orchestrator",
        native=True,
        window_size=(1440, 900),
        reload=False,
        show=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    create_app()
