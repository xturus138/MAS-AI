"""
ws_scrcpy_launcher.py
---------------------
Spawns the MAS AI custom scrcpy relay (visual/dashboard/scrcpy_relay/server.js).

On first run: auto-installs the single Node dependency (ws) via npm install.
After that: cached in scrcpy_relay/node_modules/, no network needed.

Lifecycle:
  launcher = WsScrcpyLauncher(device_id, port=8000)
  launcher.start()   → npm install if needed, then spawn Node relay
  launcher.stop()    → terminate node process
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

RELAY_DIR = Path(__file__).parent / "scrcpy_relay"


class WsScrcpyLauncher:
    def __init__(self, device_id: str, port: int = 8000):
        self.device_id = device_id
        self.port = port
        self._proc: subprocess.Popen | None = None
        self._ready = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """Install deps if needed, then spawn Node relay. Returns True on success."""
        try:
            self._ensure_npm_install()
        except Exception as exc:
            print(f"[WsScrcpy] npm install failed: {exc}", file=sys.stderr)
            return False

        node = shutil.which("node")
        if node is None:
            print("[WsScrcpy] node not found on PATH.", file=sys.stderr)
            return False

        env = {**os.environ, "PORT": str(self.port), "DEVICE": self.device_id}
        self._proc = subprocess.Popen(
            [node, str(RELAY_DIR / "server.js")],
            cwd=str(RELAY_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        threading.Thread(target=self._tail_log, daemon=True).start()
        self._ready.wait(timeout=10)
        return self._proc.poll() is None

    def stop(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_npm_install(self):
        marker = RELAY_DIR / "node_modules" / "ws"
        if marker.exists():
            return  # already installed
        npm = shutil.which("npm")
        if npm is None:
            raise EnvironmentError("npm not found on PATH")
        print("[WsScrcpy] Running npm install (first-time setup) …")
        subprocess.run([npm, "install"], cwd=str(RELAY_DIR), check=True)
        print("[WsScrcpy] npm install done.")

    def _tail_log(self):
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            line = line.rstrip()
            print(f"[scrcpy-relay] {line}")
            if "Listening" in line or str(self.port) in line:
                self._ready.set()
        self._ready.set()  # unblock start() on early exit
