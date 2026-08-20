"""Callback-driven navigation recovery for predefined workbook scenarios."""

from __future__ import annotations

import copy
import datetime as dt
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any


_MISSING = object()


class ScenarioMutationError(RuntimeError):
    """Raised when a recovery callback changes immutable workbook scenario data."""


class RecoveryCoordinator:
    """Recover the required navigation context without altering QA sub-steps.

    All live-system behavior is supplied by callbacks so this coordinator remains
    testable with plain fakes and can be integrated by a later runner task.
    """

    def __init__(
        self,
        *,
        observe_fresh: Callable[[dict[str, Any]], Any],
        assess_context: Callable[[dict[str, Any], Any], Mapping[str, Any] | bool],
        plan_transition: Callable[[dict[str, Any], Any, Mapping[str, Any]], Sequence[str]],
        execute_transition: Callable[[dict[str, Any], list[str]], Any],
        verify_final: Callable[[dict[str, Any], Any, Any], Any],
        memory: Any | None = None,
    ) -> None:
        self.observe_fresh = observe_fresh
        self.assess_context = assess_context
        self.plan_transition = plan_transition
        self.execute_transition = execute_transition
        self.verify_final = verify_final
        self.memory = memory

    def run(self, scenario: dict[str, Any], evidence_dir: str | Path) -> dict[str, Any]:
        """Perform and persist one recovery transition, re-raising operational errors."""
        evidence_path = Path(evidence_dir)
        evidence_path.mkdir(parents=True, exist_ok=True)
        raw_value = scenario.get("raw_test_step", _MISSING)
        sub_steps_value = scenario.get("sub_steps", _MISSING)
        raw_snapshot = _MISSING if raw_value is _MISSING else copy.deepcopy(raw_value)
        sub_steps_snapshot = _MISSING if sub_steps_value is _MISSING else copy.deepcopy(sub_steps_value)
        started_wall = dt.datetime.now(dt.timezone.utc)
        started_monotonic = time.monotonic()
        transition: dict[str, Any] = {
            "tcs_id": str(scenario.get("tcs_id", "")),
            "required_navigation_context": scenario.get("navigation_context", ""),
            "fresh_observation": None,
            "fresh_observation_text": "",
            "context_matched": None,
            "reason": "",
            "planned_operational_steps": [],
            "execution_result": None,
            "verification_result": None,
            "timestamps": {"started_at": started_wall.isoformat(), "finished_at": None},
            "duration_seconds": None,
            "evidence_directory": str(evidence_path),
            "artifact_paths": [],
            "source_integrity": {"preserved": None},
            "status": "running",
            "error": None,
            "cancellation": None,
        }
        raised_error: Exception | None = None

        try:
            observation = self.observe_fresh(scenario)
            transition["fresh_observation"] = observation
            transition["fresh_observation_text"] = self._observation_text(observation)
            transition["artifact_paths"] = self._collect_paths(observation)

            assessment = self._as_assessment(self.assess_context(scenario, observation))
            transition["context_matched"] = assessment["matched"]
            transition["reason"] = assessment["reason"]
            self._record_event("recovery_context_check", transition, assessment)

            if assessment["matched"]:
                self._store_transition_procedure(transition)
                transition["verification_result"] = self.verify_final(scenario, observation, None)
                self._record_event("recovery_verification", transition, transition["verification_result"])
                transition["status"] = "no_op"
            else:
                operational_steps = list(self.plan_transition(scenario, observation, assessment))
                transition["planned_operational_steps"] = operational_steps
                self._store_transition_procedure(transition)
                execution = self.execute_transition(scenario, operational_steps)
                transition["execution_result"] = execution
                transition["artifact_paths"].extend(self._collect_paths(execution))
                self._record_event("recovery_execution", transition, execution)
                transition["verification_result"] = self.verify_final(scenario, observation, execution)
                transition["artifact_paths"].extend(self._collect_paths(transition["verification_result"]))
                transition["artifact_paths"] = self._unique_paths(transition["artifact_paths"])
                self._record_event("recovery_verification", transition, transition["verification_result"])
                transition["status"] = "completed"
        except Exception as error:
            raised_error = error
            transition["status"] = "error"
            transition["error"] = {"type": type(error).__name__, "message": str(error)}
        finally:
            cancellation = sys.exc_info()[1]
            is_cancellation = isinstance(cancellation, (KeyboardInterrupt, SystemExit))
            if is_cancellation:
                transition["status"] = "interrupted"
                transition["cancellation"] = {
                    "type": type(cancellation).__name__,
                    "reason": f"Recovery cancelled by {type(cancellation).__name__}.",
                }
            source_preserved = self._source_matches(scenario, raw_snapshot, sub_steps_snapshot)
            transition["source_integrity"] = {"preserved": source_preserved}
            if not source_preserved:
                self._restore_source(scenario, raw_snapshot, sub_steps_snapshot)
                if not is_cancellation:
                    mutation_error = ScenarioMutationError(
                        "Recovery callbacks mutated the source scenario raw_test_step or sub_steps."
                    )
                    transition["status"] = "error"
                    transition["error"] = {"type": type(mutation_error).__name__, "message": str(mutation_error)}
                    raised_error = mutation_error

            transition["timestamps"]["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            transition["duration_seconds"] = time.monotonic() - started_monotonic
            artifact_path = evidence_path / "recovery_transition.json"
            self._atomic_json_write(artifact_path, transition)
            if self.memory is not None:
                try:
                    self._store_resources(transition, artifact_path)
                except Exception as persistence_error:
                    if is_cancellation:
                        pass
                    elif raised_error is None:
                        transition["status"] = "error"
                        transition["error"] = {
                            "type": type(persistence_error).__name__,
                            "message": str(persistence_error),
                        }
                        self._atomic_json_write(artifact_path, transition)
                        raised_error = persistence_error

        if raised_error is not None:
            raise raised_error
        return transition

    @staticmethod
    def _as_assessment(value: Mapping[str, Any] | bool) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return {"matched": bool(value.get("matched")), "reason": str(value.get("reason", ""))}
        return {"matched": bool(value), "reason": ""}

    @staticmethod
    def _observation_text(observation: Any) -> str:
        if isinstance(observation, Mapping):
            return str(observation.get("text", ""))
        return str(observation)

    @classmethod
    def _collect_paths(cls, value: Any) -> list[str]:
        paths: list[str] = []
        if isinstance(value, Mapping):
            for key, item in value.items():
                if key in {"screenshot_path", "xml_path", "artifact_path", "evidence_path"} and item:
                    paths.append(str(item))
                elif key == "artifact_paths" and isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
                    paths.extend(str(path) for path in item if path)
                else:
                    paths.extend(cls._collect_paths(item))
        elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            for item in value:
                paths.extend(cls._collect_paths(item))
        return cls._unique_paths(paths)

    @staticmethod
    def _unique_paths(paths: Sequence[str]) -> list[str]:
        return list(dict.fromkeys(paths))

    @staticmethod
    def _source_matches(scenario: dict[str, Any], raw_snapshot: Any, sub_steps_snapshot: Any) -> bool:
        return scenario.get("raw_test_step", _MISSING) == raw_snapshot and scenario.get("sub_steps", _MISSING) == sub_steps_snapshot

    @staticmethod
    def _restore_source(scenario: dict[str, Any], raw_snapshot: Any, sub_steps_snapshot: Any) -> None:
        for key, value in (("raw_test_step", raw_snapshot), ("sub_steps", sub_steps_snapshot)):
            if value is _MISSING:
                scenario.pop(key, None)
            else:
                scenario[key] = copy.deepcopy(value)

    def _record_event(self, event_type: str, transition: Mapping[str, Any], details: Any) -> None:
        if self.memory is None:
            return
        self.memory.update(
            {
                "episodic": {
                    "event_type": event_type,
                    "summary": f"Recovery transition for {transition['tcs_id']}",
                    "details": json.dumps(details, default=str, sort_keys=True),
                    "actor": "recovery_coordinator",
                    "step": 0,
                }
            }
        )

    def _store_transition_procedure(self, transition: Mapping[str, Any]) -> None:
        if self.memory is None:
            return
        self.memory.update(
            {
                "procedural": {
                    "entry_type": "recovery_transition",
                    "description": transition["reason"],
                    "steps": transition["planned_operational_steps"],
                    "tcs_id": transition["tcs_id"],
                }
            }
        )

    def _store_resources(self, transition: Mapping[str, Any], artifact_path: Path) -> None:
        for path in [*transition["artifact_paths"], str(artifact_path)]:
            self.memory.update(
                {
                    "resource": {
                        "title": "recovery_transition_evidence",
                        "summary": f"Recovery evidence for {transition['tcs_id']}",
                        "resource_type": self._resource_type(path, artifact_path),
                        "path": path,
                        "step": 0,
                    }
                }
            )

    @staticmethod
    def _resource_type(path: str, artifact_path: Path) -> str:
        if Path(path) == artifact_path:
            return "recovery_artifact"
        suffix = Path(path).suffix.lower()
        if suffix == ".xml":
            return "xml"
        if suffix in {".png", ".jpg", ".jpeg"}:
            return "screenshot"
        return "artifact"

    @staticmethod
    def _atomic_json_write(destination: Path, content: Mapping[str, Any]) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp", delete=False
        ) as temporary_file:
            json.dump(content, temporary_file, indent=2, sort_keys=True, default=str)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, destination)
