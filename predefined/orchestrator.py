import os
from typing import Optional, TYPE_CHECKING
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from core.models.state import AgentState

if TYPE_CHECKING:
    from adapters.figma.figma_adapter import FigmaAdapter



class BridgePlan(BaseModel):
    bridge_steps: list = Field(
        description=(
            "Ordered list of navigation steps to move from the current screen "
            "to the required starting screen for the next scenario. "
            "Each step is a plain string instruction like 'click Back' or 'click Home button'."
        )
    )
    reasoning: str = Field(
        description="Brief explanation of why these steps are needed."
    )


class FigmaFlowPlan(BaseModel):
    path_ids: list = Field(
        description=(
            "The ordered list of Figma Node IDs (e.g. ['10:5', '12:1']) that represent "
            "the full prototype flow from the start screen to the expected end screen "
            "for this scenario. Return an empty list if no path can be resolved."
        )
    )
    reasoning: str = Field(
        description="Brief explanation of why this start screen and flow were chosen."
    )



BRIDGE_SYSTEM_PROMPT = """You are the Orchestrator Agent in a MAS AI Android testing framework.

Your task is to generate a short sequence of navigation steps to transition the app
from its CURRENT screen to the REQUIRED STARTING SCREEN of the next test scenario.

Use only these action types in your steps:
- "click <element name>"
- "press back"
- "press home"
- "scroll up" / "scroll down"

Be minimal. Generate only what is strictly necessary to reach the target screen.
"""



class PredefinedOrchestrator:
    """
    Orchestrator for the Predefined (Scenario-Based) workflow.

    Responsibilities:
    - Manage step index and retry logic based on Reflector feedback.
    - Discover Figma nodes before each scenario.
    - Compute bridge navigation steps between consecutive scenarios.
    """

    def __init__(self, llm=None, figma_adapter=None):
        self.llm = llm
        self.figma: Optional["FigmaAdapter"] = figma_adapter
        self._bridge_llm = llm.with_structured_output(BridgePlan) if llm else None
        self._mapping_llm = llm.with_structured_output(FigmaFlowPlan) if llm else None
    def pre_scenario_discovery(self, scenario: dict, output_dir: str) -> dict:
        """
        Analyzes the Figma prototype flow and test scenario to determine
        the start screen and the expected path.
        """
        figma_enabled = self.figma is not None
        if not figma_enabled:
            return {
                "figma_enabled": False,
                "figma_start_node_id": "",
                "figma_end_node_id": "",
                "figma_end_screenshot_b64": "",
                "figma_bridge_steps": [],
            }

        menu_name = scenario.get("navigation_context", "")
        scenario_desc = scenario.get("scenario_desc", "")
        sub_steps_raw = "\n".join([f"- {s}" for s in scenario.get("sub_steps", [])])

        flow_summary = self.figma.get_flow_summary()

        system_prompt = (
            "You are the Orchestrator Agent in a MAS AI Android testing framework.\n"
            "Your task is to analyze a Figma prototype flow and a test scenario to "
            "determine the correct sequence of screens (frames) the app should pass through.\n\n"
            "RULES:\n"
            "1. Identify the 'Start' frame that matches the scenario's menu context.\n"
            "2. Follow the connections (transitions) in the Figma file to reach the 'End' frame "
            "that fulfills the scenario's expected result.\n"
            "3. Return the full path of Node IDs in chronological order."
        )

        human_content = (
            f"TEST SCENARIO:\n"
            f"  Menu Context: {menu_name}\n"
            f"  Description: {scenario_desc}\n"
            f"  Test Steps:\n{sub_steps_raw}\n\n"
            f"FIGMA PROTOTYPE GRAPH:\n{flow_summary}"
        )

        print(f"[Predefined] Planning Figma flow for '{menu_name}'...")
        try:
            result = self._mapping_llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_content)
            ])
            
            if not result.path_ids:
                print("[Predefined] LLM could not resolve a Figma path. Falling back to text-only.")
                return {"figma_enabled": False}

            start_id = result.path_ids[0]
            end_id = result.path_ids[-1]
            print(f"[Predefined] Flow Planned: {result.path_ids} ({result.reasoning})")

            # Capture the end-state screenshot for the Reflector
            figma_end_screenshot_b64 = self.figma.get_node_screenshot_b64(end_id)

            # Generate the composite "Gold Standard" image
            gold_standard_path = os.path.join(output_dir, "figma_gold_standard.png")
            self.figma.save_composite_gold_standard(result.path_ids, gold_standard_path)

            return {
                "figma_enabled": True,
                "figma_start_node_id": start_id,
                "figma_end_node_id": end_id,
                "figma_end_screenshot_b64": figma_end_screenshot_b64,
                "figma_bridge_steps": [],
            }
        except Exception as e:
            print(f"[Predefined] Figma flow planning failed: {e}")
            return {"figma_enabled": False}

    # ------------------------------------------------------------------
    # Bridge Navigation
    # ------------------------------------------------------------------

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

        messages = [
            SystemMessage(content=BRIDGE_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ]

        print(f"[Predefined] Computing navigation bridge to '{next_screen_name}'...")
        try:
            result = self._bridge_llm.invoke(messages)
            print(f"[Predefined] Bridge plan: {result.bridge_steps}")
            return result.bridge_steps
        except Exception as e:
            print(f"[Predefined] Bridge computation failed: {e}")
            return []

    # ------------------------------------------------------------------
    # LangGraph Node
    # ------------------------------------------------------------------

    def orchestrate(self, state: AgentState) -> dict:
        """LangGraph node: index-manager that advances or retries sub-steps."""
        sub_steps = state.get("sub_steps", [])
        current_idx = state.get("current_sub_step_index", 0)
        global_step = state.get("current_step", 0)
        output_dir = state.get("output_dir", "outputs")
        retry_count = state.get("step_retry_count", 0)

        last_passed = state.get("last_reflector_passed", True)
        sender = state.get("sender", "START")

        if sender in ["reflector", "recorder"]:
            if last_passed:
                current_idx += 1
                retry_count = 0
            else:
                retry_count += 1
                print(f"[Predefined] Step failure. Retry attempt {retry_count}/3 for index {current_idx}")

        if retry_count > 3:
            print("[Predefined] Maximum retries exceeded. Aborting scenario.")
            return {
                "is_completed": True,
                "sender": "orchestrator",
                "stagnation_count": 99,
            }

        update_data = {
            "current_sub_step_index": current_idx,
            "current_step": global_step + 1,
            "step_retry_count": retry_count,
            "sender": "orchestrator",
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
        else:
            update_data["is_completed"] = True
            print("[Predefined] All steps verified. Scenario success.")

        return update_data
