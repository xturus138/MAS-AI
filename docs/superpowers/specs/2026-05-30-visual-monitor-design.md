# Visual Monitor — Design Spec
*Date: 2026-05-30*

## Goal

When `main.py` runs, a live window automatically appears showing:
- The real phone screen mirrored via scrcpy
- Agent event overlays drawn transparently on top (bounding boxes, target highlight, touch ripple)

The window closes when the run ends. No manual steps needed.

---

## Architecture

Two components work together:

```
main.py
  └─ VisualMonitor (visual/monitor.py)
        ├─ scrcpy subprocess         ← live phone video
        └─ OverlayWindow (PyQt5)     ← transparent layer on top of scrcpy
              └─ WindowTracker thread ← polls scrcpy window position every 100ms
```

### `VisualMonitor` (visual/monitor.py)

Public API:
- `start()` — spawns scrcpy, launches OverlayWindow in a background thread
- `stop()` — kills scrcpy, closes overlay window
- `on_observer(widgets: list)` — draws blue bounding boxes for all detected widgets
- `on_decider(target_widget: dict)` — highlights the selected target widget in yellow
- `on_executor(x: int, y: int)` — draws a red ripple circle at the touch coordinates, fades over 1s

### `OverlayWindow` (visual/overlay_window.py)

- PyQt5 `QWidget` with `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WA_TranslucentBackground`
- Accepts draw commands via Qt signals (thread-safe)
- Draws shapes using `QPainter` on each `paintEvent`
- Overlay state: `{boxes: [...], target_box: {...}, ripple: {x, y, alpha}}`
- Ripple animation: `QTimer` decrements alpha every 50ms until 0

### WindowTracker thread

- Runs every 100ms in a daemon thread
- Uses `win32gui.FindWindow(None, "scrcpy")` to get scrcpy's HWND
- Reads position + size with `win32gui.GetWindowRect`
- Calls `overlay_window.sync_geometry(x, y, w, h)` to reposition the overlay
- Fixes the drift problem: overlay follows scrcpy no matter where the user drags it

---

## Coordinate Mapping

Agents work in **phone logical coordinates** (e.g. 1080×2400 px).  
scrcpy scales the phone to fit its window (e.g. 540×1200 on screen).

Mapping formula applied by OverlayWindow before drawing:
```
overlay_x = phone_x / phone_w * scrcpy_win_w
overlay_y = phone_y / phone_h * scrcpy_win_h
```

Phone resolution is read from `ADBAdapter.d.info` (`displayWidth`, `displayHeight`) at startup and passed to `VisualMonitor`.

---

## Agent Overlays

| Agent | Method called | Visual | Color | Cleared by |
|---|---|---|---|---|
| Observer | `on_observer(widgets)` | Bounding boxes for all widgets | Blue | next `on_observer` call |
| Decider | `on_decider(target_widget)` | Single filled box on target | Yellow | next `on_observer` call |
| Executor | `on_executor(x, y)` | Ripple circle at touch point | Red | fades over 1s via QTimer |

Each call to `on_observer` clears all previous boxes + target highlight (new cycle = fresh state).

---

## Integration Points

### runner.py (predefined + autonomous)

```python
# At startup, after device_adapter.connect()
monitor = VisualMonitor(
    device_w=device_adapter.d.info["displayWidth"],
    device_h=device_adapter.d.info["displayHeight"],
)
monitor.start()

# At shutdown, after recorder.finalize_run_metrics()
monitor.stop()
```

### Agent integration (via constructor injection)

`VisualMonitor` is passed to each agent (like `memory` and `logger`). Each agent calls the relevant method at the end of its main method:

- `ObserverAgent.analyze()` → `monitor.on_observer(state["widgets"])` at end
- `DeciderAgent.decide()` → `monitor.on_decider(target_widget)` at end
- `ExecutorAgent.execute()` → `monitor.on_executor(target_x, target_y)` at end (only for click/long_click/input actions)

`monitor` is optional — agents guard calls with `if self.monitor is not None`.

---

## New Files

| File | Purpose |
|---|---|
| `visual/__init__.py` | Package init |
| `visual/monitor.py` | `VisualMonitor` class — scrcpy subprocess + overlay controller |
| `visual/overlay_window.py` | PyQt5 transparent overlay window + drawing logic |

## Modified Files

| File | Change |
|---|---|
| `core/workflow/predefined/runner.py` | Instantiate VisualMonitor, call start/stop |
| `core/workflow/autonomous/runner.py` | Same as above |
| `agents/observer_agent.py` | Accept `monitor` kwarg, call `monitor.on_observer()` |
| `agents/decider_agent.py` | Accept `monitor` kwarg, call `monitor.on_decider()` |
| `agents/executor_agent.py` | Accept `monitor` kwarg, call `monitor.on_executor()` |
| `requirements.txt` | Add `PyQt5`, `pywin32` |

---

## Dependencies

- `PyQt5` — transparent overlay window (true per-pixel alpha on Windows)
- `pywin32` — `win32gui` for scrcpy window tracking
- `scrcpy` — must be installed and available on system PATH

---

## Startup Sequence

1. `runner.py` calls `monitor.start()`
2. `VisualMonitor` spawns `scrcpy` subprocess (with `--window-title scrcpy`)
3. Waits up to 5s for the scrcpy window to appear (`win32gui.FindWindow` poll)
4. Launches `OverlayWindow` in a background Qt thread, sized + positioned over scrcpy
5. Starts WindowTracker daemon thread
6. Returns — graph execution begins

## Shutdown Sequence

1. Graph finishes, `runner.py` calls `monitor.stop()`
2. WindowTracker thread is signalled to stop
3. `OverlayWindow` is closed via Qt signal
4. scrcpy subprocess is terminated (`process.terminate()`)

---

## Edge Cases

- **scrcpy not found on PATH**: `VisualMonitor.start()` catches `FileNotFoundError`, prints a warning, and continues without the monitor (graceful degradation — test still runs)
- **scrcpy window never appears** (5s timeout): same graceful degradation
- **Monitor is None**: all agents guard with `if self.monitor is not None` — safe to omit
- **Executor action is not a touch** (scroll, press_back, start_app): `on_executor` is not called for those — no spurious ripple shown
