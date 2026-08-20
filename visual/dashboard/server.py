"""
server.py
---------
Lightweight asyncio WebSocket server that pushes MAS AI live events
(observer widgets, decider target, executor tap, progress) to the
browser dashboard page.

Port: DASHBOARD_WS_PORT (default 9765)
The browser connects to ws://localhost:9765.
"""

from __future__ import annotations
import asyncio
import json
import threading
import time
from typing import Any

# Optional: websockets library. Installed lazily so missing dep doesn't crash import.
_WS_AVAILABLE = False
try:
    import websockets  # type: ignore
    _WS_AVAILABLE = True
except ImportError:
    pass

DEFAULT_WS_PORT = 9765


class DashboardServer:
    """Thread-safe event bus: Python agents call push_*() from any thread;
    this server fans out to all connected browser clients via WebSocket."""

    def __init__(self, port: int = DEFAULT_WS_PORT):
        self.port = port
        self._clients: set = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server = None
        self._ready = threading.Event()

    # ------------------------------------------------------------------
    # Public push API (called from agent threads)
    # ------------------------------------------------------------------

    def push_observer(self, widgets: list[dict]):
        self._push({"type": "observer", "widgets": widgets})

    def push_decider(self, target: dict):
        self._push({"type": "decider", "target": target})

    def push_executor(self, x: int, y: int, action_type: str = "click",
                      scroll_direction: str = ""):
        self._push({"type": "executor", "x": x, "y": y,
                    "action": action_type, "scroll": scroll_direction})

    def push_clear(self):
        self._push({"type": "clear"})

    def push_progress(self, scenario_idx: int, scenario_total: int,
                      step_idx: int, step_total: int,
                      tcs_id: str = "", status: str = ""):
        self._push({
            "type": "progress",
            "scenario_idx": scenario_idx,
            "scenario_total": scenario_total,
            "step_idx": step_idx,
            "step_total": step_total,
            "tcs_id": tcs_id,
            "status": status,
            "ts": time.strftime("%H:%M:%S"),
        })

    def push_log(self, component: str, message: str, detail: str = ""):
        self._push({
            "type": "log",
            "component": component,
            "message": message,
            "detail": detail,
            "ts": time.strftime("%H:%M:%S"),
        })

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> bool:
        if not _WS_AVAILABLE:
            print("[Dashboard] 'websockets' package not found. "
                  "Run: pip install websockets\n"
                  "         Dashboard disabled for this session.")
            return False
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)
        return True

    def stop(self):
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _push(self, payload: dict):
        if not self._loop or not self._clients:
            return
        msg = json.dumps(payload)
        asyncio.run_coroutine_threadsafe(self._broadcast(msg), self._loop)

    async def _broadcast(self, msg: str):
        dead = set()
        for ws in list(self._clients):
            try:
                await ws.send(msg)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    async def _handler(self, websocket):
        self._clients.add(websocket)
        try:
            await websocket.wait_closed()
        finally:
            self._clients.discard(websocket)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def _serve():
            async with websockets.serve(self._handler, "", self.port):
                self._ready.set()
                await asyncio.get_event_loop().create_future()  # run forever

        self._loop.run_until_complete(_serve())
