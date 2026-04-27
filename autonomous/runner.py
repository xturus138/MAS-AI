import os
import datetime

from shared import config
from core.models.state import AgentState
from core.utils.llm_factory import LLMFactory
from core.utils.xlsx_loader import load_scenarios
from adapters.device.adb_adapter import ADBAdapter
from adapters.figma.figma_adapter import build_figma_adapter_from_prompt
from tools.observer_tools import ObserverTools
from tools.executor_tools import ExecutorTools
from agents.observer_agent import ObserverAgent
from agents.decider_agent import DeciderAgent
from agents.executor_agent import ExecutorAgent
from agents.reflector_agent import ReflectorAgent
from agents.recorder_agent import RecorderAgent
from autonomous.orchestrator import AutonomousOrchestrator
from autonomous.graph import build_autonomous_graph


def run_autonomous():
    """
    Entry point for the Autonomous (Goal-Based) workflow.

    Fair Experiment:
    This runner now fetches the Figma Gold Standard context before starting,
    ensuring that the Autonomous mode has the same 'visual goals' as the 
    Predefined mode. The only difference is the Orchestrator's internal logic.
    """
    print("[*] Starting AUTONOMOUS Workflow...")

    session_id = f"run_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # --- Infrastructure ---
    figma_adapter = build_figma_adapter_from_prompt(access_token=config.FIGMA_ACCESS_TOKEN)
    device_adapter = ADBAdapter(config.TARGET_DEVICE).connect()

    # --- LLMs ---
    perception_llm   = LLMFactory.create("observer",     session_id=session_id)
    strategic_llm    = LLMFactory.create("decider",      session_id=session_id)
    reflector_llm    = LLMFactory.create("reflector",    session_id=session_id)
    orchestrator_llm = LLMFactory.create("orchestrator", session_id=session_id)

    # --- Shared Agents ---
    obs_tools = ObserverTools(device_adapter)
    exe_tools = ExecutorTools(device_adapter)

    observer  = ObserverAgent(perception_llm, obs_tools.get_tools())
    decider   = DeciderAgent(strategic_llm)
    executor  = ExecutorAgent(exe_tools)
    reflector = ReflectorAgent(reflector_llm)
    recorder  = RecorderAgent()

    # --- Autonomous-specific Orchestrator (now with Figma adapter) ---
    orchestrator = AutonomousOrchestrator(llm=orchestrator_llm, figma_adapter=figma_adapter)

    # --- Build Graph ---
    app = build_autonomous_graph(observer, decider, executor, reflector, recorder, orchestrator)

    # --- Load Scenarios ---
    xlsx_path = os.path.join(os.getcwd(), "scenario.xlsx")
    if not os.path.exists(xlsx_path):
        print(f"[-] Excel file not found at {xlsx_path}.")
        return

    scenarios = load_scenarios(xlsx_path)
    if not scenarios:
        print("[-] No valid scenarios extracted.")
        return

    # --- Execute Each Scenario ---
    for scenario_index, target_scenario in enumerate(scenarios):
        tcs_id = target_scenario["tcs_id"]
        print(f"\n[+] Executing Scenario {scenario_index + 1}/{len(scenarios)}: {tcs_id} ({target_scenario['scenario_desc']})")

        timestamp  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(config.OUTPUT_DIR, f"{tcs_id}_{timestamp}")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # Fair Experiment: Fetch Figma context (Gold Standard) even in autonomous mode
        figma_context = orchestrator.pre_scenario_discovery(
            scenario=target_scenario,
            output_dir=output_dir,
        )

        # Use scenario description as the high-level task goal
        task_goal = target_scenario["scenario_desc"]

        initial_state: AgentState = {
            "tcs_id":                   tcs_id,
            "navigation_context":       target_scenario["navigation_context"],
            "scenario_desc":            target_scenario["scenario_desc"],
            "test_type":                target_scenario["test_type"],
            "user_role":                target_scenario["user_role"],
            "sub_steps":                target_scenario["sub_steps"], # Keep for parity tracing
            "task_goal":                task_goal,
            "expected_result":          target_scenario["expected_result"],
            "current_sub_step_index":   0,
            "current_step":             0,
            "screenshot_path":          "",
            "previous_screenshot_path": "",
            "annotated_screenshot_path": "",
            "ui_elements_summary":      "",
            "ocr_result":               "",
            "detected_elements":        "",
            "observer_analysis":        "",
            "widgets":                  [],
            "action_plan":              {},
            "execution_result":         "",
            "is_completed":             False,
            "action_history":           [],
            "chat_logs":                [],
            "orchestrator_reasoning":   "",
            "sender":                   "START",
            "stagnation_count":         0,
            "previous_ui_summary":      "",
            "reflector_reasoning":      "None",
            "output_dir":               output_dir,
            "step_dir":                 "",
            "step_retry_count":         0,
            "last_reflector_passed":    True,
            **figma_context,
        }

        config_run  = {"recursion_limit": 150}
        final_state = app.invoke(initial_state, config=config_run)

        print("\n=== SCENARIO SUMMARY ===")
        print(f"TCS ID : {final_state['tcs_id']}")
        print(f"Status : {'Failed' if final_state.get('stagnation_count', 0) > 3 else 'Finished'}")
        print(f"Steps  : {final_state.get('current_step', 0)}")
        print(f"Results: {output_dir}")
