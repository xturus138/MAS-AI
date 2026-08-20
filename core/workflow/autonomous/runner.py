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
from visual.monitor import VisualMonitor
from core.utils.output_writer import write_run_overview, write_run_index as _write_run_index
from core.utils.output_manager import create_run_output, write_latest_index, compute_run_root


def run_autonomous(xlsx_path: str = "", figma_url: str | None = None):
    """
    Entry point for the Autonomous (Goal-Based) workflow.

    Parameters
    ----------
    xlsx_path:
        Absolute (or CWD-relative) path to the scenario.xlsx to run.
        Required; no scenario workbook is discovered from the current working
        directory.
    figma_url:
        Figma file URL for visual validation.  Overrides ``FIGMA_URL_QA``
        from .env when provided.

    Fair Experiment:
    Fetches the Figma Gold Standard context before starting so Autonomous mode
    has the same visual goal reference as Predefined mode. The only difference
    is the Orchestrator's internal decision logic.

    Flow per scenario:
      1. MIRIXMemorySystem init  →  2. Figma discovery  →  3. memory.init_session()
      4. Build graph  →  5. Run graph loop  →  6. finalize_run_metrics()
    """
    print("[*] Starting AUTONOMOUS Workflow...")

    if not xlsx_path:
        print("[-] Explicit scenario workbook path is required.")
        return
    if not os.path.exists(xlsx_path):
        print(f"[-] scenario.xlsx not found at: {xlsx_path}")
        return

    run_root, date_str, run_number = compute_run_root("autonomous")
    all_run_metrics = []
    os.makedirs(run_root, exist_ok=True)
    print(f"[*] Run root: {run_root}")

    figma_adapter = build_figma_adapter_from_prompt(
        access_token=config.FIGMA_ACCESS_TOKEN, figma_url=figma_url or None
    )
    device_adapter = ADBAdapter(config.TARGET_DEVICE).connect()
    obs_tools = ObserverTools(device_adapter)
    exe_tools = ExecutorTools(device_adapter)
    device_info = device_adapter.d.info
    monitor = VisualMonitor(
        device_w=device_info.get("displayWidth", 1080),
        device_h=device_info.get("displayHeight", 2400),
    )
    monitor.start()

    scenarios = load_scenarios(xlsx_path)
    if not scenarios:
        print("[-] No valid scenarios extracted.")
        return

    try:
        for scenario_index, target_scenario in enumerate(scenarios):
            tcs_id = target_scenario["tcs_id"]
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            session_id = f"{tcs_id}_{timestamp}"
            print(f"\n[+] Executing Scenario {scenario_index + 1}/{len(scenarios)}: {tcs_id} | Session: {session_id}")

            paths = create_run_output(mode="autonomous", tcs_id=tcs_id, timestamp=timestamp,
                                      run_root=run_root, scenario_index=scenario_index)
            output_dir = paths.run_dir
            write_latest_index(paths)

            memory = MIRIXMemorySystem(session_id=session_id, output_dir=output_dir)

            logger = ProcessLogger(output_dir)
            logger.log("RUNNER", f"Scenario {scenario_index + 1}/{len(scenarios)} started",
                       f"tcs_id={tcs_id}  session_id={session_id}\n"
                       f"mode=autonomous  output_dir={output_dir}")

            perception_llm   = LLMFactory.create("observer",     session_id=session_id, log_dir=paths.llm_logs_dir)
            strategic_llm    = LLMFactory.create("decider",      session_id=session_id, log_dir=paths.llm_logs_dir)
            reflector_llm    = LLMFactory.create("reflector",    session_id=session_id, log_dir=paths.llm_logs_dir)
            orchestrator_llm = LLMFactory.create("orchestrator", session_id=session_id, log_dir=paths.llm_logs_dir)

            orchestrator = AutonomousOrchestrator(
                llm=orchestrator_llm, figma_adapter=figma_adapter, memory=memory, logger=logger
            )
            observer  = ObserverAgent(perception_llm, obs_tools.get_tools(), memory=memory, logger=logger, monitor=monitor)
            decider   = DeciderAgent(strategic_llm, memory=memory, logger=logger, monitor=monitor)
            executor  = ExecutorAgent(exe_tools, memory=memory, logger=logger, monitor=monitor)
            reflector = ReflectorAgent(reflector_llm, memory=memory, logger=logger, device=device_adapter)
            recorder  = RecorderAgent(memory=memory, logger=logger)

            logger.log("RUNNER", "Starting Figma pre-scenario discovery")
            figma_context = orchestrator.pre_scenario_discovery(
                scenario=target_scenario,
                output_dir=output_dir,
            )
            logger.log("RUNNER", "Figma discovery complete",
                       f"figma_enabled={figma_context.get('figma_enabled', False)}\n"
                       f"start_node={figma_context.get('figma_start_node_id', '')}\n"
                       f"end_node={figma_context.get('figma_end_node_id', '')}")

            autonomous_scenario = dict(target_scenario)
            autonomous_scenario["task_goal"] = target_scenario.get("scenario_desc", "")

            memory.init_session(
                scenario=autonomous_scenario,
                tcs_id=tcs_id,
                figma_context=figma_context,
            )

            app = build_autonomous_graph(observer, decider, executor, reflector, orchestrator)

            initial_state: AgentState = {
                "tcs_id":                   tcs_id,
                "session_id":               session_id,
                "sender":                   "START",
                "next_agent":               "OBSERVE",
                "current_step":             0,
                "is_completed":             False,
                "screenshot_path":          "",
                "output_dir":               output_dir,
                "step_dir":                 "",
                "output_paths":             paths.as_dict(),
                "steps_dir":                paths.steps_dir,
                "logs_dir":                 paths.logs_dir,
                "llm_logs_dir":             paths.llm_logs_dir,
                "reports_dir":              paths.reports_dir,
                "figma_dir":                paths.figma_dir,
                "action_plan":              {},
                "execution_result":         "",
                "last_reflector_passed":    False,
                "observer_analysis":        "",
                "observer_analysis_step":   -1,
                "widgets":                  [],
                "memory_context":           "",
                "current_sub_step_index":   0,
                "orchestrator_instruction": "",
                "is_final_step":            False,
                "is_first_verify_attempt":  True,
                "step_retry_count":         0,
                "stagnation_count":         0,
                "recovery_attempts":        0,
                "last_agent_calls":         [],
                "start_time":               0.0,
                "end_time":                 0.0,
                "steps_completed_count":    0,
                "total_reflector_calls":    0,
                "reflector_pass_count":     0,
                "total_first_verify_calls": 0,
                "reflector_first_pass_count": 0,
                "widget_lookup_success":    0,
                "widget_lookup_fail":       0,
                "widget_text_fallback_count": 0,
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

            metrics = recorder.finalize_run_metrics(
                final_state,
                shared_dir=run_root,
                source_workbook=xlsx_path,
            )
            if metrics:
                all_run_metrics.append(metrics)

            if metrics:
                steps_data = []
                if memory is not None:
                    episodes = memory.episodic.all_as_dicts()
                    ref_eps = [ep for ep in episodes if ep.get("actor") == "reflector"]
                    for ep in ref_eps:
                        summary_text = ep.get("summary", "")
                        verdict_str = "PASSED" if "PASSED" in summary_text else "FAILED"
                        steps_data.append({
                            "step_number": ep.get("step", "?"),
                            "instruction": summary_text[:60],
                            "action_type": "",
                            "verdict": verdict_str,
                        })
                write_run_overview(
                    output_dir=output_dir,
                    tcs_id=tcs_id,
                    status=status,
                    mode="autonomous",
                    steps_completed=final_state.get("steps_completed_count", 0),
                    total_steps=final_state.get("current_step", 0),
                    duration_seconds=metrics.get("total_duration_seconds", 0),
                    physical_actions=metrics.get("physical_actions", 0),
                    figma_enabled=figma_context.get("figma_enabled", False),
                    tokens=metrics.get("total_tokens_estimate", 0),
                    cost_usd=metrics.get("total_price_usd", 0.0),
                    reflector_judgment=metrics.get("justification", {}).get("reflector_final_judgment", ""),
                    steps_data=steps_data,
                )

            memory.close()

            print("\n=== SCENARIO SUMMARY ===")
            print(f"TCS ID : {final_state['tcs_id']}")
            print(f"Status : {'Stagnated' if final_state.get('stagnation_count', 0) > 3 else 'Finished'}")
            print(f"Steps  : {final_state.get('current_step', 0)}")
            print(f"Results: {output_dir}")

        RecorderAgent.write_run_summary(all_run_metrics, run_root)

        _write_run_index(run_root, all_run_metrics)
        mode_root = os.path.join(config.OUTPUT_DIR, "runs", "autonomous")
        _write_run_index(mode_root, all_run_metrics)

    finally:
        monitor.stop()
