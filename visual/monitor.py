"""
visual/monitor.py — TkDashboard
---------------------------------
Floating native window (tkinter, stdlib only).
Kiri: device screenshot via ADB screencap (refresh ~1s).
Kanan: progress counter, bar, status card, 3 recent updates.

Public API (identik dengan sebelumnya):
  monitor = VisualMonitor(device_id, device_w, device_h)
  monitor.start()
  monitor.push_progress(scenario_idx, scenario_total, step_idx, step_total, tcs_id, status)
  monitor.push_log(component, message, detail)   ← hanya pesan QA yg muncul
  monitor.on_observer(widgets)
  monitor.on_decider(target_widget)
  monitor.on_executor(x, y, action_type, scroll_direction)
  monitor.on_clear()
  monitor.stop()

Requires: tkinter (stdlib), Pillow (pip install Pillow), adb in PATH
Env vars: LIVE_DASHBOARD_ENABLED (default true)
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

# Window dimensions
_WIN_W  = 900
_WIN_H  = 640
_DEV_W  = 360   # left panel width
_SHOT_INTERVAL = 1.2  # seconds between screencaps


class TkDashboard:
    """Compact floating window: device screen left, progress right."""

    def __init__(self, device_id: str = "", device_w: int = 1080, device_h: int = 2400):
        self.device_id = device_id or os.getenv("TARGET_DEVICE", "")
        self.device_w  = device_w
        self.device_h  = device_h
        self._enabled  = _ENABLED
        self._q: queue.Queue = queue.Queue()
        self._tk_thread: threading.Thread | None = None
        self._running = False

    # ── Lifecycle ──────────────────────────────────────────────────────

    def start(self) -> bool:
        if not self._enabled:
            return False
        self._running = True
        self._tk_thread = threading.Thread(target=self._run_tk, daemon=True)
        self._tk_thread.start()
        return True

    def stop(self):
        self._running = False
        self._q.put({"type": "_quit"})

    # ── Agent hooks (thin shims — kept for runner compatibility) ───────

    def on_observer(self, widgets: list): pass
    def on_decider(self, target_widget: dict): pass
    def on_executor(self, x: int, y: int, action_type: str = "click",
                    scroll_direction: str = ""): pass
    def on_clear(self): pass

    # ── Public update methods ──────────────────────────────────────────

    def push_progress(self, scenario_idx: int, scenario_total: int,
                      step_idx: int = 0, step_total: int = 0,
                      tcs_id: str = "", status: str = ""):
        self._q.put({
            "type": "progress",
            "scenario_idx": scenario_idx,
            "scenario_total": scenario_total,
            "tcs_id": tcs_id,
            "status": status,
        })

    def push_log(self, component: str, message: str, detail: str = ""):
        # Only surface QA-relevant messages (not developer internals)
        skip = {"OBSERVER", "DECIDER", "EXECUTOR"}
        if component.upper() in skip:
            return
        self._q.put({"type": "log", "message": message})

    # ── Tk window (runs in its own thread) ────────────────────────────

    def _run_tk(self):
        try:
            import tkinter as tk
            from tkinter import font as tkfont
        except ImportError:
            print("[Dashboard] tkinter not available.")
            return

        try:
            from PIL import Image, ImageTk
            _pil_ok = True
        except ImportError:
            print("[Dashboard] Pillow not found — install: pip install Pillow\n"
                  "           Device screen will be blank.")
            _pil_ok = False

        root = tk.Tk()
        root.title("MAS AI")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.configure(bg="white")

        # Center on screen
        root.update_idletasks()
        sx = (root.winfo_screenwidth()  - _WIN_W) // 2
        sy = (root.winfo_screenheight() - _WIN_H) // 2
        root.geometry(f"{_WIN_W}x{_WIN_H}+{sx}+{sy}")

        # ── Fonts
        f_label  = tkfont.Font(family="Segoe UI", size=9)
        f_big    = tkfont.Font(family="Segoe UI", size=48, weight="bold")
        f_denom  = tkfont.Font(family="Segoe UI", size=22)
        f_tcs    = tkfont.Font(family="Segoe UI", size=14, weight="bold")
        f_badge  = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        f_update = tkfont.Font(family="Segoe UI", size=10)

        # ── Layout: left panel (device) + right panel (info)
        left = tk.Frame(root, bg="#f8f8f8", width=_DEV_W, height=_WIN_H)
        left.pack_propagate(False)
        left.pack(side="left", fill="y")

        right = tk.Frame(root, bg="white")
        right.pack(side="left", fill="both", expand=True, padx=16, pady=14)

        # Separator
        tk.Frame(root, bg="#f0f0f0", width=1).place(x=_DEV_W, y=0, height=_WIN_H)

        # ── Left: device label + canvas
        tk.Label(left, text="DEVICE", font=f_label, bg="#f8f8f8",
                 fg="#ccc").pack(pady=(10, 4))
        dev_canvas = tk.Canvas(left, bg="#f0f0f0", highlightthickness=0,
                               width=_DEV_W - 2,
                               height=_WIN_H - 36)
        dev_canvas.pack(padx=1)
        _dev_img_ref: list = []  # keep reference to avoid GC

        # Placeholder phone icon text
        dev_canvas.create_text((_DEV_W - 2) // 2, (_WIN_H - 36) // 2,
                                text="📱\nNo device", fill="#ccc",
                                font=f_update, justify="center",
                                tags="placeholder")

        # ── Right: Test Cases counter
        tk.Label(right, text="TEST CASES", font=f_label, bg="white",
                 fg="#bbb", anchor="w").pack(fill="x")

        counter_frame = tk.Frame(right, bg="white")
        counter_frame.pack(fill="x")
        lbl_done  = tk.Label(counter_frame, text="—", font=f_big, bg="white", fg="#111")
        lbl_done.pack(side="left")
        lbl_denom = tk.Label(counter_frame, text=" / —", font=f_denom, bg="white", fg="#bbb")
        lbl_denom.pack(side="left", padx=(2, 0))

        # ── Progress bar (canvas)
        BAR_H = 10
        bar_frame = tk.Frame(right, bg="white")
        bar_frame.pack(fill="x", pady=(8, 0))
        bar_canvas = tk.Canvas(bar_frame, height=BAR_H, bg="#f0f0f0",
                               highlightthickness=0)
        bar_canvas.pack(fill="x")
        bar_canvas.create_rectangle(0, 0, 0, BAR_H, fill="#111",
                                    outline="", tags="fill")

        meta_frame = tk.Frame(right, bg="white")
        meta_frame.pack(fill="x")
        lbl_pct = tk.Label(meta_frame, text="0%", font=f_label, bg="white", fg="#bbb")
        lbl_pct.pack(side="left")
        lbl_eta = tk.Label(meta_frame, text="", font=f_label, bg="white", fg="#bbb")
        lbl_eta.pack(side="right")

        # ── Status card
        card = tk.Frame(right, bg="white", bd=1, relief="solid",
                        highlightbackground="#f0f0f0")
        card.pack(fill="x", pady=(10, 0))
        tk.Label(card, text="RUNNING", font=f_label, bg="white",
                 fg="#bbb", anchor="w").pack(fill="x", padx=8, pady=(6, 0))
        lbl_tcs   = tk.Label(card, text="Waiting…", font=f_tcs,
                              bg="white", fg="#111", anchor="w")
        lbl_tcs.pack(fill="x", padx=8)
        lbl_badge = tk.Label(card, text="", font=f_badge, bg="#f3f4f6",
                              fg="#9ca3af", anchor="w", padx=6, pady=1)
        lbl_badge.pack(anchor="w", padx=8, pady=(2, 8))

        # ── Updates feed (3 lines)
        tk.Frame(right, height=1, bg="#f0f0f0").pack(fill="x", pady=(8, 0))
        feed_frame = tk.Frame(right, bg="white")
        feed_frame.pack(fill="x", pady=(4, 0))
        feed_labels = [
            tk.Label(feed_frame, text="", font=f_update, bg="white",
                     fg="#666", anchor="w")
            for _ in range(3)
        ]
        for fl in feed_labels:
            fl.pack(fill="x")

        # ── State
        state = {
            "done": 0, "total": 0, "t0": None,
            "updates": [],  # list of str, newest first
        }

        # ── Bar width helper
        def set_bar(pct: float):
            root.update_idletasks()
            w = bar_canvas.winfo_width()
            bar_canvas.coords("fill", 0, 0, int(w * pct / 100), BAR_H)

        # ── Badge colour
        BADGE_STYLES = {
            "run":  ("#eff6ff", "#2563eb"),
            "pass": ("#dcfce7", "#16a34a"),
            "fail": ("#fee2e2", "#dc2626"),
            "":     ("#f3f4f6", "#9ca3af"),
        }

        def set_badge(text: str, style: str):
            bg, fg = BADGE_STYLES.get(style, BADGE_STYLES[""])
            lbl_badge.config(text=text, bg=bg, fg=fg)

        # ── Feed update
        def push_update(msg: str):
            t = time.strftime("%H:%M")
            state["updates"].insert(0, f"{msg}  {t}")
            state["updates"] = state["updates"][:3]
            for i, fl in enumerate(feed_labels):
                fl.config(text=state["updates"][i] if i < len(state["updates"]) else "")

        # ── Process queue
        def poll_queue():
            try:
                while True:
                    msg = self._q.get_nowait()
                    if msg["type"] == "_quit":
                        root.destroy()
                        return
                    elif msg["type"] == "progress":
                        done  = msg["scenario_idx"]
                        total = msg["scenario_total"]
                        tcs   = msg.get("tcs_id", "")
                        st    = (msg.get("status") or "").upper()
                        state["done"]  = done
                        state["total"] = total
                        if state["t0"] is None and done > 0:
                            state["t0"] = time.time()
                        lbl_done.config(text=str(done) if total else "—")
                        lbl_denom.config(text=f" / {total}" if total else " / —")
                        pct = round(done / total * 100) if total else 0
                        lbl_pct.config(text=f"{pct}%")
                        set_bar(pct)
                        if done > 0 and total > 0 and done < total and state["t0"]:
                            rem = int((time.time() - state["t0"]) / done * (total - done))
                            m, s = rem // 60, rem % 60
                            lbl_eta.config(text=f"~{m}m {s}s" if m else f"~{s}s")
                        elif done >= total > 0:
                            lbl_eta.config(text="Done ✓")
                        if tcs:
                            lbl_tcs.config(text=tcs)
                        if st == "RUNNING":
                            set_badge("● Running", "run")
                        elif st == "PASSED":
                            set_badge("Passed ✓", "pass")
                            push_update(f"{tcs} passed ✓")
                        elif "ANOMALY" in st or "FAIL" in st:
                            set_badge("Needs review", "fail")
                            push_update(f"{tcs} — needs review ⚠")
                    elif msg["type"] == "log":
                        push_update(msg["message"])
            except queue.Empty:
                pass
            root.after(120, poll_queue)

        # ── Device screencap thread
        _shot_lock = threading.Lock()

        def screencap_loop():
            while self._running:
                if not _pil_ok or not self.device_id:
                    time.sleep(_SHOT_INTERVAL)
                    continue
                try:
                    result = subprocess.run(
                        ["adb", "-s", self.device_id,
                         "exec-out", "screencap", "-p"],
                        capture_output=True, timeout=5
                    )
                    if result.returncode == 0 and result.stdout:
                        img = Image.open(BytesIO(result.stdout))
                        # Scale to fit left panel
                        panel_h = _WIN_H - 36
                        ratio = min((_DEV_W - 2) / img.width, panel_h / img.height)
                        new_w = int(img.width * ratio)
                        new_h = int(img.height * ratio)
                        img = img.resize((new_w, new_h), Image.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        with _shot_lock:
                            _dev_img_ref.clear()
                            _dev_img_ref.append(photo)
                        # Schedule canvas update on main thread
                        root.after(0, lambda p=photo: _update_canvas(p))
                except Exception:
                    pass
                time.sleep(_SHOT_INTERVAL)

        def _update_canvas(photo):
            dev_canvas.delete("placeholder")
            dev_canvas.delete("shot")
            x = (_DEV_W - 2) // 2
            y = (_WIN_H - 36) // 2
            dev_canvas.create_image(x, y, anchor="center", image=photo, tags="shot")

        if self.device_id:
            threading.Thread(target=screencap_loop, daemon=True).start()

        root.after(120, poll_queue)
        root.mainloop()


# Drop-in alias — runner imports VisualMonitor
VisualMonitor = TkDashboard
BrowserDashboard = TkDashboard  # backwards compat
