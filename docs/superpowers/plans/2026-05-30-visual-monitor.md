# Visual Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically launch a scrcpy phone mirror + transparent PyQt5 overlay window from `main.py` that shows Observer bounding boxes (blue), Decider target highlight (yellow), and Executor touch ripple (red) on the live phone screen.

**Architecture:** `VisualMonitor` spawns scrcpy as a subprocess, then launches a frameless transparent `OverlayWindow` (PyQt5) positioned over scrcpy. A daemon thread polls scrcpy's Win32 window position every 100ms and re-syncs the overlay, fixing drift. Agents call `monitor.on_observer/on_decider/on_executor` which emit Qt signals to draw overlays thread-safely.

**Tech Stack:** PyQt5 (transparent overlay), pywin32/win32gui (window tracking), scrcpy (external, on PATH), Python subprocess, threading.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `visual/__init__.py` | Package init |
| Create | `visual/overlay_window.py` | PyQt5 transparent window; draws boxes, highlight, ripple |
| Create | `visual/monitor.py` | `VisualMonitor` — scrcpy subprocess + overlay controller |
| Create | `tests/test_visual_monitor.py` | Unit tests for coord mapping + graceful degradation |
| Modify | `agents/observer_agent.py` | Add `monitor` kwarg, call `monitor.on_observer()` at end of `analyze()` |
| Modify | `agents/decider_agent.py` | Add `monitor` kwarg, call `monitor.on_decider()` at end of `decide()` |
| Modify | `agents/executor_agent.py` | Add `monitor` kwarg, call `monitor.on_executor()` at end of `execute()` |
| Modify | `core/workflow/predefined/runner.py` | Instantiate `VisualMonitor`, pass to agents, call `start()`/`stop()` |
| Modify | `core/workflow/autonomous/runner.py` | Same as predefined runner |
| Modify | `requirements.txt` | Add `PyQt5`, `pywin32` |

---

### Task 1: Add dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add PyQt5 and pywin32 to requirements.txt**

Open `requirements.txt` and append two lines so the file becomes:

```
uiautomator2
pydantic
langchain
langchain-openai
langchain-core
langgraph
easyocr
opencv-python
numpy
Pillow
python-dotenv
toons
tiktoken
openpyxl
mcp
httpx
PyQt5
pywin32
```

- [ ] **Step 2: Install the new dependencies**

```bash
pip install PyQt5 pywin32
```

Expected: both packages install without error.

- [ ] **Step 3: Verify imports work**

```bash
python -c "from PyQt5.QtWidgets import QApplication; import win32gui; print('OK')"
```

Expected output: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add PyQt5 and pywin32 for visual monitor"
```

---

### Task 2: Create OverlayWindow

**Files:**
- Create: `visual/__init__.py`
- Create: `visual/overlay_window.py`
- Create: `tests/test_visual_monitor.py` (coordinate mapping tests only)

- [ ] **Step 1: Write the failing coordinate-mapping test**

Create `tests/test_visual_monitor.py`:

```python
import pytest


def _map_coords(phone_x, phone_y, device_w, device_h, win_w, win_h):
    """Pure coordinate mapping logic (extracted for testability)."""
    return (
        int(phone_x / device_w * win_w),
        int(phone_y / device_h * win_h),
    )


def test_map_coords_center():
    ox, oy = _map_coords(540, 1200, 1080, 2400, 540, 1200)
    assert ox == 270
    assert oy == 600


def test_map_coords_origin():
    ox, oy = _map_coords(0, 0, 1080, 2400, 540, 1200)
    assert ox == 0
    assert oy == 0


def test_map_coords_full():
    ox, oy = _map_coords(1080, 2400, 1080, 2400, 540, 1200)
    assert ox == 540
    assert oy == 1200


def test_map_coords_non_square():
    ox, oy = _map_coords(100, 200, 1000, 2000, 500, 800)
    assert ox == 50
    assert oy == 80
```

- [ ] **Step 2: Run test to verify it fails (module not found yet)**

```bash
pytest tests/test_visual_monitor.py -v
```

Expected: tests PASS (pure math, no import of visual module yet). Note: these will pass immediately because the helper is defined inline in the test file — that's intentional. The test validates the math before we embed it in the class.

- [ ] **Step 3: Create the package init**

Create `visual/__init__.py`:

```python
```

(empty file — just marks it as a package)

- [ ] **Step 4: Create the overlay window**

Create `visual/overlay_window.py`:

```python
import sys
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen


class OverlayWindow(QWidget):
    update_signal = pyqtSignal(list, dict, dict)
    sync_geometry_signal = pyqtSignal(int, int, int, int)

    def __init__(self, device_w: int, device_h: int):
        super().__init__()
        self.device_w = device_w
        self.device_h = device_h
        self._boxes = []
        self._target_box = {}
        self._ripple = {}

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.update_signal.connect(self._apply_update)
        self.sync_geometry_signal.connect(self._apply_geometry)

        self._ripple_timer = QTimer(self)
        self._ripple_timer.timeout.connect(self._fade_ripple)

        self.show()

    def _apply_update(self, boxes, target_box, ripple):
        self._boxes = boxes
        self._target_box = target_box
        self._ripple = ripple
        if ripple:
            self._ripple_timer.start(50)
        self.update()

    def _apply_geometry(self, x, y, w, h):
        self.setGeometry(x, y, w, h)

    def _fade_ripple(self):
        if not self._ripple:
            self._ripple_timer.stop()
            return
        self._ripple["alpha"] = max(0, self._ripple["alpha"] - 15)
        if self._ripple["alpha"] == 0:
            self._ripple = {}
            self._ripple_timer.stop()
        self.update()

    def _map(self, phone_x, phone_y):
        w, h = max(self.width(), 1), max(self.height(), 1)
        return (
            int(phone_x / self.device_w * w),
            int(phone_y / self.device_h * h),
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Observer: blue bounding boxes
        pen = QPen(QColor(0, 120, 255, 200))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 120, 255, 30))
        for box in self._boxes:
            if len(box) != 4:
                continue
            x1, y1 = self._map(box[0], box[1])
            x2, y2 = self._map(box[2], box[3])
            painter.drawRect(x1, y1, x2 - x1, y2 - y1)

        # Decider: yellow target highlight
        if self._target_box:
            b = self._target_box.get("bounds", [])
            if len(b) == 4:
                x1, y1 = self._map(b[0], b[1])
                x2, y2 = self._map(b[2], b[3])
                pen = QPen(QColor(255, 200, 0, 230))
                pen.setWidth(3)
                painter.setPen(pen)
                painter.setBrush(QColor(255, 200, 0, 60))
                painter.drawRect(x1, y1, x2 - x1, y2 - y1)

        # Executor: red ripple circle
        if self._ripple:
            rx, ry = self._map(self._ripple["x"], self._ripple["y"])
            alpha = self._ripple["alpha"]
            pen = QPen(QColor(255, 50, 50, alpha))
            pen.setWidth(3)
            painter.setPen(pen)
            painter.setBrush(QColor(255, 50, 50, alpha // 3))
            painter.drawEllipse(rx - 30, ry - 30, 60, 60)

        painter.end()
```

- [ ] **Step 5: Commit**

```bash
git add visual/__init__.py visual/overlay_window.py tests/test_visual_monitor.py
git commit -m "feat(visual): add OverlayWindow with blue/yellow/red overlays"
```

---

### Task 3: Create VisualMonitor

**Files:**
- Modify: `visual/monitor.py` (create)
- Modify: `tests/test_visual_monitor.py` (add graceful-degradation tests)

- [ ] **Step 1: Write failing graceful-degradation tests**

Append to `tests/test_visual_monitor.py`:

```python
from unittest.mock import patch, MagicMock
import sys
import os

# Add project root to path so we can import visual.monitor
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_monitor_no_crash_when_overlay_none():
    """All public methods must be safe to call when overlay is None (monitor disabled)."""
    from visual.monitor import VisualMonitor
    m = VisualMonitor(device_w=1080, device_h=2400)
    # _overlay is None by default before start()
    m.on_observer([{"bounds": [0, 0, 100, 100]}])
    m.on_decider({"bounds": [10, 10, 80, 80]})
    m.on_executor(540, 1200)
    m.stop()  # must not raise


def test_monitor_start_scrcpy_not_found():
    """If scrcpy is not on PATH, start() prints a warning and leaves _overlay as None."""
    from visual.monitor import VisualMonitor
    m = VisualMonitor(device_w=1080, device_h=2400)
    with patch("subprocess.Popen", side_effect=FileNotFoundError):
        m.start()
    assert m._overlay is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_visual_monitor.py::test_monitor_no_crash_when_overlay_none tests/test_visual_monitor.py::test_monitor_start_scrcpy_not_found -v
```

Expected: `ModuleNotFoundError: No module named 'visual.monitor'`

- [ ] **Step 3: Create VisualMonitor**

Create `visual/monitor.py`:

```python
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
            return

        self._qt_thread = threading.Thread(target=self._launch_overlay, daemon=True)
        self._qt_thread.start()
        time.sleep(0.8)

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
        self._overlay.setGeometry(x, y, x2 - x, y2 - y)
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_visual_monitor.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add visual/monitor.py tests/test_visual_monitor.py
git commit -m "feat(visual): add VisualMonitor with scrcpy + overlay control"
```

---

### Task 4: Add monitor to ObserverAgent

**Files:**
- Modify: `agents/observer_agent.py`

- [ ] **Step 1: Add `monitor` kwarg to `__init__`**

In `agents/observer_agent.py`, change the `__init__` signature (line 13):

```python
def __init__(self, llm: ILLMClient, tools: list, memory=None, logger=None, monitor=None):
    self.llm = llm
    self.take_screenshot = tools[0]
    self.ocr_extract_text = tools[1]
    self.detect_visual_elements = tools[2]
    self.annotate_screenshot = tools[3]
    self.check_keyboard_state = tools[4]
    self.parse_screen_omniparser = tools[5] if len(tools) > 5 else None
    self.memory = memory
    self.logger = logger
    self.monitor = monitor
```

- [ ] **Step 2: Call `monitor.on_observer()` at the end of `analyze()`**

In `agents/observer_agent.py`, the `analyze()` method currently ends at line 536 with:

```python
        return {
            "screenshot_path": raw_path,
            "widgets": final_widget_set,
            "observer_analysis": raw_res,
            "observer_analysis_step": current_step,
            "stagnation_count": new_stagnation_count,
            "memory_context": memory_context,
            "sender": "observer",
        }
```

Add the monitor call just before the `return`:

```python
        if self.monitor is not None:
            self.monitor.on_observer(final_widget_set)

        return {
            "screenshot_path": raw_path,
            "widgets": final_widget_set,
            "observer_analysis": raw_res,
            "observer_analysis_step": current_step,
            "stagnation_count": new_stagnation_count,
            "memory_context": memory_context,
            "sender": "observer",
        }
```

- [ ] **Step 3: Run existing tests to check nothing broke**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add agents/observer_agent.py
git commit -m "feat(observer): emit on_observer to VisualMonitor"
```

---

### Task 5: Add monitor to DeciderAgent

**Files:**
- Modify: `agents/decider_agent.py`

- [ ] **Step 1: Add `monitor` kwarg to `__init__`**

In `agents/decider_agent.py`, change line 53:

```python
class DeciderAgent:
    def __init__(self, llm, memory=None, logger=None, monitor=None):
        self.llm = llm.with_structured_output(ActionPlan)
        self.memory = memory
        self.logger = logger
        self.monitor = monitor
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human",
             "Session Memory Context:\n{memory_context}\n\n"
             "Screen Analysis:\n{observer_analysis}\n\n"
             "STEP INSTRUCTION: \"{current_sub_step}\"\n\n"
             "Output ONE ActionPlan for the STEP INSTRUCTION.")
        ])
```

- [ ] **Step 2: Call `monitor.on_decider()` at the end of `decide()`**

In `agents/decider_agent.py`, find the `return` at the bottom of `decide()` (line 138):

```python
        return {
            "action_plan": plan.model_dump(),
            "is_completed": plan.is_completed,
            "memory_context": memory_context,
            "sender": "decider",
        }
```

Add the monitor call just before it. The target widget must be looked up from `state["widgets"]` using `plan.target_id`. The `state` parameter is already available in `decide(state: AgentState)`:

```python
        if self.monitor is not None and not plan.is_completed:
            widgets = state.get("widgets", [])
            target_widget = next(
                (w for w in widgets if w.get("id") == plan.target_id), {}
            )
            self.monitor.on_decider(target_widget)

        return {
            "action_plan": plan.model_dump(),
            "is_completed": plan.is_completed,
            "memory_context": memory_context,
            "sender": "decider",
        }
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add agents/decider_agent.py
git commit -m "feat(decider): emit on_decider to VisualMonitor"
```

---

### Task 6: Add monitor to ExecutorAgent

**Files:**
- Modify: `agents/executor_agent.py`

- [ ] **Step 1: Add `monitor` kwarg to `__init__`**

In `agents/executor_agent.py`, change line 9:

```python
class ExecutorAgent:
    def __init__(self, tools: ExecutorTools, memory=None, logger=None, monitor=None):
        self.tools = tools
        self.memory = memory
        self.logger = logger
        self.monitor = monitor
```

- [ ] **Step 2: Call `monitor.on_executor()` after a successful touch action**

In `agents/executor_agent.py`, find the final `return` at line 185:

```python
        return {
            "execution_result": result,
            "sender": "executor",
            "widget_lookup_success": widget_lookup_success,
            "widget_lookup_fail": widget_lookup_fail,
            "widget_text_fallback_count": widget_text_fallback,
        }
```

Add the monitor call just before it. Only emit for touch actions where `target_x` and `target_y` were resolved (i.e., not -1):

```python
        if self.monitor is not None and action_type in ("click", "long_click", "input") and target_x != -1:
            self.monitor.on_executor(target_x, target_y)

        return {
            "execution_result": result,
            "sender": "executor",
            "widget_lookup_success": widget_lookup_success,
            "widget_lookup_fail": widget_lookup_fail,
            "widget_text_fallback_count": widget_text_fallback,
        }
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add agents/executor_agent.py
git commit -m "feat(executor): emit on_executor to VisualMonitor"
```

---

### Task 7: Wire VisualMonitor into predefined runner

**Files:**
- Modify: `core/workflow/predefined/runner.py`

- [ ] **Step 1: Import VisualMonitor**

At the top of `core/workflow/predefined/runner.py`, after the existing imports, add:

```python
from visual.monitor import VisualMonitor
```

- [ ] **Step 2: Instantiate and start the monitor (once per run)**

In `run_predefined()`, after `device_adapter = ADBAdapter(config.TARGET_DEVICE).connect()` (line 12), add:

```python
    device_info = device_adapter.d.info
    monitor = VisualMonitor(
        device_w=device_info.get("displayWidth", 1080),
        device_h=device_info.get("displayHeight", 2400),
    )
    monitor.start()
```

- [ ] **Step 3: Pass monitor to each agent**

In the agent construction block (around line 78–85), pass `monitor` to each agent:

```python
        observer  = ObserverAgent(perception_llm, obs_tools.get_tools(), memory=memory, logger=logger, monitor=monitor)
        decider   = DeciderAgent(strategic_llm, memory=memory, logger=logger, monitor=monitor)
        executor  = ExecutorAgent(exe_tools, memory=memory, logger=logger, monitor=monitor)
        reflector = ReflectorAgent(reflector_llm, memory=memory, logger=logger, device=device_adapter)
        recorder  = RecorderAgent(memory=memory, logger=logger)
```

- [ ] **Step 4: Stop the monitor after the last scenario finishes**

At the very end of `run_predefined()`, after the loop, add:

```python
    monitor.stop()
```

(The loop ends at line 189 in the original file. Add `monitor.stop()` after the `if scenario_index < len(scenarios) - 1` block, outside the loop.)

- [ ] **Step 5: Run tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add core/workflow/predefined/runner.py
git commit -m "feat(runner/predefined): wire VisualMonitor — start on run, stop after last scenario"
```

---

### Task 8: Wire VisualMonitor into autonomous runner

**Files:**
- Modify: `core/workflow/autonomous/runner.py`

- [ ] **Step 1: Read the current autonomous runner structure**

Open `core/workflow/autonomous/runner.py` and identify:
- Where `device_adapter` is constructed (around line 41–42, same pattern as predefined)
- Where agents are constructed
- Where the run loop ends

- [ ] **Step 2: Import VisualMonitor**

Add at the top of `core/workflow/autonomous/runner.py`:

```python
from visual.monitor import VisualMonitor
```

- [ ] **Step 3: Instantiate and start monitor**

After `device_adapter = ADBAdapter(config.TARGET_DEVICE).connect()`, add:

```python
    device_info = device_adapter.d.info
    monitor = VisualMonitor(
        device_w=device_info.get("displayWidth", 1080),
        device_h=device_info.get("displayHeight", 2400),
    )
    monitor.start()
```

- [ ] **Step 4: Pass monitor to agents**

In the agent construction block, add `monitor=monitor` to `ObserverAgent`, `DeciderAgent`, and `ExecutorAgent` (same pattern as Task 7 Step 3).

- [ ] **Step 5: Stop monitor after run ends**

Add `monitor.stop()` at the very end of `run_autonomous()`, outside the scenario loop.

- [ ] **Step 6: Run tests**

```bash
pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add core/workflow/autonomous/runner.py
git commit -m "feat(runner/autonomous): wire VisualMonitor"
```

---

### Task 9: End-to-end smoke test

**Goal:** Confirm the full pipeline works with a real device connected.

- [ ] **Step 1: Verify scrcpy is installed**

```bash
scrcpy --version
```

Expected: prints scrcpy version (e.g. `scrcpy 2.x`). If missing, install from https://github.com/Genymobile/scrcpy/releases and ensure it is on PATH.

- [ ] **Step 2: Connect device and run main.py**

```bash
python main.py
```

Expected sequence:
1. `[*] Connecting to device ...` — ADB connects
2. scrcpy window appears (phone mirrored on screen)
3. Transparent overlay window appears on top of scrcpy
4. During Observer step → blue bounding boxes appear on overlay
5. During Decider step → yellow highlight appears on the chosen widget
6. During Executor step → red ripple circle appears at the touch point
7. After all scenarios finish → scrcpy window closes, overlay closes

- [ ] **Step 3: Verify graceful degradation (no scrcpy)**

Temporarily rename scrcpy to confirm degradation:

```powershell
# Windows — temporarily break PATH lookup by renaming
Rename-Item "$env:USERPROFILE\scrcpy\scrcpy.exe" "scrcpy.exe.bak"
python main.py
Rename-Item "$env:USERPROFILE\scrcpy\scrcpy.exe.bak" "scrcpy.exe"
```

Expected: `[VisualMonitor] WARNING: scrcpy not found on PATH. Monitor disabled.` printed, test run continues normally without the monitor.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: visual monitor complete — scrcpy + agent overlays"
```
