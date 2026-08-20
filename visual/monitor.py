"""
visual/monitor.py  —  BrowserDashboard
---------------------------------------
Drop-in replacement for the old PyQt5/win32gui VisualMonitor.

Public API is identical so no agent code needs to change:
  monitor.start()
  monitor.on_observer(widgets)
  monitor.on_decider(target_widget)
  monitor.on_executor(x, y, action_type, scroll_direction)
  monitor.on_clear()
  monitor.stop()

New: also exposes push_progress() and push_log() for runner integration.

Requires:
  pip install websockets
  node >= 18  (for ws-scrcpy-web)
  LIVE_DASHBOARD_ENABLED=true  (default)
"""

from __future__ import annotations
import os
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

_DASHBOARD_DIR = Path(__file__).parent / "dashboard"
_INDEX_HTML    = _DASHBOARD_DIR / "index.html"

# env-controlled ports
_WS_PORT     = int(os.getenv("DASHBOARD_WS_PORT",    "9765"))
_SCRCPY_PORT = int(os.getenv("DASHBOARD_SCRCPY_PORT", "8000"))
_ENABLED     = os.getenv("LIVE_DASHBOARD_ENABLED", "true").lower() == "true"


class BrowserDashboard:
    """Live browser dashboard: ws-scrcpy video + WebSocket event feed."""

    def __init__(self, device_id: str = "", device_w: int = 1080, device_h: int = 2400):
        self.device_id = device_id or os.getenv("TARGET_DEVICE", "")
        self.device_w  = device_w
        self.device_h  = device_h
        self._enabled  = _ENABLED
        self._server   = None          # DashboardServer
        self._launcher = None          # WsScrcpyLauncher
        self._http_proc: subprocess.Popen | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        if not self._enabled:
            print("[Dashboard] LIVE_DASHBOARD_ENABLED=false — skipped.")
            return False

        ok = True

        # 1. Start WebSocket push server
        try:
            from visual.dashboard.server import DashboardServer
            self._server = DashboardServer(port=_WS_PORT)
            if not self._server.start():
                print("[Dashboard] WS server failed to start.")
                ok = False
        except Exception as exc:
            print(f"[Dashboard] WS server error: {exc}")
            ok = False

        # 2. Serve index.html via a tiny Python HTTP server
        threading.Thread(target=self._serve_html, daemon=True).start()
        time.sleep(0.5)  # let HTTP server bind

        # 3. Spawn ws-scrcpy-web (auto-clone on first run)
        try:
            from visual.dashboard.ws_scrcpy_launcher import WsScrcpyLauncher
            self._launcher = WsScrcpyLauncher(device_id=self.device_id, port=_SCRCPY_PORT)
            ws_ok = self._launcher.start()
            if not ws_ok:
                print("[Dashboard] ws-scrcpy-web failed to start — "
                      "live device screen will be unavailable.")
        except Exception as exc:
            print(f"[Dashboard] ws-scrcpy-web error: {exc}")

        # 4. Open browser — dashboard index.html served on _SCRCPY_PORT+1
        dashboard_url = f"http://localhost:{_SCRCPY_PORT + 1}"
        try:
            webbrowser.open(dashboard_url)
            print(f"[Dashboard] Opened: {dashboard_url}")
        except Exception:
            print(f"[Dashboard] Open manually: {dashboard_url}")

        return ok

    def stop(self):
        if self._launcher:
            self._launcher.stop()
        if self._server:
            self._server.stop()
        if self._http_proc:
            try:
                self._http_proc.terminate()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Agent hooks  (same API as old VisualMonitor)
    # ------------------------------------------------------------------

    def on_observer(self, widgets: list):
        if self._server:
            self._server.push_observer(widgets)

    def on_decider(self, target_widget: dict):
        if self._server and target_widget:
            self._server.push_decider(target_widget)

    def on_executor(self, x: int, y: int, action_type: str = "click",
                    scroll_direction: str = ""):
        if self._server:
            self._server.push_executor(x, y, action_type, scroll_direction)

    def on_clear(self):
        if self._server:
            self._server.push_clear()

    # ------------------------------------------------------------------
    # Runner hooks  (new)
    # ------------------------------------------------------------------

    def push_progress(self, scenario_idx: int, scenario_total: int,
                      step_idx: int = 0, step_total: int = 0,
                      tcs_id: str = "", status: str = ""):
        if self._server:
            self._server.push_progress(
                scenario_idx, scenario_total, step_idx, step_total, tcs_id, status
            )

    def push_log(self, component: str, message: str, detail: str = ""):
        if self._server:
            self._server.push_log(component, message, detail)

    # ------------------------------------------------------------------
    # Tiny HTTP server for index.html
    # ------------------------------------------------------------------

    def _serve_html(self):
        """Serve visual/dashboard/ as a static site on _SCRCPY_PORT+1."""
        import http.server
        import socketserver

        port = _SCRCPY_PORT + 1
        handler = _make_handler(str(_DASHBOARD_DIR))
        with socketserver.TCPServer(("", port), handler) as httpd:
            httpd.serve_forever()

    # ------------------------------------------------------------------
    # Backwards-compat shim: old VisualMonitor constructor took (w, h)
    # ------------------------------------------------------------------

    @classmethod
    def from_dimensions(cls, device_w: int, device_h: int) -> "BrowserDashboard":
        return cls(device_w=device_w, device_h=device_h)


# ── Alias so old import `from visual.monitor import VisualMonitor` works ──
VisualMonitor = BrowserDashboard


def _make_handler(directory: str):
    """Return a SimpleHTTPRequestHandler subclass rooted at `directory`."""
    import http.server

    class _H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, fmt, *args):  # silence HTTP log spam
            pass

    return _H
