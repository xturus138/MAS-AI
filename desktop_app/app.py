"""Native-window entry point for the MAS AI Orchestrator desktop app."""

from __future__ import annotations

from nicegui import ui


def create_app() -> None:
    """Configure pages and launch the native NiceGUI window.

    Page registration happens via side-effecting imports in later tasks
    (each page module calls @ui.page(...) at import time). This function
    only owns the final ui.run(...) call so there is exactly one place
    that starts the native window.
    """
    ui.run(
        title="MAS AI Orchestrator",
        native=True,
        window_size=(1440, 900),
        reload=False,
        show=False,
    )


if __name__ in {"__main__", "__mp_main__"}:
    create_app()
