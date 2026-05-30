import time
from typing import Optional
from langgraph.types import Command
from core.models.state import AgentState
from tools.executor_tools import ExecutorTools


class ExecutorAgent:
    def __init__(self, tools: ExecutorTools, memory=None, logger=None, monitor=None, check_crash: bool = False):
        self.tools = tools
        self.memory = memory
        self.logger = logger
        self.monitor = monitor
        self._check_crash = check_crash

    def _log(self, msg: str, detail: str = ""):
        if self.logger is not None:
            self.logger.log("EXECUTOR", msg, detail)

    # ── Text-Match Fallback ───────────────────────────────────────────────────
    def _text_match_fallback(self, widgets: list, plan: dict) -> Optional[dict]:
        """Find a widget by keyword match when target_id lookup fails.

        Extracts tokens (>3 chars) from intent + text_payload, then scores
        each widget by how many keywords appear in its text field.
        Returns the highest-scoring widget, or None if no match.
        """
        raw = (plan.get("intent") or "") + " " + (plan.get("text_payload") or "")
        keywords = [w.lower() for w in raw.split() if len(w) > 3]
        if not keywords:
            return None

        best: Optional[dict] = None
        best_score = 0
        for widget in widgets:
            widget_text = (widget.get("text") or "").lower()
            if not widget_text:
                continue
            score = sum(1 for kw in keywords if kw in widget_text)
            if score > best_score:
                best_score = score
                best = widget

        return best if best_score > 0 else None

    def execute(self, state: AgentState) -> Command:
        plan = state["action_plan"]
        action_type = plan["action_type"]
        current_step = state.get("current_step", 0)

        target_x, target_y = -1, -1
        lookup_error = None
        widgets = state.get("widgets", [])

        widget_lookup_success = state.get("widget_lookup_success", 0)
        widget_lookup_fail    = state.get("widget_lookup_fail", 0)
        widget_text_fallback  = state.get("widget_text_fallback_count", 0)

        self._log(
            f"Step {current_step} — Executing: {action_type}",
            f"intent={plan.get('intent', '')}\n"
            f"target_id={plan.get('target_id', -1)}\n"
            f"text_payload={plan.get('text_payload', '')!r}\n"
            f"scroll_direction={plan.get('scroll_direction', '')!r}"
        )

        if plan.get("is_completed"):
            result = "No Action Required (Step already satisfied)"
            print(f"[Executor] {result}")
            self._log("No action — step already satisfied")
            if self.memory is not None:
                self.memory.update({
                    "episodic": {
                        "event_type": "execution",
                        "summary": "No action required — step already satisfied",
                        "details": result,
                        "actor": "executor",
                        "step": current_step,
                    }
                })
            if self.logger is not None:
                self.logger.separator()
            return {
                "execution_result": result,
                "sender": "executor",
                "widget_lookup_success": widget_lookup_success,
                "widget_lookup_fail": widget_lookup_fail,
                "widget_text_fallback_count": widget_text_fallback,
            }

        if action_type in ["click", "long_click", "input"]:
            target_id = plan.get("target_id", -1)
            target_widget = next((w for w in widgets if w.get("id") == target_id), None)

            if target_widget:
                bounds = target_widget.get("bounds", [0, 0, 0, 0])
                target_x = (bounds[0] + bounds[2]) // 2
                target_y = (bounds[1] + bounds[3]) // 2
                widget_text = target_widget.get("text", "(no text)")
                print(f"[Executor] Resolved ID {target_id} -> click=({target_x},{target_y}) | widget='{widget_text}'")
                self._log(
                    f"Widget resolved: ID {target_id} → ({target_x},{target_y})",
                    f"text='{widget_text}'  bounds={bounds}"
                )
                widget_lookup_success += 1
            else:
                # ── Text-match fallback: try keyword match before declaring failure ──
                fallback_widget = self._text_match_fallback(widgets, plan)
                if fallback_widget:
                    bounds = fallback_widget.get("bounds", [0, 0, 0, 0])
                    target_x = (bounds[0] + bounds[2]) // 2
                    target_y = (bounds[1] + bounds[3]) // 2
                    widget_text = fallback_widget.get("text", "(no text)")
                    print(f"[Executor] [FALLBACK] ID {target_id} not found — text-match → widget='{widget_text}' ({target_x},{target_y})")
                    self._log(
                        f"Widget text-match fallback: ID {target_id} → '{widget_text}' ({target_x},{target_y})",
                        f"bounds={bounds}"
                    )
                    widget_text_fallback += 1
                    widget_lookup_success += 1
                else:
                    lookup_error = f"ERROR: Target ID {target_id} not found in current UI state"
                    self._log(f"Widget lookup FAILED: ID {target_id} not found in {len(widgets)} widgets")
                    widget_lookup_fail += 1

        try:
            if lookup_error:
                result = lookup_error
            elif action_type == "click":
                result = self.tools.click_coordinates(target_x, target_y)
            elif action_type == "long_click":
                result = self.tools.long_click(target_x, target_y)
            elif action_type == "input":
                self.tools.click_coordinates(target_x, target_y)
                result = self.tools.type_text(plan["text_payload"])
            elif action_type == "scroll":
                result = self.tools.swipe_screen(plan["scroll_direction"])
            elif action_type == "press_back":
                result = self.tools.press_back()
            elif action_type == "press_home":
                result = self.tools.press_home()
            elif action_type == "press_enter":
                result = self.tools.press_enter()
            elif action_type == "start_app":
                result = self.tools.start_app(plan["app_package"])
            else:
                result = f"ERROR: Unknown action_type '{action_type}'"
        except Exception as e:
            result = f"ERROR (Execution Failed): {str(e)}"

        print(f"[Executor] [{action_type}] {plan['intent']} -> {result}")
        is_error = str(result).startswith("ERROR")
        self._log(
            f"ADB result: {'FAIL' if is_error else 'OK'}",
            str(result)
        )

        if self.monitor is not None and action_type in ("click", "long_click", "input") and target_x != -1:
            self.monitor.on_executor(target_x, target_y)

        # Brief pause so the UI can start rendering before the next screenshot
        time.sleep(1)

        # Clear overlay annotations — the screen has changed, old boxes no longer apply.
        if self.monitor is not None:
            self.monitor.on_clear()

        # ── ADB crash detection (opt-in; skipped by default for QA speed) ─────
        if self._check_crash and not is_error:
            crash_line = self.tools.check_crash(lines=50)
            if crash_line:
                result = f"[CRASH] {crash_line} | original: {result}"
                print(f"[Executor] ⚠️  CRASH DETECTED: {crash_line}")
                self._log("CRASH detected in logcat", crash_line)

        # Recompute after potential crash mutation
        is_error = str(result).startswith("ERROR") or str(result).startswith("[CRASH]")

        # ── Memory Update ─────────────────────────────────────────────────────
        if self.memory is not None:
            self.memory.update({
                "episodic": {
                    "event_type": "execution",
                    "summary": f"[{'FAIL' if is_error else 'OK'}] {action_type}: {plan.get('intent', '')}",
                    "details": result,
                    "actor": "executor",
                    "step": current_step,
                },
            })

        if self.logger is not None:
            self.logger.separator()

        return {
            "execution_result": result,
            "sender": "executor",
            "widget_lookup_success": widget_lookup_success,
            "widget_lookup_fail": widget_lookup_fail,
            "widget_text_fallback_count": widget_text_fallback,
        }
