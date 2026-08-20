import json
from pathlib import Path

import pytest

from memory.meta_manager import MIRIXMemorySystem


class RecordingMemory:
    def __init__(self):
        self.packets = []

    def update(self, packet):
        self.packets.append(packet)


def scenario():
    return {
        "tcs_id": "TCS-42",
        "navigation_context": "Chat detail for Ada",
        "raw_test_step": "1. Open chat\n2. Send message",
        "sub_steps": ["Open chat", "Send message"],
    }


def recovery(**overrides):
    from core.workflow.predefined.recovery import RecoveryCoordinator

    callbacks = {
        "observe_fresh": lambda case: {"text": "Home screen", "screenshot_path": "fresh.png"},
        "assess_context": lambda case, observation: {
            "matched": False,
            "reason": "The required chat is not open.",
        },
        "plan_transition": lambda case, observation, assessment: ["Open chats", "Open Ada"],
        "execute_transition": lambda case, steps: {"xml_path": "after.xml"},
        "verify_final": lambda case, observation, execution: {"passed": True},
    }
    callbacks.update(overrides)
    return RecoveryCoordinator(**callbacks)


def test_mirix_gateway_returns_underlying_labeled_mapping():
    expected = {"core": "<core_memory>context</core_memory>", "episodic": ""}

    class Retriever:
        def retrieve_with_labels(self, topic, max_per_store):
            assert (topic, max_per_store) == ("chat", 3)
            return expected

    memory = object.__new__(MIRIXMemorySystem)
    memory._retriever = Retriever()

    assert memory.retrieve_with_labels("chat", max_per_store=3) is expected


def test_already_matching_context_skips_planning_and_execution(tmp_path):
    called = []
    coordinator = recovery(
        assess_context=lambda case, observation: {"matched": True, "reason": "Already at chat."},
        plan_transition=lambda *args: called.append("plan"),
        execute_transition=lambda *args: called.append("execute"),
    )

    transition = coordinator.run(scenario(), tmp_path)

    assert called == []
    assert transition["status"] == "no_op"
    artifact = json.loads((tmp_path / "recovery_transition.json").read_text(encoding="utf-8"))
    assert artifact["context_matched"] is True
    assert artifact["planned_operational_steps"] == []


def test_matching_context_stores_a_separate_no_op_transition_in_mirix(tmp_path):
    memory = RecordingMemory()
    coordinator = recovery(
        memory=memory,
        assess_context=lambda case, observation: {"matched": True, "reason": "Already at chat."},
    )

    coordinator.run(scenario(), tmp_path)

    procedural_packets = [packet["procedural"] for packet in memory.packets if "procedural" in packet]
    assert procedural_packets == [
        {
            "entry_type": "recovery_transition",
            "description": "Already at chat.",
            "steps": [],
            "tcs_id": "TCS-42",
        }
    ]


def test_mismatch_runs_recovery_and_persists_transition_artifact(tmp_path):
    executed_steps = []
    coordinator = recovery(
        execute_transition=lambda case, steps: executed_steps.extend(steps) or {"artifact_path": "execution.log"},
    )

    transition = coordinator.run(scenario(), tmp_path)

    assert executed_steps == ["Open chats", "Open Ada"]
    assert transition["status"] == "completed"
    artifact = json.loads((tmp_path / "recovery_transition.json").read_text(encoding="utf-8"))
    assert artifact["tcs_id"] == "TCS-42"
    assert artifact["required_navigation_context"] == "Chat detail for Ada"
    assert artifact["fresh_observation"]["text"] == "Home screen"
    assert artifact["verification_result"] == {"passed": True}
    assert artifact["artifact_paths"] == ["fresh.png", "execution.log"]
    assert artifact["timestamps"]["started_at"]
    assert artifact["timestamps"]["finished_at"]
    assert artifact["duration_seconds"] >= 0


def test_recovery_cannot_mutate_source_raw_step_or_sub_steps(tmp_path):
    case = scenario()
    raw_before = case["raw_test_step"]
    steps_before = list(case["sub_steps"])
    coordinator = recovery(
        observe_fresh=lambda case: case["sub_steps"].append("Injected transition") or {"text": "Home"},
    )

    with pytest.raises(Exception, match="source scenario"):
        coordinator.run(case, tmp_path)

    artifact = json.loads((tmp_path / "recovery_transition.json").read_text(encoding="utf-8"))
    assert artifact["status"] == "error"
    assert artifact["source_integrity"]["preserved"] is False
    assert case["raw_test_step"] == raw_before
    assert case["sub_steps"] == steps_before


def test_scenario_without_optional_source_fields_is_not_a_false_mutation(tmp_path):
    case = {"tcs_id": "TCS-absent", "navigation_context": "Chat detail for Ada"}

    transition = recovery().run(case, tmp_path)

    assert transition["status"] == "completed"
    assert transition["source_integrity"]["preserved"] is True
    assert "raw_test_step" not in case
    assert "sub_steps" not in case


def test_mirix_stores_recovery_separately_without_overwriting_workflow(tmp_path):
    memory = RecordingMemory()
    coordinator = recovery(memory=memory)

    coordinator.run(scenario(), tmp_path)

    procedural_packets = [packet["procedural"] for packet in memory.packets if "procedural" in packet]
    assert procedural_packets == [
        {
            "entry_type": "recovery_transition",
            "description": "The required chat is not open.",
            "steps": ["Open chats", "Open Ada"],
            "tcs_id": "TCS-42",
        }
    ]
    assert all(packet.get("entry_type") != "workflow" for packet in procedural_packets)
    episodic_events = [packet["episodic"]["event_type"] for packet in memory.packets if "episodic" in packet]
    assert episodic_events == ["recovery_context_check", "recovery_execution", "recovery_verification"]
    resource_paths = [packet["resource"]["path"] for packet in memory.packets if "resource" in packet]
    assert resource_paths[:2] == ["fresh.png", "after.xml"]
    assert resource_paths[-1].endswith("recovery_transition.json")


def test_resource_memory_failure_replaces_success_artifact_with_error(tmp_path):
    class ResourceFailingMemory(RecordingMemory):
        def update(self, packet):
            if "resource" in packet:
                raise RuntimeError("fake resource persistence exploded")
            super().update(packet)

    coordinator = recovery(memory=ResourceFailingMemory())

    with pytest.raises(RuntimeError, match="fake resource persistence exploded"):
        coordinator.run(scenario(), tmp_path)

    artifact = json.loads((tmp_path / "recovery_transition.json").read_text(encoding="utf-8"))
    assert artifact["status"] == "error"
    assert artifact["error"] == {
        "type": "RuntimeError",
        "message": "fake resource persistence exploded",
    }


def test_keyboard_interrupt_is_recorded_as_interrupted_not_a_recovery_error(tmp_path):
    coordinator = recovery(observe_fresh=lambda case: (_ for _ in ()).throw(KeyboardInterrupt()))

    with pytest.raises(KeyboardInterrupt):
        coordinator.run(scenario(), tmp_path)

    artifact = json.loads((tmp_path / "recovery_transition.json").read_text(encoding="utf-8"))
    assert artifact["status"] == "interrupted"
    assert artifact["cancellation"] == {
        "type": "KeyboardInterrupt",
        "reason": "Recovery cancelled by KeyboardInterrupt.",
    }
    assert artifact["error"] is None


def test_cancellation_stores_collected_resources_and_transition_artifact_in_mirix(tmp_path):
    memory = RecordingMemory()
    coordinator = recovery(
        memory=memory,
        observe_fresh=lambda case: {
            "text": "Home screen",
            "screenshot_path": "fresh.png",
            "xml_path": "fresh.xml",
        },
        assess_context=lambda case, observation: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    with pytest.raises(KeyboardInterrupt):
        coordinator.run(scenario(), tmp_path)

    resource_paths = [packet["resource"]["path"] for packet in memory.packets if "resource" in packet]
    assert resource_paths[:2] == ["fresh.png", "fresh.xml"]
    assert resource_paths[-1].endswith("recovery_transition.json")


def test_resource_persistence_failure_during_cancellation_cannot_mask_interrupt(tmp_path):
    class ResourceFailingMemory(RecordingMemory):
        resource_attempted = False

        def update(self, packet):
            if "resource" in packet:
                self.resource_attempted = True
                raise RuntimeError("fake cancellation resource persistence exploded")
            super().update(packet)

    memory = ResourceFailingMemory()
    coordinator = recovery(
        memory=memory,
        observe_fresh=lambda case: {"text": "Home", "screenshot_path": "fresh.png"},
        assess_context=lambda case, observation: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    with pytest.raises(KeyboardInterrupt):
        coordinator.run(scenario(), tmp_path)

    artifact = json.loads((tmp_path / "recovery_transition.json").read_text(encoding="utf-8"))
    assert memory.resource_attempted is True
    assert artifact["status"] == "interrupted"
    assert artifact["error"] is None


def test_callback_exception_retains_an_error_bearing_transition_artifact(tmp_path):
    coordinator = recovery(plan_transition=lambda *args: (_ for _ in ()).throw(RuntimeError("fake planner exploded")))

    with pytest.raises(RuntimeError, match="fake planner exploded"):
        coordinator.run(scenario(), tmp_path)

    artifact = json.loads((tmp_path / "recovery_transition.json").read_text(encoding="utf-8"))
    assert artifact["status"] == "error"
    assert artifact["error"]["type"] == "RuntimeError"
    assert artifact["error"]["message"] == "fake planner exploded"
