"""
visual/monitor.py  -  TkDashboard
----------------------------------
Native tkinter floating window. No browser, no Node, no extra ports.

Layout:
  LEFT  : device screenshot (full-height, aspect-ratio preserved, HD quality)
  RIGHT : narrow panel
    [1] header  - "Pengujian sedang berjalan..." + ETA
    [2] progress - % besar + "N/69 skenario selesai" kecil
    [3] agent feed - humanized activity per agent (+ overlay box on screenshot)

Public API:
  monitor = VisualMonitor(device_id, device_w, device_h)
  monitor.start()
  monitor.push_progress(scenario_idx, scenario_total, step_idx, step_total, tcs_id, status)
  monitor.push_log(component, message, detail)
  monitor.on_observer(widgets)        <- overlay boxes kiri
  monitor.on_decider(target_widget)   <- highlight box target
  monitor.on_executor(x, y, ...)      <- tap indicator
  monitor.on_clear()
  monitor.stop()

Env: LIVE_DASHBOARD_ENABLED (default true)
Deps: tkinter (stdlib), Pillow (pip install Pillow), adb in PATH
"""

from __future__ import annotations
import os
import queue
import subprocess
import threading
import time
from io import BytesIO
from typing import Any

_ENABLED = os.getenv("LIVE_DASHBOARD_ENABLED", "true").lower() == "true"

# ── Dimensions ────────────────────────────────────────────────────────────────
_RIGHT_W       = 280          # right panel fixed width
_WIN_H         = 700          # window height
_SHOT_INTERVAL = 1.2          # screencap refresh (seconds)
_FEED_MAX      = 200          # max agent activity lines kept in memory (scrollable)

# ── Humanizer ────────────────────────────────────────────────────────────────
_HUMANIZE: dict[str, list[str]] = {
    "OBSERVER": [
        "Scanning the device screen...",
        "Detecting visible UI elements...",
        "Analyzing screen widgets and components...",
    ],
    "DECIDER": [
        "Deciding the next best action...",
        "Analyzing the situation and planning...",
        "Identifying the target element on screen...",
    ],
    "EXECUTOR": [
        "Performing action on device...",
        "Tapping button / entering text...",
        "Interacting with the device...",
    ],
    "REFLECTOR": [
        "Checking the result of the action...",
        "Verifying whether the step succeeded...",
        "Evaluating the current screen state...",
    ],
    "ORCHESTRATOR": [
        "Moving to the next step...",
        "Coordinating the test sequence...",
        "Preparing the next step...",
    ],
    "RECORDER": [
        "Saving test results...",
        "Recording evidence and artifacts...",
    ],
    "RUNNER": [
        "Starting a new test scenario...",
        "Setting up the test environment...",
    ],
}

_AGENT_ICON: dict[str, str] = {
    "OBSERVER":     "Observer",
    "DECIDER":      "Decider",
    "EXECUTOR":     "Executor",
    "REFLECTOR":    "Reflector",
    "ORCHESTRATOR": "Orchestrator",
    "RECORDER":     "Recorder",
    "RUNNER":       "Runner",
}

_AGENT_COLOR: dict[str, str] = {
    "OBSERVER":     "#6366f1",   # indigo
    "DECIDER":      "#f59e0b",   # amber
    "EXECUTOR":     "#10b981",   # emerald
    "REFLECTOR":    "#3b82f6",   # blue
    "ORCHESTRATOR": "#8b5cf6",   # violet
    "RECORDER":     "#64748b",   # slate
    "RUNNER":       "#6b7280",   # gray
}

_rng_state = [0]

def _humanize(component: str, message: str) -> tuple[str, str]:
    """Return (icon_label, human_sentence) for a component."""
    key = component.upper()
    options = _HUMANIZE.get(key)
    if options:
        _rng_state[0] += 1
        text = options[_rng_state[0] % len(options)]
    else:
        text = message[:80] if message else "Sedang bekerja..."
    label = _AGENT_ICON.get(key, key.title())
    return label, text


class TkDashboard:
    """Compact floating window: HD device screen left, QA info right."""

    def __init__(self, device_id: str = "", device_w: int = 1080, device_h: int = 2400):
        self.device_id = device_id or os.getenv("TARGET_DEVICE", "")
        self.device_w  = device_w
        self.device_h  = device_h
        self._enabled  = _ENABLED
        self._q: queue.Queue = queue.Queue(maxsize=200)
        self._tk_thread: threading.Thread | None = None
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> bool:
        if not self._enabled:
            return False
        self._running = True
        self._tk_thread = threading.Thread(target=self._run_tk, daemon=True)
        self._tk_thread.start()
        return True

    def stop(self):
        self._running = False
        try:
            self._q.put_nowait({"type": "_quit"})
        except queue.Full:
            pass

    # ── Agent hooks ────────────────────────────────────────────────────────────

    def on_observer(self, widgets: list):
        """Draw overlay boxes on device canvas for each detected widget."""
        try:
            self._q.put_nowait({
                "type": "overlay_boxes",
                "widgets": [
                    {"x": w.get("x", 0), "y": w.get("y", 0),
                     "w": w.get("width", 0), "h": w.get("height", 0),
                     "label": w.get("text", "") or w.get("element_type", "")}
                    for w in (widgets or [])
                ]
            })
        except queue.Full:
            pass
        self.push_log("OBSERVER", "detected widgets")

    def on_decider(self, target_widget: dict):
        if target_widget:
            try:
                self._q.put_nowait({"type": "overlay_target", "widget": target_widget})
            except queue.Full:
                pass
        self.push_log("DECIDER", "selected target")

    def on_executor(self, x: int, y: int, action_type: str = "click",
                    scroll_direction: str = ""):
        try:
            self._q.put_nowait({"type": "overlay_tap", "x": x, "y": y})
        except queue.Full:
            pass
        self.push_log("EXECUTOR", f"{action_type} at {x},{y}")

    def on_clear(self):
        try:
            self._q.put_nowait({"type": "overlay_clear"})
        except queue.Full:
            pass

    # ── Progress & log ────────────────────────────────────────────────────────

    def push_progress(self, scenario_idx: int, scenario_total: int,
                      step_idx: int = 0, step_total: int = 0,
                      tcs_id: str = "", status: str = ""):
        try:
            self._q.put_nowait({
                "type": "progress",
                "scenario_idx": scenario_idx,
                "scenario_total": scenario_total,
                "tcs_id": tcs_id,
                "status": status,
            })
        except queue.Full:
            pass

    def push_log(self, component: str, message: str, detail: str = ""):
        label, human = _humanize(component, message)
        color = _AGENT_COLOR.get(component.upper(), "#6b7280")
        try:
            self._q.put_nowait({
                "type": "agent_activity",
                "label": label,
                "text": human,
                "color": color,
            })
        except queue.Full:
            pass

    # ── Tkinter window ────────────────────────────────────────────────────────

    def _run_tk(self):
        try:
            import tkinter as tk
            from tkinter import font as tkfont
        except ImportError:
            print("[Dashboard] tkinter not available.")
            return

        try:
            from PIL import Image, ImageTk, ImageDraw, ImageFont
            _pil_ok = True
        except ImportError:
            print("[Dashboard] pip install Pillow  <- device screen needs this")
            _pil_ok = False

        # Device panel width = height * phone aspect ratio
        aspect = self.device_w / max(self.device_h, 1)
        dev_w  = int(_WIN_H * aspect)
        win_w  = dev_w + _RIGHT_W

        root = tk.Tk()
        root.title("MAS AI - Live Testing")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.configure(bg="white")

        sx = (root.winfo_screenwidth()  - win_w) // 2
        sy = (root.winfo_screenheight() - _WIN_H) // 2
        root.geometry(f"{win_w}x{_WIN_H}+{sx}+{sy}")

        # ── Fonts
        f_header = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        f_sub    = tkfont.Font(family="Segoe UI", size=8)
        f_pct    = tkfont.Font(family="Segoe UI", size=36, weight="bold")
        f_count  = tkfont.Font(family="Segoe UI", size=9)
        f_agent  = tkfont.Font(family="Segoe UI", size=8, weight="bold")
        f_feed   = tkfont.Font(family="Segoe UI", size=8)
        f_eta    = tkfont.Font(family="Segoe UI", size=9)

        # ── Left: device canvas ───────────────────────────────────────────────
        dev_canvas = tk.Canvas(root, width=dev_w, height=_WIN_H,
                               bg="#1a1a1a", highlightthickness=0)
        dev_canvas.pack(side="left")

        # Placeholder
        dev_canvas.create_text(dev_w // 2, _WIN_H // 2,
                                text="Connecting to device...",
                                fill="#555", font=f_sub, tags="placeholder")

        # ── Right: info panel ─────────────────────────────────────────────────
        right = tk.Frame(root, bg="white", width=_RIGHT_W)
        right.pack_propagate(False)
        right.pack(side="left", fill="y")

        # thin separator
        tk.Frame(root, width=1, bg="#e5e7eb").place(x=dev_w, y=0, height=_WIN_H)

        pad = {"padx": 14}

        # [1] Header
        hdr = tk.Frame(right, bg="#f9fafb")
        hdr.pack(fill="x")
        tk.Label(hdr, text="Testing in Progress",
                 font=f_header, bg="#f9fafb", fg="#111",
                 anchor="w").pack(fill="x", padx=14, pady=(14, 0))
        tk.Label(hdr, text="Please wait until all scenarios are complete.",
                 font=f_sub, bg="#f9fafb", fg="#6b7280",
                 anchor="w").pack(fill="x", padx=14)
        lbl_eta = tk.Label(hdr, text="Estimated time: calculating...",
                           font=f_eta, bg="#f9fafb", fg="#6366f1",
                           anchor="w")
        lbl_eta.pack(fill="x", padx=14, pady=(2, 10))

        tk.Frame(right, height=1, bg="#e5e7eb").pack(fill="x")

        # [2] Progress
        prog_frame = tk.Frame(right, bg="white")
        prog_frame.pack(fill="x", pady=(14, 0), **pad)

        lbl_pct = tk.Label(prog_frame, text="0%", font=f_pct,
                           bg="white", fg="#111")
        lbl_pct.pack(anchor="w")

        BAR_H = 8
        bar_bg = tk.Canvas(prog_frame, height=BAR_H, bg="#f0f0f0",
                           highlightthickness=0)
        bar_bg.pack(fill="x", pady=(4, 4))
        bar_bg.create_rectangle(0, 0, 0, BAR_H, fill="#111",
                                outline="", tags="fill")

        lbl_count = tk.Label(prog_frame, text="0 / 0 scenarios completed",
                             font=f_count, bg="white", fg="#9ca3af")
        lbl_count.pack(anchor="w")

        tk.Frame(right, height=1, bg="#e5e7eb").pack(fill="x", pady=(12, 0))

        # [3] Agent activity feed — scrollable
        tk.Label(right, text="Agent Activity", font=f_agent,
                 bg="white", fg="#374151", anchor="w").pack(
                 fill="x", padx=14, pady=(10, 4))

        feed_outer = tk.Frame(right, bg="#f9fafb")
        feed_outer.pack(fill="both", expand=True, padx=5, pady=5)

        feed_canvas = tk.Canvas(feed_outer, bg="#f9fafb", highlightthickness=0)
        feed_scroll = tk.Scrollbar(feed_outer, orient="vertical",
                                   command=feed_canvas.yview)
        feed_canvas.configure(yscrollcommand=feed_scroll.set)
        feed_scroll.pack(side="right", fill="y")
        feed_canvas.pack(side="left", fill="both", expand=True)

        feed_inner = tk.Frame(feed_canvas, bg="#f9fafb")
        feed_window = feed_canvas.create_window((0, 0), window=feed_inner,
                                                anchor="nw")

        def _on_feed_resize(event):
            feed_canvas.itemconfig(feed_window, width=event.width)
        feed_canvas.bind("<Configure>", _on_feed_resize)

        def _on_inner_resize(event):
            feed_canvas.configure(scrollregion=feed_canvas.bbox("all"))
        feed_inner.bind("<Configure>", _on_inner_resize)

        feed_rows: list[dict] = []   # kept for compat (unused now)

        # ── Overlay state ─────────────────────────────────────────────────────
        _overlay: dict = {
            "boxes": [],         # list of (x,y,w,h,label) in device coords
            "target": None,      # (x,y,w,h)
            "tap": None,         # (x,y)
            "photo": None,       # current ImageTk reference
            "base_img": None,    # PIL Image without overlays
            "scale": 1.0,
            "off_x": 0,
            "off_y": 0,
        }

        def _draw_overlays():
            """Composite base_img + boxes and redraw canvas."""
            if not _pil_ok or _overlay["base_img"] is None:
                return
            img = _overlay["base_img"].copy()
            draw = ImageDraw.Draw(img)
            sw, sh = img.size

            def dev2screen(dx, dy, dw=0, dh=0):
                sx_ = int(dx * _overlay["scale"]) + _overlay["off_x"]
                sy_ = int(dy * _overlay["scale"]) + _overlay["off_y"]
                sw_ = int(dw * _overlay["scale"])
                sh_ = int(dh * _overlay["scale"])
                return sx_, sy_, sx_ + sw_, sy_ + sh_

            for bx, by, bw, bh, bl in _overlay["boxes"]:
                x0, y0, x1, y1 = dev2screen(bx, by, bw, bh)
                draw.rectangle([x0, y0, x1, y1], outline="#6366f1", width=2)
                if bl:
                    draw.text((x0 + 2, y0 + 2), bl[:20], fill="#6366f1")

            if _overlay["target"]:
                tx, ty, tw, th = _overlay["target"]
                x0, y0, x1, y1 = dev2screen(tx, ty, tw, th)
                draw.rectangle([x0, y0, x1, y1], outline="#f59e0b", width=3)

            if _overlay["tap"]:
                tx, ty = _overlay["tap"]
                cx, cy, _, _ = dev2screen(tx, ty)
                r = 18
                draw.ellipse([cx - r, cy - r, cx + r, cy + r],
                             outline="#10b981", width=3)
                draw.line([cx - 6, cy, cx + 6, cy], fill="#10b981", width=2)
                draw.line([cx, cy - 6, cx, cy + 6], fill="#10b981", width=2)

            photo = ImageTk.PhotoImage(img)
            _overlay["photo"] = photo
            dev_canvas.delete("shot")
            dev_canvas.create_image(dev_w // 2, _WIN_H // 2,
                                    anchor="center", image=photo, tags="shot")
            dev_canvas.delete("placeholder")

        # ── State ─────────────────────────────────────────────────────────────
        state = {
            "done": 0, "total": 0, "t0": None,
            "feed": [],   # list of (label_str, text_str, color_str), newest first
        }

        def set_bar(pct: float):
            root.update_idletasks()
            w = bar_bg.winfo_width()
            bar_bg.coords("fill", 0, 0, int(w * pct / 100), BAR_H)


        def poll_queue():
            try:
                for _ in range(20):   # drain burst
                    msg = self._q.get_nowait()
                    t = msg["type"]

                    if t == "_quit":
                        root.destroy()
                        return

                    elif t == "progress":
                        done  = msg["scenario_idx"]
                        total = msg["scenario_total"]
                        state["done"]  = done
                        state["total"] = total
                        if state["t0"] is None and done > 0:
                            state["t0"] = time.time()
                        pct = round(done / total * 100) if total else 0
                        lbl_pct.config(text=f"{pct}%")
                        set_bar(pct)
                        lbl_count.config(
                            text=f"{done} / {total} scenarios completed")
                        if done > 0 and total > 0 and state["t0"]:
                            elapsed = time.time() - state["t0"]
                            if done < total:
                                rem = int(elapsed / done * (total - done))
                                m, s = rem // 60, rem % 60
                                eta = f"{m}m {s}s" if m else f"{s}s"
                                lbl_eta.config(
                                    text=f"Estimated time: ~{eta} remaining")
                            else:
                                lbl_eta.config(text="All scenarios completed!")

                    elif t == "agent_activity":
                        _append_feed(msg["label"], msg["text"], msg["color"])

                    elif t == "overlay_boxes":
                        _overlay["boxes"] = [
                            (w["x"], w["y"], w["w"], w["h"], w["label"])
                            for w in msg["widgets"]
                        ]
                        _draw_overlays()

                    elif t == "overlay_target":
                        tw = msg["widget"]
                        _overlay["target"] = (
                            tw.get("x", 0), tw.get("y", 0),
                            tw.get("width", 0), tw.get("height", 0))
                        _draw_overlays()

                    elif t == "overlay_tap":
                        _overlay["tap"] = (msg["x"], msg["y"])
                        _draw_overlays()
                        # Clear tap after 600ms
                        root.after(600, lambda: _clear_tap())

                    elif t == "overlay_clear":
                        _overlay["boxes"] = []
                        _overlay["target"] = None
                        _overlay["tap"]    = None
                        _draw_overlays()

            except queue.Empty:
                pass
            root.after(80, poll_queue)

        def _clear_tap():
            _overlay["tap"] = None
            _draw_overlays()

        # ── Screencap thread ──────────────────────────────────────────────────
        def screencap_loop():
            while self._running:
                if not _pil_ok or not self.device_id:
                    time.sleep(_SHOT_INTERVAL)
                    continue
                try:
                    result = subprocess.run(
                        ["adb", "-s", self.device_id,
                         "exec-out", "screencap", "-p"],
                        capture_output=True, timeout=6
                    )
                    if result.returncode == 0 and result.stdout:
                        img = Image.open(BytesIO(result.stdout))
                        # Fit into dev_w x _WIN_H, maintain aspect
                        ratio = min(dev_w / img.width, _WIN_H / img.height)
                        nw = int(img.width  * ratio)
                        nh = int(img.height * ratio)
                        img = img.resize((nw, nh), Image.LANCZOS)
                        # center offsets for overlay mapping
                        off_x = (dev_w - nw) // 2
                        off_y = (_WIN_H - nh) // 2
                        _overlay["base_img"] = img
                        _overlay["scale"]    = ratio
                        _overlay["off_x"]   = off_x
                        _overlay["off_y"]   = off_y
                        root.after(0, _draw_overlays)
                except Exception:
                    pass
                time.sleep(_SHOT_INTERVAL)

        if self.device_id:
            threading.Thread(target=screencap_loop, daemon=True).start()

        root.after(80, poll_queue)
        root.mainloop()


# Aliases
VisualMonitor    = TkDashboard
BrowserDashboard = TkDashboard
