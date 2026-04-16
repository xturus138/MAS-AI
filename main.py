import os

from shared import config
from core.models.state import AgentState
from core.workflow.graph import build_graph
from adapters.device.adb_adapter import ADBAdapter
from adapters.llm.langchain_adapter import LangChainAdapter
from tools.observer_tools import ObserverTools
from tools.executor_tools import ExecutorTools
from agents.observer_agent import ObserverAgent
from agents.decider_agent import DeciderAgent
from agents.executor_agent import ExecutorAgent
from agents.orchestrator_agent import OrchestratorAgent


def run_workflow():
    print("[*] Starting Multi-Agent Swarm System...")

    # 1. Initialize Infrastructure (Adapters)
    device_adapter = ADBAdapter(config.TARGET_DEVICE).connect()
    
    # [Hybrid Setup] - Easily swap models here
    perception_llm = LangChainAdapter(
        model_name=config.PERCEPTION_MODEL, 
        base_url=config.LOCAL_LLM_URL, 
        is_local=True
    )
    strategic_llm = LangChainAdapter(
        model_name=config.STRATEGIC_MODEL,
        api_key=config.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1"
    )

    # 2. Initialize Tools
    obs_tools = ObserverTools(device_adapter, config.OUTPUT_DIR)
    exe_tools = ExecutorTools(device_adapter)

    # 3. Initialize Agents (Dependency Injection)
    observer     = ObserverAgent(perception_llm, obs_tools.get_tools())
    decider      = DeciderAgent(strategic_llm)
    executor     = ExecutorAgent(exe_tools)
    orchestrator = OrchestratorAgent(strategic_llm)

    # 4. Build the Swarm Graph
    app = build_graph(orchestrator, observer, decider, executor)

    initial_state: AgentState = {
        "task_goal": "Create a new note, write 'Meeting at 3 PM tomorrow', and save it",
        "current_step": 0,
        "screenshot_path": "",
        "annotated_screenshot_path": "",
        "ocr_result": "",
        "detected_elements": "",
        "ui_elements_summary": "",
        "observer_analysis": "",
        "widgets": [],
        "action_plan": {},
        "execution_result": "",
        "is_completed": False,
        "action_history": [],
        "current_subgoal": "",
        "orchestrator_reasoning": "",
        "sender": "START",  # Explicitly start to trigger Observer
        "stagnation_count": 0,
        "previous_ui_summary": "",
    }

    config_run = {"recursion_limit": 100}

    # Execute Graph
    final_state = app.invoke(initial_state, config=config_run)

    print("\n=== FINAL SUMMARY ===")
    status = "Success" if final_state["is_completed"] else "Stopped (Budget / Recursion Limit)"
    print(f"Status : {status}")
    print(f"Steps  : {final_state['current_step']}")
    print(f"Last Orchestrator Reasoning: {final_state.get('orchestrator_reasoning', 'N/A')}")
    print("Action History:")
    for entry in final_state["action_history"]:
        print(f"  - {entry}")


if __name__ == "__main__":
    run_workflow()