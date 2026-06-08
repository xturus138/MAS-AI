import os
from typing import Optional, TYPE_CHECKING
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from core.models.state import AgentState
from shared.prompts.predefined_orchestrator_prompts import (
    FIGMA_FLOW_SYSTEM_PROMPT,
    FIGMA_FLOW_EXAMPLES,
    BRIDGE_SYSTEM_PROMPT,
    BRIDGE_EXAMPLES,
)

if TYPE_CHECKING:
    from adapters.figma.figma_adapter import FigmaAdapter
    from memory.meta_manager import MIRIXMemorySystem


class BridgePlan(BaseModel):
    """Chain-of-Thought: reasoning MUST be first field."""
    reasoning: str = Field(
        description="Analyze current vs target screen step-by-step before determining bridge steps."
    )
    bridge_steps: list = Field(
        description=(
            "Ordered list of navigation steps to move from the current screen "
            "to the required starting screen for the next scenario. "
            "Each step is a plain string instruction like 'click Back' or 'click Home button'."
        )
    )


class FigmaFlowPlan(BaseModel):
    """Chain-of-Thought: reasoning MUST be first field."""
    reasoning: str = Field(
        description="Analyze scenario context and Figma graph step-by-step before selecting path."
    )
    path_ids: list = Field(
        description=(
            "The ordered list of Figma Node IDs (e.g. ['10:5', '12:1']) that represent "
            "the full prototype flow from the start screen to the expected end screen "
            "for this scenario. Return an empty list if no path can be resolved."
        )
    )


# Note: BRIDGE_SYSTEM_PROMPT now imported from shared.prompts.predefined_orchestrator_prompts


class PredefinedOrchestrator:
    """
    Orchestrator for the Predefined (Scenario-Based) workflow.

    Responsibilities:
    - Manage step index and retry logic based on Reflector feedback.
    - Discover Figma nodes before each scenario.
    - Compute bridge navigation steps between consecutive scenarios.
    """

    def __init__(self, llm=None, figma_adapter=None, memory=None, logger=None):
        self.llm = llm
        self.figma: Optional["FigmaAdapter"] = figma_adapter
        self.memory: Optional["MIRIXMemorySystem"] = memory
        self.logger = logger
        self._bridge_llm = llm.with_structured_output(BridgePlan) if llm else None
        self._mapping_llm = llm.with_structured_output(FigmaFlowPlan) if llm else None

    def _log(self, msg: str, detail: str = ""):
        if self.logger is not None:
            self.logger.log("ORCHESTRATOR", msg, detail)

    def pre_scenario_discovery(self, scenario: dict, output_dir: str) -> dict:
        """
        Analyzes the Figma prototype flow and test scenario to determine
        the start screen and the expected path.

        Returns figma_context dict that is passed to memory.init_session().
        The figma_end_screenshot_b64 is stored in Resource Memory, not AgentState.
        """
        figma_enabled = self.figma is not None
        if not figma_enabled:
            return {
                "figma_enabled": False,
                "figma_start_node_id": "",
                "figma_end_node_id": "",
                "figma_end_screenshot_b64": "",
            }

        menu_name = scenario.get("navigation_context", "")
        scenario_desc = scenario.get("scenario_desc", "")
        sub_steps_raw = "\n".join([f"- {s}" for s in scenario.get("sub_steps", [])])

        flow_summary = self.figma.get_flow_summary()

        human_content = (
            f"TEST SCENARIO:\n"
            f"  Menu Context: {menu_name}\n"
            f"  Description: {scenario_desc}\n"
            f"  Test Steps:\n{sub_steps_raw}\n\n"
            f"FIGMA PROTOTYPE GRAPH:\n{flow_summary}"
        )

        # Build messages with Few-Shot examples for Figma flow planning
        messages = [SystemMessage(content=FIGMA_FLOW_SYSTEM_PROMPT)]
        for role, content in FIGMA_FLOW_EXAMPLES:
            if role == "human":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(SystemMessage(content=content))
        messages.append(HumanMessage(content=human_content))

        print(f"[Predefined] Planning Figma flow for '{menu_name}'...")
        try:
            result = self._mapping_llm.invoke(messages)

            if not result.path_ids:
                print("[Predefined] LLM could not resolve a Figma path. Falling back to text-only.")
                return {"figma_enabled": False, "figma_start_node_id": "", "figma_end_node_id": "", "figma_end_screenshot_b64": ""}

            start_id = result.path_ids[0]
            end_id = result.path_ids[-1]
            print(f"[Predefined] Flow Planned: {result.path_ids} ({result.reasoning})")

            figma_end_screenshot_b64 = self.figma.get_node_screenshot_b64(end_id)

            gold_standard_path = os.path.join(output_dir, "figma_gold_standard.png")
            self.figma.save_composite_gold_standard(result.path_ids, gold_standard_path)

            return {
                "figma_enabled": True,
                "figma_start_node_id": start_id,
                "figma_end_node_id": end_id,
                "figma_end_screenshot_b64": figma_end_screenshot_b64,
            }
        except Exception as e:
            print(f"[Predefined] Figma flow planning failed: {e}")
            return {"figma_enabled": False, "figma_start_node_id": "", "figma_end_node_id": "", "figma_end_screenshot_b64": ""}

    # ── Bridge Navigation ─────────────────────────────────────────────────────

    def compute_bridge(self, current_screen_description: str, next_start_node_id: str) -> list:
        """Compute minimal navigation steps from the current screen to the next scenario's start."""
        if not self.figma or not self._bridge_llm:
            return []

        next_context = self.figma.get_node_context(next_start_node_id)
        next_screen_name = next_context.get("document", {}).get("name", next_start_node_id)

        human_content = (
            f"CURRENT SCREEN (where the app is now):\n{current_screen_description}\n\n"
            f"REQUIRED STARTING SCREEN (for next scenario):\n{next_screen_name}\n"
            f"Figma Node ID: {next_start_node_id}"
        )

        # Build messages with Few-Shot examples for bridge navigation
        messages = [SystemMessage(content=BRIDGE_SYSTEM_PROMPT)]
        for role, content in BRIDGE_EXAMPLES:
            if role == "human":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(SystemMessage(content=content))
        messages.append(HumanMessage(content=human_content))

        print(f"[Predefined] Computing navigation bridge to '{next_screen_name}'...")
        try:
            result = self._bridge_llm.invoke(messages)
            print(f"[Predefined] Bridge plan: {result.bridge_steps}")
            return result.bridge_steps
        except Exception as e:
            print(f"[Predefined] Bridge computation failed: {e}")
            return []

    # ── LangGraph Node ────────────────────────────────────────────────────────

    def orchestrate(self, state: AgentState) -> dict:
        """LangGraph node: index-manager that advances or retries sub-steps."""
        tcs_id = state.get("tcs_id", "")
        current_idx = state.get("current_sub_step_index", 0)
        global_step = state.get("current_step", 0)
        output_dir = state.get("output_dir", "outputs")
        retry_count = state.get("step_retry_count", 0)

        last_passed = state.get("last_reflector_passed", True)
        sender = state.get("sender", "START")

        if self.logger is not None:
            self.logger.section(f"CYCLE {global_step} — ORCHESTRATOR (predefined)")
        self._log(
            f"Entered from sender={sender}  step_index={current_idx}  retry={retry_count}",
            f"last_reflector_passed={last_passed}"
        )

        print(f"[Orchestrator] Step {current_idx + 1} | from={sender} | reflector={'PASS' if last_passed else 'FAIL'} | retry={retry_count}")

        # Advance or retry based on reflector outcome
        if sender == "reflector":
            if last_passed:
                current_idx += 1
                retry_count = 0
                self._log(f"Step {current_idx - 1} verified — advancing to index {current_idx}")
            else:
                retry_count += 1
                print(f"[Orchestrator] ⚠ Step failed — retry {retry_count}/3")
                self._log(f"Step FAILED — retry {retry_count}/3 for index {current_idx}")

        if retry_count > 3:
            print("[Orchestrator] ✗ Maximum retries (3) exceeded — aborting scenario.")
            self._log("ABORT — maximum retries (3) exceeded")
            if self.memory is not None:
                self.memory.update({
                    "episodic": {
                        "event_type": "orchestrator_decision",
                        "summary": "Maximum retries exceeded. Aborting scenario.",
                        "details": "",
                        "actor": "orchestrator",
                        "step": global_step,
                    }
                })
            return {
                "is_completed": True,
                "sender": "orchestrator",
                "stagnation_count": 99,
            }

        steps_completed_count = state.get("steps_completed_count", 0)
        if sender == "reflector" and last_passed:
            steps_completed_count += 1

        # Read sub_steps from Procedural Memory
        sub_steps = []
        if self.memory is not None:
            sub_steps = self.memory.procedural.get_steps(tcs_id, "workflow")

        update_data = {
            "current_sub_step_index": current_idx,
            "current_step": global_step + 1,
            "step_retry_count": retry_count,
            "sender": "orchestrator",
            "is_first_verify_attempt": (retry_count == 0),
            "steps_completed_count": steps_completed_count,
        }

        if current_idx < len(sub_steps):
            step_dir = os.path.join(output_dir, f"step_{current_idx + 1}")
            if retry_count > 0:
                step_dir = os.path.join(output_dir, f"step_{current_idx + 1}_retry_{retry_count}")

            if not os.path.exists(step_dir):
                os.makedirs(step_dir)

            update_data["step_dir"] = step_dir
            update_data["is_completed"] = False
            print(f"[Predefined] Dispatching: {sub_steps[current_idx]}")
            self._log(f"→ Dispatching step {current_idx + 1}/{len(sub_steps)}", sub_steps[current_idx])

            if self.memory is not None:
                self.memory.update({
                    "episodic": {
                        "event_type": "orchestrator_decision",
                        "summary": f"Dispatching step {current_idx + 1}: {sub_steps[current_idx]}",
                        "details": "",
                        "actor": "orchestrator",
                        "step": global_step + 1,
                    }
                })
        else:
            completion_msg = f"All {len(sub_steps)} predefined sub-steps completed and verified successfully."
            update_data["is_completed"] = True
            print("[Predefined] All steps verified. Scenario success.")
            self._log("→ ALL STEPS COMPLETE — scenario success", completion_msg)

            if self.memory is not None:
                self.memory.update({
                    "episodic": {
                        "event_type": "orchestrator_decision",
                        "summary": completion_msg,
                        "details": "",
                        "actor": "orchestrator",
                        "step": global_step + 1,
                    }
                })

        return update_data
