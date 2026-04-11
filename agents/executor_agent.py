from core.models.state import AgentState
from tools.executor_tools import ExecutorTools


class ExecutorAgent:
    def __init__(self, tools: ExecutorTools):
        self.tools = tools

    def execute(self, state: AgentState) -> dict:
        plan = state["action_plan"]
        action_type = plan["action_type"]

        try:
            if action_type == "click":
                result = self.tools.click_coordinates(plan["target_x"], plan["target_y"])
            elif action_type == "long_click":
                result = self.tools.long_click(plan["target_x"], plan["target_y"])
            elif action_type == "input":
                self.tools.click_coordinates(plan["target_x"], plan["target_y"])
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

        new_history = state["action_history"] + [
            f"Step {state['current_step']}: [{action_type}] {plan['intent']} -> {result}"
        ]

        return {
            "execution_result": result,
            "action_history": new_history,
        }