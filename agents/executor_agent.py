from langchain_core.messages import SystemMessage, HumanMessage
from core.state import AgentState

class ExecutorAgent:
    def __init__(self, llm, tools):
        self.llm_with_tools = llm.bind_tools(tools)
        self.tools_map = {tool.name: tool for tool in tools}

    def execute(self, state: AgentState) -> dict:
        system_prompt = SystemMessage(
            content=(
                "You are an Android executor robot. Your task is to execute the Decider's instruction on the device.\n\n"
                "GUIDELINES:\n"
                "1. Map labels, resource IDs, or descriptions from the Decider to the exact '@x,y' coordinates found in the Screen Data.\n"
                "2. Use 'swipe_screen' if the instruction involves scrolling, paging, or finding elements not currently visible.\n"
                "3. Use 'click_coordinates' for standard button/link interactions using its center point.\n"
                "4. Use 'start_app' if the Decider wants to open a specific application and you are not currently in it.\n"
                "5. If a form needs to be submitted after typing, use 'press_enter'.\n"
                "6. Only use tools provided to you. Do not guess or hallucinate parameters."
            )
        )
        human_prompt = HumanMessage(
            content=f"Instruction from Decider: {state['decider_instruction']}\n\n"
                    f"Screen Data (Summarized): \n{state['ui_elements_summary']}"
        )

        response = self.llm_with_tools.invoke([system_prompt, human_prompt])

        execution_logs = []
        if response.tool_calls:
            for tool_call in response.tool_calls:
                try:
                    tool_name = tool_call["name"]
                    if tool_name in self.tools_map:
                        selected_tool = self.tools_map[tool_name]
                        tool_output = selected_tool.invoke(tool_call["args"])
                        execution_logs.append(f"[{tool_name}]: {tool_output}")
                    else:
                        execution_logs.append(f"Error: Tool '{tool_name}' not found.")
                except Exception as e:
                    execution_logs.append(f"Error executing {tool_call['name']}: {str(e)}")
        else:
            execution_logs.append("Executor: No tool was called. Instruction might be unclear or already completed.")

        result_str = " | ".join(execution_logs)
        print(f"[Executor] {result_str}")

        new_history = state["action_history"] + [
            f"Step {state['current_step']}: {state['decider_instruction']} → {result_str}"
        ]
        return {
            "execution_result": result_str,
            "action_history": new_history,
        }