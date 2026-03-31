from langchain_core.messages import SystemMessage, HumanMessage
from core.state import OrchestratorState

# STEP 1 LOGIKA EXECUTOR MENGGUNAKAN LANGCHAIN TOOLS BINDING //
class ExecutorAgent:
    def __init__(self, llm, tools):
        self.llm_with_tools = llm.bind_tools(tools)
        self.tools_map = {tool.name: tool for tool in tools}

    def execute(self, state: OrchestratorState) -> OrchestratorState:
        system_prompt = SystemMessage(content="Anda adalah robot eksekutor Android. Gunakan tools yang tersedia untuk menjalankan instruksi.")
        human_prompt = HumanMessage(content=f"Instruksi dari Orchestrator: {state.orchestrator_instruction}\n\nData layar: {state.ui_elements_summary}")
        
        response = self.llm_with_tools.invoke([system_prompt, human_prompt])
        
        execution_logs = []
        if response.tool_calls:
            for tool_call in response.tool_calls:
                selected_tool = self.tools_map[tool_call["name"]]
                tool_output = selected_tool.invoke(tool_call["args"])
                execution_logs.append(tool_output)
        else:
            execution_logs.append("Executor gagal menemukan tool yang tepat untuk instruksi ini.")
            
        result_str = " | ".join(execution_logs)
        state.execution_result = result_str
        state.action_history.append(f"Step {state.current_step}: {state.orchestrator_instruction} -> {result_str}")
        
        return state