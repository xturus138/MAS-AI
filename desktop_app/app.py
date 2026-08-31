"""Native-window entry point for the MAS AI Orchestrator desktop app."""

from __future__ import annotations

from nicegui import ui

from desktop_app.shell import FOOTER_SCREENS, SCREENS


def _register_stub_pages() -> None:
    """Register a placeholder body for every screen.

    Each of Tasks 9-16 replaces one of these page functions with real
    content; registration order and route strings must not change, since
    desktop_app/shell.py's SCREENS/FOOTER_SCREENS lists are the single
    source of truth other tasks route against.
    """
    for route, label, _icon in [*SCREENS, *FOOTER_SCREENS]:
        _register_one_stub(route, label)


def _register_one_stub(route: str, label: str) -> None:
    from desktop_app.shell import render_shell

    @ui.page(route)
    def _page(route=route, label=label) -> None:
        with render_shell(route):
            ui.label(f"{label} (stub)").classes("text-2xl font-bold text-slate-800")


def create_app() -> None:
    """Configure pages and launch the native NiceGUI window."""
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
