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

    def _should_overlay_widget(self, widget: dict) -> bool:
        """Return True if widget should be drawn on debug overlay.

        XML-first path can emit large structural containers with resource-id-derived
        labels. Those are useful in workflow state, but painting them causes the
        whole scrcpy window to wash blue. Filter here only for monitor display.
        """
        bounds = widget.get("bounds")
        if not bounds or len(bounds) != 4:
            return False

        x1, y1, x2, y2 = bounds
        width = max(0, x2 - x1)
        height = max(0, y2 - y1)
        if width <= 0 or height <= 0:
            return False

        source = widget.get("source", "")
        actionable = widget.get("actionable", False)
        role = widget.get("role", "")
        class_name = widget.get("class", "")

        if source == "xml":
            screen_area = max(1, self.device_w * self.device_h)
            area_ratio = (width * height) / screen_area
            width_ratio = width / max(1, self.device_w)
            height_ratio = height / max(1, self.device_h)
            structural_class = any(token in class_name for token in ("FrameLayout", "LinearLayout", "ViewGroup"))

            if not actionable and role == "view" and structural_class and area_ratio >= 0.05:
                return False
            if not actionable and width_ratio >= 0.85 and height_ratio >= 0.20:
                return False
            if not actionable and area_ratio >= 0.12:
                return False

        return True

    def _filter_overlay_boxes(self, widgets: list) -> list:
        return [w["bounds"] for w in widgets if self._should_overlay_widget(w)]

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
        cl = win32gui.GetClientRect(hwnd)
        tl = win32gui.ClientToScreen(hwnd, (0, 0))
        return tl[0], tl[1], cl[2], cl[3]

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
        self._current_boxes = self._filter_overlay_boxes(widgets)
        self._current_target = {}
        self._overlay.update_signal.emit(self._current_boxes, {}, {})

    def on_decider(self, target_widget: dict):
        if self._overlay is None or not target_widget:
            return
        self._current_target = target_widget
        self._overlay.update_signal.emit(self._current_boxes, target_widget, {})

    def on_executor(self, x: int, y: int, action_type: str = "click", scroll_direction: str = ""):
        if self._overlay is None:
            return
        ripple = {"x": x, "y": y, "alpha": 255, "action_type": action_type, "scroll_direction": scroll_direction}
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
