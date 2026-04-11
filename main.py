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


def run_workflow():
    print("[*] Starting Multi-Agent System...")

    # 1. Initialize Adapters (Infrastructure)
    device_adapter = ADBAdapter(config.TARGET_DEVICE).connect()
    llm_adapter = LangChainAdapter()

    # 2. Initialize Tools (Domain Services)
    obs_tools = ObserverTools(device_adapter, config.OUTPUT_DIR)
    exe_tools = ExecutorTools(device_adapter)

    # 3. Initialize Agents (Business Logic)
    observer = ObserverAgent(llm_adapter, obs_tools.get_tools())
    decider = DeciderAgent(llm_adapter)
    executor = ExecutorAgent(exe_tools)

    # 4. Orchestration (Workflow)
    app = build_graph(observer, decider, executor)

    initial_state: AgentState = {
        "task_goal": "Search for 'Kabel Data Type C'. Click the top result to open the product page, and click the 'Masukkan Keranjang' (Add to Cart) button.",
        "current_step": 0,
        "screenshot_path": "",
        "annotated_screenshot_path": "",
        "ocr_result": "",
        "detected_elements": "",
        "ui_elements_summary": "",
        "observer_analysis": "",
        "action_plan": {},
        "execution_result": "",
        "is_completed": False,
        "action_history": [],
    }

    config_run = {"recursion_limit": 50}

    # Execute Graph
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