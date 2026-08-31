"""Sidebar navigation shell shared by every MAS AI Orchestrator screen."""

from __future__ import annotations

from nicegui import ui

# (route, label, icon) — main nav items, in the order the Figma mockups show.
SCREENS: list[tuple[str, str, str]] = [
    ("/", "Dashboard", "dashboard"),
    ("/test-suites", "Test Suites", "checklist"),
    ("/device-config", "Device Config", "phone_android"),
    ("/reports", "Reports", "bar_chart"),
    ("/settings", "Settings", "settings"),
]

# Footer nav items — matches the Figma mockups' sidebar footer.
FOOTER_SCREENS: list[tuple[str, str, str]] = [
    ("/documentation", "Documentation", "menu_book"),
    ("/system-logs", "System Logs", "receipt_long"),
]


def render_shell(active_route: str) -> ui.column:
    """Render the top bar + sidebar, and return a column to place page content in.

    Usage in a page function:
        with render_shell("/test-suites"):
            ui.label("Test Suites Management")
            ...
    """
    ui.query("body").style("background-color: #f8fafc;")

    with ui.header().classes(
        "bg-white border-b border-slate-200 px-6 py-3 items-center justify-between"
    ):
        ui.label("MAS AI Orchestrator").classes("text-lg font-bold text-slate-800")
        ui.icon("account_circle", size="28px").classes("text-slate-400")

    with ui.left_drawer(fixed=True).classes("bg-white border-r border-slate-200 p-3") as drawer:
        drawer.props("width=280")
        with ui.column().classes("w-full gap-1"):
            for route, label, icon in SCREENS:
                _nav_link(route, label, icon, active=route == active_route)
        ui.space()
        ui.separator().classes("my-3")
        with ui.column().classes("w-full gap-1"):
            for route, label, icon in FOOTER_SCREENS:
                _nav_link(route, label, icon, active=route == active_route)

    content = ui.column().classes("w-full p-6 gap-4")
    return content


def _nav_link(route: str, label: str, icon: str, *, active: bool) -> None:
    classes = "w-full items-center gap-3 px-3 py-2 rounded-lg no-underline"
    classes += " bg-emerald-50 text-emerald-700 font-semibold" if active else " text-slate-600 hover:bg-slate-50"
    with ui.link(target=route).classes(classes):
        with ui.row().classes("items-center gap-3"):
            ui.icon(icon, size="18px")
            ui.label(label).classes("text-sm")
