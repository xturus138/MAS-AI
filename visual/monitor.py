import subprocess
import threading
import time
import sys
from typing import Optional


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
        try:
            self._scrcpy_proc = subprocess.Popen(
                ["scrcpy", "--window-title", "scrcpy", "--always-on-top"],
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

    def _launch_overlay(self):
        from PyQt5.QtWidgets import QApplication
        from visual.overlay_window import OverlayWindow
        import win32gui

        self._app = QApplication.instance() or QApplication(sys.argv)
        rect = win32gui.GetWindowRect(self._hwnd)
        x, y, x2, y2 = rect
        self._overlay = OverlayWindow(self.device_w, self.device_h)
        self._overlay_ready.set()
        self._overlay.setGeometry(x, y, x2 - x, y2 - y)
        self._overlay.show()
        self._app.exec_()

    def _track_window(self):
        import win32gui
        while self._running:
            if self._overlay and self._hwnd:
                try:
                    rect = win32gui.GetWindowRect(self._hwnd)
                    x, y, x2, y2 = rect
                    self._overlay.sync_geometry_signal.emit(x, y, x2 - x, y2 - y)
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
