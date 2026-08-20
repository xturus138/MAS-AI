"""Reliable Firebase Chat predefined-batch runner.

Pure workbook/config checks run before the read-only device probe.  Live
device, monitor, Figma, LLM, and per-case runtime construction happens only
after the complete preflight succeeds.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared import config
from core.utils.output_manager import compute_run_root
from core.utils.xlsx_loader import load_scenarios
from core.workflow.predefined.batch import (
    PredefinedBatchCoordinator,
    validate_resume_manifest,
)
from core.workflow.predefined.preflight import (
    ADBPreflightProbe,
    PreflightReport,
    validate_config,
    validate_device,
    validate_workbook,
)


@dataclass(frozen=True)
class RunnerDependencies:
    """Dependency seams used by focused fake-runner tests."""

    config_values: Mapping[str, object]
    workbook_validator: Callable[[str], PreflightReport]
    config_validator: Callable[[Mapping[str, object]], PreflightReport]
    device_probe_factory: Callable[[str], Any]
    device_validator: Callable[..., PreflightReport]
    scenario_loader: Callable[[str], list[dict[str, Any]]]
    run_root_factory: Callable[[str], tuple[str, str, int]]
    runtime_factory: Callable[..., AbstractContextManager]
    aggregate_report_writer: Callable[..., Any]


def _config_values() -> dict[str, object]:
    return {
        name: value
        for name, value in vars(config).items()
        if name.isupper()
    }


def _write_aggregate_report(*, manifest: dict, source_workbook: str, run_root: str) -> str:
    from agents.recorder_agent import RecorderAgent

    return RecorderAgent.write_batch_report(
        manifest=manifest,
        source_workbook=source_workbook,
        destination=str(Path(run_root) / "test_report.xlsx"),
    )


def _validate_workbook_for_scenario(xlsx_path: str) -> PreflightReport:
    """Enforce the strict Firebase Chat baseline only for that scenario.

    Any other scenario folder (selected via ``scenarios/<name>/scenario.xlsx``)
    only needs to satisfy generic structural checks, so predefined runs are
    not locked to the 69-case Firebase Chat baseline.
    """

    resolved = Path(xlsx_path).expanduser().resolve()
    is_firebase_chat = resolved.parent.name.lower() == "firebase_chat"
    return validate_workbook(xlsx_path, strict_firebase_chat=is_firebase_chat)


def _default_dependencies() -> RunnerDependencies:
    return RunnerDependencies(
        config_values=_config_values(),
        workbook_validator=_validate_workbook_for_scenario,
        config_validator=validate_config,
        device_probe_factory=lambda serial: ADBPreflightProbe(serial),
        device_validator=validate_device,
        scenario_loader=load_scenarios,
        run_root_factory=compute_run_root,
        runtime_factory=_default_runtime_factory,
        aggregate_report_writer=_write_aggregate_report,
    )


def _print_preflight(report: PreflightReport) -> None:
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))


def require_verified_recovery(
    *,
    initial_assessment: Mapping[str, Any],
    planned_steps: Sequence[str],
    final_assessment: Mapping[str, Any],
) -> None:
    """Fail closed when a required recovery cannot be planned or verified."""
    if not bool(initial_assessment.get("matched")) and not list(planned_steps):
        raise RuntimeError("Navigation recovery produced no operational transition plan.")
    if not bool(final_assessment.get("matched")):
        raise RuntimeError("Navigation recovery could not verify the required context.")


def require_case_reporting_artifacts(attempt_dir: str | Path) -> None:
    """Reject a case whose Recorder did not produce both required reports."""
    attempt_path = Path(attempt_dir)
    required = (
        attempt_path / "final_metrics.json",
        attempt_path / "reports" / "test_report.xlsx",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(
            "Required per-case reporting artifact is missing: " + ", ".join(missing)
        )


def derive_case_outcome(state: Mapping[str, Any], *, total_steps: int) -> dict[str, str]:
    """Derive one canonical evidence-bounded terminal outcome."""
    history = list(state.get("technical_error_history") or [])
    last_reasoning = str(state.get("last_reflector_reasoning") or "")
    execution_result = str(state.get("execution_result") or "")
    action_reasoning = str((state.get("action_plan") or {}).get("reasoning") or "")

    technical_markers = (
        "[SYSTEM_ERROR]",
        "Fatal failure in Observer",
        "ERROR (Execution Failed)",
        "ERROR: Target ID",
        "[CRASH]",
    )
    fallback_markers = (
        "LLM output parsing failed",
        "Decider LLM returned None",
    )
    if (
        history
        or any(marker in last_reasoning for marker in technical_markers)
        or any(marker in execution_result for marker in technical_markers)
        or any(marker in action_reasoning for marker in fallback_markers)
    ):
        reason = history[-1].get("reason", "") if history else (
            last_reasoning or execution_result or action_reasoning
        )
        return {
            "status": "technical_error",
            "reason": str(reason) or "Technical fallback prevented a trustworthy QA verdict.",
            "actual_observation": str(state.get("observer_analysis") or ""),
        }

    if int(state.get("stagnation_count") or 0) >= 3:
        return {
            "status": "stagnated",
            "reason": "Repeated UI observations showed no sufficient progress.",
            "actual_observation": str(state.get("observer_analysis") or ""),
        }

    if bool(state.get("retry_exhausted")):
        return {
            "status": "functional_anomaly",
            "reason": str(state.get("failure_reason") or "Expected and actual QA behavior still differed after allowed retries."),
            "actual_observation": str(state.get("observer_analysis") or ""),
        }

    completed_steps = int(state.get("steps_completed_count") or 0)
    if (
        bool(state.get("is_completed"))
        and completed_steps >= total_steps
        and bool(state.get("last_reflector_passed", False))
    ):
        return {
            "status": "success",
            "reason": "All original QA steps were verified.",
            "actual_observation": str(state.get("observer_analysis") or ""),
        }

    if state.get("last_reflector_passed") is False:
        return {
            "status": "functional_anomaly",
            "reason": last_reasoning or "Expected and actual QA behavior differed.",
            "actual_observation": str(state.get("observer_analysis") or ""),
        }

    return {
        "status": "technical_error",
        "reason": "Scenario ended without a trustworthy QA verdict.",
        "actual_observation": str(state.get("observer_analysis") or ""),
    }


def run_predefined(
    xlsx_path: str = "",
    figma_url: str | None = None,
    *,
    preflight_only: bool = False,
    resume: str | None = None,
    dependencies: RunnerDependencies | None = None,
):
    """Run or resume the predefined baseline after strict read-only preflight."""
    print("[*] Starting PREDEFINED Workflow...")
    if not xlsx_path:
        print("[-] Explicit scenario workbook path is required.")
        return None
    if not os.path.exists(xlsx_path):
        print(f"[-] scenario.xlsx not found at: {xlsx_path}")
        return None

    deps = dependencies or _default_dependencies()
    effective_config = dict(deps.config_values)
    effective_config["WORKFLOW_STRATEGY"] = "predefined"

    report = PreflightReport()
    workbook_report = deps.workbook_validator(xlsx_path)
    report.merge(workbook_report)
    report.merge(deps.config_validator(effective_config))
    if report.blocking:
        _print_preflight(report)
        return report

    scenarios = deps.scenario_loader(xlsx_path)
    if not scenarios:
        report.add(
            "workbook",
            "workbook.no_scenarios",
            "error",
            "No valid scenarios were extracted from the workbook.",
        )
        _print_preflight(report)
        return report

    fingerprint = str(
        workbook_report.metadata.get("workbook", {}).get("fingerprint")
        or scenarios[0].get("workbook_fingerprint")
        or ""
    )
    ordered_tcs_ids = [str(scenario["tcs_id"]) for scenario in scenarios]
    if resume:
        validate_resume_manifest(
            resume,
            workbook_fingerprint=fingerprint,
            ordered_tcs_ids=ordered_tcs_ids,
        )

    strict_firebase_chat = bool(
        workbook_report.metadata.get("workbook", {}).get("strict_firebase_chat", True)
    )
    target_serial = str(effective_config.get("TARGET_DEVICE") or "")
    snapshot = deps.device_probe_factory(target_serial).capture()
    report.merge(
        deps.device_validator(
            snapshot,
            expected_serial=target_serial,
            strict_firebase_chat=strict_firebase_chat,
        )
    )
    _print_preflight(report)
    if report.blocking or preflight_only:
        return report

    if resume:
        run_root = str(Path(resume).expanduser().resolve())
    else:
        run_root, _date_str, _run_number = deps.run_root_factory("predefined")
        run_root = str(Path(run_root).expanduser().resolve())

    with deps.runtime_factory(
        xlsx_path=str(Path(xlsx_path).expanduser().resolve()),
        run_root=run_root,
        figma_url=figma_url,
        config_values=effective_config,
        device_snapshot=snapshot,
    ) as case_executor:
        coordinator = PredefinedBatchCoordinator(
            scenarios=scenarios,
            source_workbook=xlsx_path,
            workbook_fingerprint=fingerprint,
            run_root=run_root,
            case_executor=case_executor,
        )
        manifest = coordinator.run()

    deps.aggregate_report_writer(
        manifest=manifest,
        source_workbook=str(Path(xlsx_path).expanduser().resolve()),
        run_root=run_root,
    )
    return manifest


class _RecoveryEpisodicView:
    def last_by_actor(self, _actor: str):
        return None


class _RecoveryMemoryView:
    """Read normal context but suppress operational events from QA history."""

    def __init__(self, memory: Any):
        self._memory = memory
        self.core = memory.core
        self.episodic = _RecoveryEpisodicView()

    def retrieve(self, *args, **kwargs):
        return self._memory.retrieve(*args, **kwargs)

    def retrieve_with_labels(self, *args, **kwargs):
        return self._memory.retrieve_with_labels(*args, **kwargs)

    def update(self, _packet: dict) -> None:
        return None


@contextmanager
def _temporary_agent_memory(agents: Sequence[Any], memory: Any):
    originals = [agent.memory for agent in agents]
    try:
        for agent in agents:
            agent.memory = memory
        yield
    finally:
        for agent, original in zip(agents, originals):
            agent.memory = original


def _agent_update(result: Any, *, phase: str) -> dict[str, Any]:
    if isinstance(result, Mapping):
        update = dict(result)
        goto = None
    else:
        update = getattr(result, "update", None)
        goto = getattr(result, "goto", None)
        if goto == "__end__" or not isinstance(update, Mapping):
            reason = (update or {}).get("execution_result", "") if isinstance(update, Mapping) else ""
            raise RuntimeError(f"{phase} failed before producing trustworthy state: {reason}")
        update = dict(update)

    history = list(update.get("technical_error_history") or [])
    execution_result = str(update.get("execution_result") or "")
    technical_markers = (
        "[SYSTEM_ERROR]",
        "Fatal failure",
        "ERROR (Execution Failed)",
        "ERROR: Target ID",
        "[CRASH]",
    )
    if history or any(marker in execution_result for marker in technical_markers):
        reason = history[-1].get("reason", "") if history else execution_result
        raise RuntimeError(f"{phase} produced technical evidence: {reason}")
    return update


def reconcile_cleanup_failure_artifacts(
    *,
    attempt_dir: str | Path,
    source_workbook: str,
    tcs_id: str,
    metrics: Mapping[str, Any],
    cleanup_error: Exception,
) -> dict[str, Any]:
    """Rewrite already-produced case artifacts to the final technical status."""
    from agents.recorder_agent import RecorderAgent

    attempt_path = Path(attempt_dir)
    reason = f"{type(cleanup_error).__name__}: {cleanup_error}"
    rewritten = dict(metrics)
    rewritten["status"] = "technical_error"
    rewritten["error_or_anomaly_reason"] = reason
    justification = dict(rewritten.get("justification") or {})
    justification["cleanup_failure"] = reason
    rewritten["justification"] = justification

    PredefinedBatchCoordinator._atomic_json_write(
        attempt_path / "final_metrics.json", rewritten
    )
    RecorderAgent().write_test_report(
        {
            "tcs_id": tcs_id,
            "output_dir": str(attempt_path),
            "reports_dir": str(attempt_path / "reports"),
        },
        rewritten,
        source_workbook=source_workbook,
    )
    return rewritten


def _initial_state(*, scenario: Mapping[str, Any], session_id: str, paths: Any) -> dict[str, Any]:
    return {
        "tcs_id": str(scenario["tcs_id"]),
        "session_id": session_id,
        "sender": "START",
        "next_agent": "",
        "current_step": 0,
        "is_completed": False,
        "screenshot_path": "",
        "output_dir": paths.run_dir,
        "step_dir": "",
        "output_paths": paths.as_dict(),
        "steps_dir": paths.steps_dir,
        "logs_dir": paths.logs_dir,
        "llm_logs_dir": paths.llm_logs_dir,
        "reports_dir": paths.reports_dir,
        "figma_dir": paths.figma_dir,
        "action_plan": {},
        "execution_result": "",
        "last_reflector_passed": True,
        "last_reflector_reasoning": "",
        "observer_analysis": "",
        "observer_analysis_step": -1,
        "widgets": [],
        "memory_context": "",
        "current_sub_step_index": 0,
        "orchestrator_instruction": "",
        "is_final_step": False,
        "is_first_verify_attempt": True,
        "step_retry_count": 0,
        "stagnation_count": 0,
        "recovery_attempts": 0,
        "last_agent_calls": [],
        "start_time": 0.0,
        "end_time": 0.0,
        "steps_completed_count": 0,
        "total_reflector_calls": 0,
        "reflector_pass_count": 0,
        "total_first_verify_calls": 0,
        "reflector_first_pass_count": 0,
        "widget_lookup_success": 0,
        "widget_lookup_fail": 0,
        "widget_text_fallback_count": 0,
        "technical_error_history": [],
        "retry_exhausted": False,
        "failure_reason": "",
        "canonical_status": "",
        "uncertainty_artifact_dir": "",
    }


class _LiveCaseExecutor:
    def __init__(self, *, device: Any, monitor: Any, figma: Any, observer_tools: Any, executor_tools: Any, source_workbook: str):
        self.device = device
        self.monitor = monitor
        self.figma = figma
        self.observer_tools = observer_tools
        self.executor_tools = executor_tools
        self.source_workbook = source_workbook

    def __call__(self, scenario: dict[str, Any], evidence_dir: Path) -> Mapping[str, Any]:
        from agents.decider_agent import DeciderAgent
        from agents.executor_agent import ExecutorAgent
        from agents.observer_agent import ObserverAgent
        from agents.recorder_agent import RecorderAgent
        from agents.reflector_agent import ReflectorAgent
        from core.utils.llm_factory import LLMFactory
        from core.utils.output_manager import create_run_output, write_latest_index
        from core.utils.output_writer import write_run_overview
        from core.utils.process_logger import ProcessLogger
        from core.workflow.predefined.graph import build_predefined_graph
        from core.workflow.predefined.orchestrator import PredefinedOrchestrator
        from core.workflow.predefined.recovery import RecoveryCoordinator
        from memory.meta_manager import MIRIXMemorySystem

        tcs_id = str(scenario["tcs_id"])
        timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        session_id = f"{tcs_id}_{timestamp}"
        paths = create_run_output(
            mode="predefined",
            tcs_id=tcs_id,
            timestamp=timestamp,
            attempt_dir=str(evidence_dir),
        )
        write_latest_index(paths)
        memory = None
        logger = None
        recovery_artifact: str | None = None
        final_state: dict[str, Any] = {}
        metrics: dict[str, Any] = {}
        case_error: Exception | None = None
        logger_closed = False

        try:
            memory = MIRIXMemorySystem(
                session_id=session_id,
                output_dir=paths.run_dir,
                cross_run_dir=paths.shared_memory_dir,
            )
            logger = ProcessLogger(paths.run_dir)
            llms = {
                role: LLMFactory.create(role, session_id=session_id, log_dir=paths.llm_logs_dir)
                for role in ("observer", "decider", "reflector", "orchestrator")
            }
            orchestrator = PredefinedOrchestrator(
                llm=llms["orchestrator"], figma_adapter=self.figma, memory=memory, logger=logger
            )
            observer = ObserverAgent(
                llms["observer"], self.observer_tools.get_tools(), memory=memory, logger=logger, monitor=self.monitor
            )
            decider = DeciderAgent(llms["decider"], memory=memory, logger=logger, monitor=self.monitor)
            executor = ExecutorAgent(self.executor_tools, memory=memory, logger=logger, monitor=self.monitor)
            reflector = ReflectorAgent(llms["reflector"], memory=memory, logger=logger, device=self.device)
            recorder = RecorderAgent(memory=memory, logger=logger)

            figma_context = orchestrator.pre_scenario_discovery(scenario=scenario, output_dir=paths.run_dir)
            memory.init_session(scenario=scenario, tcs_id=tcs_id, figma_context=figma_context)
            base_state = _initial_state(scenario=scenario, session_id=session_id, paths=paths)
            recovery_view = _RecoveryMemoryView(memory)
            observation_counter = 0
            assessment_holder: dict[str, Any] = {}
            planned_steps_holder: list[str] = []

            def observe_fresh(_case):
                nonlocal observation_counter
                observation_counter += 1
                state = dict(base_state)
                state["current_step"] = -observation_counter
                state["step_dir"] = str(evidence_dir / "recovery" / f"observation_{observation_counter:02d}")
                Path(state["step_dir"]).mkdir(parents=True, exist_ok=True)
                with _temporary_agent_memory((observer,), recovery_view):
                    update = _agent_update(observer.analyze(state), phase="Recovery observation")
                return {
                    "text": str(update.get("observer_analysis") or ""),
                    "screenshot_path": update.get("screenshot_path"),
                    "xml_path": str(Path(state["step_dir"]) / "hierarchy.xml"),
                    "state_update": update,
                }

            def assess_context(case, observation):
                assessment = orchestrator.assess_navigation_context(
                    observation_text=str(observation.get("text") or ""),
                    required_context=str(case.get("navigation_context") or ""),
                )
                assessment_holder.clear()
                assessment_holder.update(assessment)
                return assessment

            def plan_transition(case, observation, assessment):
                steps = orchestrator.plan_recovery_transition(
                    observation_text=str(observation.get("text") or ""),
                    required_context=str(case.get("navigation_context") or ""),
                    figma_context=figma_context,
                )
                planned_steps_holder.clear()
                planned_steps_holder.extend(str(step) for step in steps)
                if not steps:
                    require_verified_recovery(
                        initial_assessment=assessment,
                        planned_steps=steps,
                        final_assessment={"matched": True},
                    )
                return steps

            def execute_transition(_case, steps):
                state = dict(base_state)
                artifacts: list[str] = []
                for step_number, instruction in enumerate(steps, start=1):
                    state["orchestrator_instruction"] = str(instruction)
                    state["current_step"] = -100 - step_number
                    state["step_dir"] = str(evidence_dir / "recovery" / f"transition_{step_number:02d}")
                    Path(state["step_dir"]).mkdir(parents=True, exist_ok=True)
                    with _temporary_agent_memory((observer, decider, executor), recovery_view):
                        state.update(_agent_update(observer.analyze(state), phase="Recovery Observer"))
                        state.update(_agent_update(decider.decide(state), phase="Recovery Decider"))
                        state.update(_agent_update(executor.execute(state), phase="Recovery Executor"))
                    artifacts.append(state["step_dir"])
                return {"artifact_paths": artifacts, "steps_executed": len(steps)}

            def verify_final(case, observation, execution):
                if execution is None:
                    return {"passed": True, "assessment": dict(assessment_holder)}
                verified_observation = observe_fresh(case)
                final_assessment = orchestrator.assess_navigation_context(
                    observation_text=str(verified_observation.get("text") or ""),
                    required_context=str(case.get("navigation_context") or ""),
                )
                require_verified_recovery(
                    initial_assessment=assessment_holder,
                    planned_steps=planned_steps_holder,
                    final_assessment=final_assessment,
                )
                return {
                    "passed": True,
                    "assessment": final_assessment,
                    "screenshot_path": verified_observation.get("screenshot_path"),
                    "xml_path": verified_observation.get("xml_path"),
                }

            RecoveryCoordinator(
                observe_fresh=observe_fresh,
                assess_context=assess_context,
                plan_transition=plan_transition,
                execute_transition=execute_transition,
                verify_final=verify_final,
                memory=memory,
            ).run(scenario, evidence_dir)
            recovery_artifact = str(evidence_dir / "recovery_transition.json")

            app = build_predefined_graph(observer, decider, executor, reflector, orchestrator)
            initial_state = _initial_state(scenario=scenario, session_id=session_id, paths=paths)
            initial_state["start_time"] = time.time()
            final_state = dict(app.invoke(initial_state, config={"recursion_limit": 150}))
            final_state["end_time"] = time.time()
            outcome = derive_case_outcome(final_state, total_steps=len(scenario.get("sub_steps", [])))
            final_state["canonical_status"] = outcome["status"]
            metrics = recorder.finalize_run_metrics(
                final_state,
                source_workbook=self.source_workbook,
                canonical_status=outcome["status"],
            )
            require_case_reporting_artifacts(paths.run_dir)
            logger_closed = True
            write_run_overview(
                output_dir=paths.run_dir,
                tcs_id=tcs_id,
                status=outcome["status"],
                mode="predefined",
                steps_completed=final_state.get("steps_completed_count", 0),
                total_steps=len(scenario.get("sub_steps", [])),
                duration_seconds=metrics.get("total_duration_seconds", 0),
                physical_actions=metrics.get("physical_actions", 0),
                figma_enabled=figma_context.get("figma_enabled", False),
                tokens=metrics.get("total_tokens_estimate", 0),
                cost_usd=metrics.get("total_price_usd", 0.0),
                reflector_judgment=metrics.get("justification", {}).get("reflector_final_judgment", ""),
                steps_data=[],
            )
        except Exception as error:
            case_error = error
        finally:
            if memory is not None:
                try:
                    memory.close()
                except Exception as close_error:
                    case_error = case_error or close_error
            if logger is not None and not logger_closed:
                try:
                    logger.close()
                except Exception as close_error:
                    case_error = case_error or close_error

        metrics_path = evidence_dir / "final_metrics.json"
        if case_error is not None and metrics_path.is_file():
            try:
                persisted_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
                metrics = reconcile_cleanup_failure_artifacts(
                    attempt_dir=evidence_dir,
                    source_workbook=self.source_workbook,
                    tcs_id=tcs_id,
                    metrics=metrics or persisted_metrics,
                    cleanup_error=case_error,
                )
            except Exception as reconciliation_error:
                case_error = RuntimeError(
                    f"{case_error}; canonical artifact reconciliation failed: "
                    f"{reconciliation_error}"
                )

        screenshots = sorted(
            str(path)
            for pattern in ("*.png", "*.jpg", "*.jpeg")
            for path in evidence_dir.rglob(pattern)
        )
        common = {
            "actual_observation": str(final_state.get("observer_analysis") or ""),
            "final_screenshot_paths": screenshots,
            "process_log_paths": [str(path) for path in evidence_dir.rglob("process.log")],
            "llm_log_paths": [str(path) for path in evidence_dir.rglob("logs/llm/*.json")],
            "recovery_artifact": recovery_artifact,
            "metrics_path": str(metrics_path) if metrics_path.is_file() else None,
        }
        if case_error is not None:
            reason_path = evidence_dir / "case_runtime_error.txt"
            reason_path.write_text(
                f"{type(case_error).__name__}: {case_error}\n",
                encoding="utf-8",
            )
            return {
                **common,
                "status": "technical_error",
                "duration_seconds": metrics.get("total_duration_seconds", 0),
                "reason_ref": str(reason_path),
                "error_or_anomaly_reason": str(reason_path),
            }

        outcome = derive_case_outcome(final_state, total_steps=len(scenario.get("sub_steps", [])))
        return {
            **common,
            "status": outcome["status"],
            "duration_seconds": metrics.get("total_duration_seconds", 0),
            "reason_ref": outcome["reason"],
            "error_or_anomaly_reason": outcome["reason"],
            "actual_observation": outcome["actual_observation"],
        }


@contextmanager
def _default_runtime_factory(
    *,
    xlsx_path: str,
    run_root: str,
    figma_url: str | None,
    config_values: Mapping[str, object],
    device_snapshot: Any,
):
    if config_values.get("OBSERVER_UNCERTAINTY_ENABLED") is not False:
        raise RuntimeError("Observer uncertainty must remain False for this baseline.")

    from adapters.device.adb_adapter import ADBAdapter
    from adapters.figma.figma_adapter import build_figma_adapter_from_prompt
    from tools.executor_tools import ExecutorTools
    from tools.observer_tools import ObserverTools
    from visual.monitor import VisualMonitor

    device = ADBAdapter(str(config_values.get("TARGET_DEVICE") or "")).connect()
    observer_tools = ObserverTools(device)
    executor_tools = ExecutorTools(device)
    figma = build_figma_adapter_from_prompt(
        access_token=config.FIGMA_ACCESS_TOKEN,
        figma_url=figma_url or None,
    )
    info = device.d.info
    monitor = VisualMonitor(
        device_w=info.get("displayWidth", 1080),
        device_h=info.get("displayHeight", 2400),
    )
    monitor.start()
    try:
        yield _LiveCaseExecutor(
            device=device,
            monitor=monitor,
            figma=figma,
            observer_tools=observer_tools,
            executor_tools=executor_tools,
            source_workbook=xlsx_path,
        )
    finally:
        try:
            monitor.stop()
        except Exception as error:
            print(f"[Predefined] Warning: monitor shutdown failed: {error}")
