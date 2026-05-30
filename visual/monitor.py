import shutil
import subprocess
import threading
import time
import sys
from typing import Optional

_SCRCPY_FALLBACK_PATHS = [
    r"C:\scrcpy\scrcpy-win64-v4.0\scrcpy.exe",
    r"C:\scrcpy\scrcpy.exe",
]


class VisualMonitor:
    def __init__(self, device_w: int, device_h: int):
        self.device_w = device_w
        self.device_h = device_h
        self._scrcpy_proc: Optional[subprocess.Popen] = None
        self._overlay = None
        self._app = None
        self._running = False
        self._hwnd = None
        self._current_boxes: list = []
        self._current_target: dict = {}
        self._overlay_ready = threading.Event()

    def start(self):
        scrcpy_cmd = shutil.which("scrcpy")
        if scrcpy_cmd is None:
            for path in _SCRCPY_FALLBACK_PATHS:
                if shutil.which(path) is not None or __import__("os").path.isfile(path):
                    scrcpy_cmd = path
                    break
        if scrcpy_cmd is None:
            print("[VisualMonitor] WARNING: scrcpy not found on PATH. Monitor disabled.")
            return

        try:
            self._scrcpy_proc = subprocess.Popen(
                [scrcpy_cmd, "--window-title", "scrcpy"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            print("[VisualMonitor] WARNING: scrcpy not found on PATH. Monitor disabled.")
            return

        import win32gui
        deadline = time.time() + 5
        while time.time() < deadline:
            self._hwnd = win32gui.FindWindow(None, "scrcpy")
            if self._hwnd:
                break
            time.sleep(0.2)

        if not self._hwnd:
            print("[VisualMonitor] WARNING: scrcpy window did not appear. Monitor disabled.")
            self._scrcpy_proc.terminate()
            self._scrcpy_proc = None
            return

        self._qt_thread = threading.Thread(target=self._launch_overlay, daemon=True)
        self._qt_thread.start()
        self._overlay_ready.wait(timeout=3.0)

        self._running = True
        self._tracker_thread = threading.Thread(target=self._track_window, daemon=True)
        self._tracker_thread.start()

    def _client_rect(self, hwnd):
        """Return (x, y, w, h) of the scrcpy *client* area in screen coordinates.

        GetWindowRect includes the title bar and borders; using the client area
        ensures the overlay is sized/positioned to match only the phone content.
        """
        import win32gui
        cl = win32gui.GetClientRect(hwnd)          # (0, 0, w, h) in client coords
        tl = win32gui.ClientToScreen(hwnd, (0, 0)) # top-left in screen coords
        return tl[0], tl[1], cl[2], cl[3]         # x, y, w, h

    def _launch_overlay(self):
        from PyQt5.QtWidgets import QApplication
        from visual.overlay_window import OverlayWindow

        self._app = QApplication.instance() or QApplication(sys.argv)
        x, y, w, h = self._client_rect(self._hwnd)
        self._overlay = OverlayWindow(self.device_w, self.device_h)
        self._overlay_ready.set()
        self._overlay.setGeometry(x, y, w, h)
        self._overlay.show()
        self._app.exec_()

    def _track_window(self):
        while self._running:
            if self._overlay and self._hwnd:
                try:
                    x, y, w, h = self._client_rect(self._hwnd)
                    self._overlay.sync_geometry_signal.emit(x, y, w, h)
                except Exception:
                    pass
            time.sleep(0.1)

    def on_observer(self, widgets: list):
        if self._overlay is None:
            return
        self._current_boxes = [w["bounds"] for w in widgets if w.get("bounds") and len(w["bounds"]) == 4]
        self._current_target = {}
        self._overlay.update_signal.emit(self._current_boxes, {}, {})

    def on_decider(self, target_widget: dict):
        if self._overlay is None or not target_widget:
            return
        self._current_target = target_widget
        self._overlay.update_signal.emit(self._current_boxes, target_widget, {})

    def on_executor(self, x: int, y: int):
        if self._overlay is None:
            return
        ripple = {"x": x, "y": y, "alpha": 255}
        self._overlay.update_signal.emit(self._current_boxes, self._current_target, ripple)

    def on_clear(self):
        """Clear all annotations (call after action completes so stale boxes don't linger)."""
        if self._overlay is None:
            return
        self._current_boxes = []
        self._current_target = {}
        self._overlay.update_signal.emit([], {}, {})

    def stop(self):
        self._running = False
        if self._app is not None:
            try:
                self._app.quit()
            except Exception:
                pass
        if self._scrcpy_proc is not None:
            try:
                self._scrcpy_proc.terminate()
            except Exception:
                pass
