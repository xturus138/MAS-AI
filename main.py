import config
from core.llm_client import get_shared_llm
from core.state import AgentState
from core.graph import build_graph
from core.device_connection import DeviceConnection
from tools.observer_tools import ObserverTools
from tools.executor_tools import ExecutorTools
from agents.observer_agent import ObserverAgent
from agents.decider_agent import DeciderAgent
from agents.executor_agent import ExecutorAgent


def run_workflow():
    print("[*] Starting Multi-Agent System (LangGraph)...")

    device_session = DeviceConnection(config.TARGET_DEVICE).connect()
    shared_llm = get_shared_llm()

    obs_tools = ObserverTools(device_session, config.OUTPUT_DIR)
    exe_tools = ExecutorTools(device_session)

    observer = ObserverAgent(shared_llm, obs_tools.get_tools())
    decider = DeciderAgent(shared_llm)
    executor = ExecutorAgent(exe_tools)

    app = build_graph(observer, decider, executor)

    initial_state: AgentState = {
        "task_goal": "Open Shopee, go to profile, and change the name into 'Raditya138'",
        "current_step": 0,
        "screenshot_path": "",
        "ui_elements_summary": "",
        "observer_analysis": "",
        "action_plan": {},
        "execution_result": "",
        "is_completed": False,
        "action_history": [],
    }

    config_run = {"recursion_limit": 50}

    final_state = app.invoke(initial_state, config=config_run)

    print("\n=== FINAL SUMMARY ===")
    status = "Success" if final_state["is_completed"] else "Stopped (Recursion Limit)"
    print(f"Status : {status}")
    print(f"Steps  : {final_state['current_step']}")
    print("Action History:")
    for entry in final_state["action_history"]:
        print(f"  - {entry}")


if __name__ == "__main__":
    run_workflow()