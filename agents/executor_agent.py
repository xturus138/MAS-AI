from langchain_core.messages import SystemMessage, HumanMessage
from core.state import AgentState

class ExecutorAgent:
    def __init__(self, llm, tools):
        self.llm_with_tools = llm.bind_tools(tools)
        self.tools_map = {tool.name: tool for tool in tools}

    def execute(self, state: AgentState) -> dict:
        system_prompt = SystemMessage(
            content="You are an Android executor robot. "
                    "Use the available tools to execute instructions."
        )
        human_prompt = HumanMessage(
            content=f"Instruction from Decider: {state['decider_instruction']}\n\n"
                    f"Screen data: {state['ui_elements_summary']}"
        )

        response = self.llm_with_tools.invoke([system_prompt, human_prompt])

        execution_logs = []
        if response.tool_calls:
            for tool_call in response.tool_calls:
                selected_tool = self.tools_map[tool_call["name"]]
                tool_output = selected_tool.invoke(tool_call["args"])
                execution_logs.append(tool_output)
        else:
            execution_logs.append("Executor: Could not find a suitable tool for this instruction.")

        result_str = " | ".join(execution_logs)
        print(f"[Executor] {result_str}")

        new_history = state["action_history"] + [
            f"Step {state['current_step']}: {state['decider_instruction']} → {result_str}"
        ]
        return {
            "execution_result": result_str,
            "action_history": new_history,
        }