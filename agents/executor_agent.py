import json
import os
import time
from langgraph.types import Command
from core.models.state import AgentState
from tools.executor_tools import ExecutorTools


class ExecutorAgent:
    def __init__(self, tools: ExecutorTools, memory=None, logger=None):
        self.tools = tools
        self.memory = memory
        self.logger = logger

    def _log(self, msg: str, detail: str = ""):
        if self.logger is not None:
            self.logger.log("EXECUTOR", msg, detail)

    def execute(self, state: AgentState) -> Command:
        plan = state["action_plan"]
        action_type = plan["action_type"]
        current_step = state.get("current_step", 0)

        target_x, target_y = -1, -1
        lookup_error = None
        widgets = state.get("widgets", [])

        widget_lookup_success = state.get("widget_lookup_success", 0)
        widget_lookup_fail = state.get("widget_lookup_fail", 0)

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

        # ScenGen pattern: explicit delay for UI rendering (e.g. Activity transitions)
        time.sleep(3)

        # ScenGen pattern: explicit State Transition Management
        current_screenshot = state.get("screenshot_path", "")
        step_dir = state.get("step_dir", "outputs")
        post_action_path = os.path.join(step_dir, "post_action.png")

        try:
            self.tools.d.screenshot(post_action_path)
            new_screenshot = post_action_path
            self._log("Post-action screenshot captured", post_action_path)
        except Exception as e:
            print(f"[Executor] Failed to capture post-action UI state: {e}")
            self._log("Post-action screenshot FAILED", str(e))
            new_screenshot = current_screenshot

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
                "resource": {
                    "title": f"post_action_step_{current_step}",
                    "summary": f"Post-action screenshot after {action_type}",
                    "resource_type": "screenshot",
                    "path": new_screenshot,
                    "step": current_step,
                },
            })

        if self.logger is not None:
            self.logger.separator()

        return {
            "execution_result": result,
            "screenshot_path": new_screenshot,
            "sender": "executor",
            "widget_lookup_success": widget_lookup_success,
            "widget_lookup_fail": widget_lookup_fail,
        }
