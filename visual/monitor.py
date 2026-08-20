"""
visual/monitor.py  —  BrowserDashboard
---------------------------------------
Drop-in replacement untuk VisualMonitor lama.

Public API:
  monitor.start()
  monitor.on_observer(widgets)
  monitor.on_decider(target_widget)
  monitor.on_executor(x, y, action_type, scroll_direction)
  monitor.on_clear()
  monitor.push_progress(scenario_idx, scenario_total, step_idx, step_total, tcs_id, status)
  monitor.push_log(component, message, detail)
  monitor.stop()

Requires: pip install websockets
Env vars: LIVE_DASHBOARD_ENABLED (default true), DASHBOARD_WS_PORT (default 9765),
          DASHBOARD_SCRCPY_PORT (default 8000)
"""

from __future__ import annotations
import os
import socket
import threading
import time
import webbrowser
from pathlib import Path

_DASHBOARD_DIR = Path(__file__).parent / "dashboard"
_ENABLED       = os.getenv("LIVE_DASHBOARD_ENABLED", "true").lower() == "true"
_WS_PORT       = int(os.getenv("DASHBOARD_WS_PORT",    "9765"))
_SCRCPY_PORT   = int(os.getenv("DASHBOARD_SCRCPY_PORT", "8000"))


def _free_port(preferred: int) -> int:
    """Return preferred port if free, else let OS pick one."""
    with socket.socket() as s:
        try:
            s.bind(("", preferred))
            return preferred
        except OSError:
            s.bind(("", 0))
            return s.getsockname()[1]


class BrowserDashboard:
    """Live browser dashboard: device screen + progress + QA updates."""

    def __init__(self, device_id: str = "", device_w: int = 1080, device_h: int = 2400):
        self.device_id = device_id or os.getenv("TARGET_DEVICE", "")
        self.device_w  = device_w
        self.device_h  = device_h
        self._enabled  = _ENABLED
        self._server   = None
        self._launcher = None
        self._ws_port  = _WS_PORT
        self._http_port = _SCRCPY_PORT + 1
        self._scrcpy_port = _SCRCPY_PORT

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        if not self._enabled:
            print("[Dashboard] LIVE_DASHBOARD_ENABLED=false — skipped.")
            return False

        # Pick free ports (avoids EADDRINUSE on re-run)
        self._ws_port     = _free_port(_WS_PORT)
        self._scrcpy_port = _free_port(_SCRCPY_PORT)
        self._http_port   = _free_port(_SCRCPY_PORT + 1)

        # 1. WebSocket push server
        try:
            from visual.dashboard.server import DashboardServer
            self._server = DashboardServer(port=self._ws_port)
            if not self._server.start():
                print("[Dashboard] WS server failed — install: pip install websockets")
                return False
        except Exception as exc:
            print(f"[Dashboard] WS server error: {exc}")
            return False

        # 2. Serve index.html
        threading.Thread(target=self._serve_html, daemon=True).start()
        time.sleep(0.3)

        # 3. Spawn scrcpy relay (optional — if fails, video panel empty)
        try:
            from visual.dashboard.ws_scrcpy_launcher import WsScrcpyLauncher
            self._launcher = WsScrcpyLauncher(
                device_id=self.device_id, port=self._scrcpy_port
            )
            self._launcher.start()
        except Exception as exc:
            print(f"[Dashboard] scrcpy relay skipped: {exc}")

        # 4. Inject actual ports into served HTML via JS config endpoint
        # (ports are written into a tiny config.js served alongside index.html)
        self._write_port_config()

        # 5. Open browser
        url = f"http://localhost:{self._http_port}"
        try:
            webbrowser.open(url)
        except Exception:
            print(f"[Dashboard] Open manually: {url}")

        return True

    def stop(self):
        if self._launcher:
            self._launcher.stop()
        if self._server:
            self._server.stop()

    # ------------------------------------------------------------------
    # Agent hooks
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
    # Internal
    # ------------------------------------------------------------------

    def _write_port_config(self):
        """Write config.js so index.html knows which ports to connect to."""
        cfg = _DASHBOARD_DIR / "config.js"
        cfg.write_text(
            f"window.DASHBOARD_WS_PORT={self._ws_port};\n"
            f"window.DASHBOARD_SCRCPY_PORT={self._scrcpy_port};\n",
            encoding="utf-8",
        )

    def _serve_html(self):
        import http.server, socketserver

        handler = _make_handler(str(_DASHBOARD_DIR))
        # Retry bind up to 3 times in case port just freed
        for _ in range(3):
            try:
                with socketserver.TCPServer(("", self._http_port), handler) as httpd:
                    httpd.serve_forever()
                return
            except OSError:
                self._http_port = _free_port(0)
                time.sleep(0.2)

    @classmethod
    def from_dimensions(cls, device_w: int, device_h: int) -> "BrowserDashboard":
        return cls(device_w=device_w, device_h=device_h)


# Alias — old import path still works
VisualMonitor = BrowserDashboard


def _make_handler(directory: str):
    import http.server

    class _H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, *_):
            pass  # silence HTTP log spam

    return _H
