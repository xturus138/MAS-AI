import os
import datetime
import time

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
from memory.meta_manager import MIRIXMemorySystem
from core.utils.process_logger import ProcessLogger
from core.workflow.autonomous.orchestrator import AutonomousOrchestrator
from core.workflow.autonomous.graph import build_autonomous_graph


def run_autonomous():
    """
    Entry point for the Autonomous (Goal-Based) workflow.

    Fair Experiment:
    Fetches the Figma Gold Standard context before starting so Autonomous mode
    has the same visual goal reference as Predefined mode. The only difference
    is the Orchestrator's internal decision logic.

    Flow per scenario:
      1. MIRIXMemorySystem init  →  2. Figma discovery  →  3. memory.init_session()
      4. Build graph  →  5. Run graph loop  →  6. finalize_run_metrics()
    """
    print("[*] Starting AUTONOMOUS Workflow...")

    # ── Infrastructure (Once per run) ─────────────────────────────────────────
    figma_adapter = build_figma_adapter_from_prompt(access_token=config.FIGMA_ACCESS_TOKEN)
    device_adapter = ADBAdapter(config.TARGET_DEVICE).connect()
    obs_tools = ObserverTools(device_adapter)
    exe_tools = ExecutorTools(device_adapter)

    # ── Load Scenarios ────────────────────────────────────────────────────────
    xlsx_path = os.path.join(os.getcwd(), "scenario.xlsx")
    if not os.path.exists(xlsx_path):
        print(f"[-] Excel file not found at {xlsx_path}.")
        return

    scenarios = load_scenarios(xlsx_path)
    if not scenarios:
        print("[-] No valid scenarios extracted.")
        return

    # ── Execute Each Scenario ─────────────────────────────────────────────────
    for scenario_index, target_scenario in enumerate(scenarios):
        tcs_id = target_scenario["tcs_id"]
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = f"{tcs_id}_{timestamp}"
        print(f"\n[+] Executing Scenario {scenario_index + 1}/{len(scenarios)}: {tcs_id} | Session: {session_id}")

        output_dir = os.path.join(config.OUTPUT_DIR, "autonomous", f"{tcs_id}_{timestamp}")
        os.makedirs(output_dir, exist_ok=True)

        # ── MIRIX Memory System (one per scenario) ────────────────────────────
        memory = MIRIXMemorySystem(session_id=session_id, output_dir=output_dir)

        # ── Process Logger (one per scenario) ────────────────────────────────
        logger = ProcessLogger(output_dir)
        logger.log("RUNNER", f"Scenario {scenario_index + 1}/{len(scenarios)} started",
                   f"tcs_id={tcs_id}  session_id={session_id}\n"
                   f"mode=autonomous  output_dir={output_dir}")

        # ── LLMs ──────────────────────────────────────────────────────────────
        perception_llm   = LLMFactory.create("observer",     session_id=session_id)
        strategic_llm    = LLMFactory.create("decider",      session_id=session_id)
        reflector_llm    = LLMFactory.create("reflector",    session_id=session_id)
        orchestrator_llm = LLMFactory.create("orchestrator", session_id=session_id)

        # ── Agents (all receive the shared memory + logger instances) ─────────
        orchestrator = AutonomousOrchestrator(
            llm=orchestrator_llm, figma_adapter=figma_adapter, memory=memory, logger=logger
        )
        observer  = ObserverAgent(perception_llm, obs_tools.get_tools(), memory=memory, logger=logger)
        decider   = DeciderAgent(strategic_llm, memory=memory, logger=logger)
        executor  = ExecutorAgent(exe_tools, memory=memory, logger=logger)
        reflector = ReflectorAgent(reflector_llm, memory=memory, logger=logger)
        recorder  = RecorderAgent(memory=memory, logger=logger)

        # ── Fair Experiment: Figma Gold Standard discovery ────────────────────
        logger.log("RUNNER", "Starting Figma pre-scenario discovery")
        figma_context = orchestrator.pre_scenario_discovery(
            scenario=target_scenario,
            output_dir=output_dir,
        )
        logger.log("RUNNER", "Figma discovery complete",
                   f"figma_enabled={figma_context.get('figma_enabled', False)}\n"
                   f"start_node={figma_context.get('figma_start_node_id', '')}\n"
                   f"end_node={figma_context.get('figma_end_node_id', '')}")

        # ── Bootstrap MIRIX Memory from scenario + figma context ──────────────
        # In autonomous mode, task_goal = scenario_desc (no sub_steps in core memory
        # for the orchestrator to treat them as mandatory sequence steps).
        autonomous_scenario = dict(target_scenario)
        autonomous_scenario["task_goal"] = target_scenario.get("scenario_desc", "")

        memory.init_session(
            scenario=autonomous_scenario,
            tcs_id=tcs_id,
            figma_context=figma_context,
        )

        # ── Build Graph ───────────────────────────────────────────────────────
        app = build_autonomous_graph(observer, decider, executor, reflector, orchestrator)

        # ── Initial AgentState (slim working-memory only) ─────────────────────
        initial_state: AgentState = {
            # Control
            "tcs_id":                   tcs_id,
            "session_id":               session_id,
            "sender":                   "START",
            "next_agent":               "OBSERVE",
            "current_step":             0,
            "is_completed":             False,
            # Current-step working memory
            "screenshot_path":          "",
            "output_dir":               output_dir,
            "step_dir":                 "",
            "action_plan":              {},
            "execution_result":         "",
            "last_reflector_passed":    False,
            # Observer output
            "observer_analysis":        "",
            "observer_analysis_step":   -1,
            "widgets":                  [],
            # MIRIX
            "memory_context":           "",
            # Orchestrator control
            "current_sub_step_index":   0,
            "orchestrator_instruction": "",
            "is_final_step":            False,
            "is_first_verify_attempt":  True,
            "step_retry_count":         0,
            # Stagnation / recovery
            "stagnation_count":         0,
            "recovery_attempts":        0,
            "last_agent_calls":         [],
            # Research metrics
            "start_time":               0.0,
            "end_time":                 0.0,
            "steps_completed_count":    0,
            "total_reflector_calls":    0,
            "reflector_pass_count":     0,
            "total_first_verify_calls": 0,
            "reflector_first_pass_count": 0,
            "widget_lookup_success":    0,
            "widget_lookup_fail":       0,
        }

        config_run = {"recursion_limit": 300}
        initial_state["start_time"] = time.time()

        logger.log("RUNNER", "Graph execution started", f"recursion_limit={config_run['recursion_limit']}")
        final_state = app.invoke(initial_state, config=config_run)
        final_state["end_time"] = time.time()

        stagnation = final_state.get("stagnation_count", 0)
        is_completed = final_state.get("is_completed", False)
        status = "SUCCESS" if is_completed else ("STAGNATED" if stagnation >= 3 else "FAILED")
        logger.log("RUNNER", "Graph execution completed",
                   f"status={status}  cycles={final_state.get('current_step', 0)}\n"
                   f"stagnation={stagnation}  is_completed={is_completed}")

        # ── Finalize: write metrics + episodic history to disk ────────────────
        recorder.finalize_run_metrics(final_state)
        memory.close()

        print("\n=== SCENARIO SUMMARY ===")
        print(f"TCS ID : {final_state['tcs_id']}")
        print(f"Status : {'Stagnated' if final_state.get('stagnation_count', 0) > 3 else 'Finished'}")
        print(f"Steps  : {final_state.get('current_step', 0)}")
        print(f"Results: {output_dir}")
