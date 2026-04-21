import os

from shared import config
from core.models.state import AgentState
from core.workflow.graph import build_graph
from adapters.device.adb_adapter import ADBAdapter
from core.utils.llm_factory import LLMFactory
from tools.observer_tools import ObserverTools
from tools.executor_tools import ExecutorTools
from agents.observer_agent import ObserverAgent
from agents.decider_agent import DeciderAgent
from agents.executor_agent import ExecutorAgent
from agents.supervisor_agent import SupervisorAgent


def run_workflow():
    print("[*] Starting Multi-Agent Swarm System...")

    import datetime
    session_id = f"run_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    device_adapter = ADBAdapter(config.TARGET_DEVICE).connect()

    perception_llm = LLMFactory.create("perception", session_id=session_id)
    strategic_llm  = LLMFactory.create("strategic",  session_id=session_id)

    obs_tools = ObserverTools(device_adapter, config.OUTPUT_DIR)
    exe_tools = ExecutorTools(device_adapter)

    observer     = ObserverAgent(perception_llm, obs_tools.get_tools())
    decider      = DeciderAgent(strategic_llm)
    executor     = ExecutorAgent(exe_tools)
    supervisor   = SupervisorAgent(strategic_llm)

    app = build_graph(observer, decider, executor, supervisor)

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
        "sender": "START", 
        "stagnation_count": 0,
        "previous_ui_summary": "",
    }

    config_run = {"recursion_limit": 100}

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