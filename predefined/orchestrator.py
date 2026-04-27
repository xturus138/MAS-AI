import os
from typing import Optional, TYPE_CHECKING
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from core.models.state import AgentState

if TYPE_CHECKING:
    from adapters.figma.figma_adapter import FigmaAdapter


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

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


class FigmaMappingPlan(BaseModel):
    node_id: str = Field(
        description=(
            "The Figma Node ID (e.g. '10:5') of the frame that best matches "
            "the given test scenario menu/navigation context. "
            "Return an empty string if no suitable frame is found."
        )
    )
    frame_name: str = Field(
        description="The exact name of the matched Figma frame."
    )
    reasoning: str = Field(
        description="Brief explanation of why this frame was chosen."
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# PredefinedOrchestrator
# ---------------------------------------------------------------------------

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
        self._mapping_llm = llm.with_structured_output(FigmaMappingPlan) if llm else None

    # ------------------------------------------------------------------
    # Figma Discovery
    # ------------------------------------------------------------------

    def _auto_discover_figma_node(self, menu_name: str, scenario_desc: str) -> Optional[str]:
        """Ask the LLM to match the scenario's menu context to a Figma frame."""
        if not self.figma or not self._mapping_llm:
            return None

        frames = self.figma.get_all_frames()
        if not frames:
            print("[Predefined] No frames returned from Figma, cannot auto-discover.")
            return None

        frames_list = "\n".join([f"- Name: '{f['name']}', ID: '{f['id']}'" for f in frames])

        system_prompt = (
            "You are the Orchestrator Agent in a MAS AI Android testing framework.\n"
            "Your job is to identify which Figma frame corresponds to the starting screen "
            "of the given test scenario.\n"
            "You will be given a list of all frames from the Figma file. "
            "Select the one whose name best matches the test scenario's menu or navigation context.\n"
            "If no frame is a good match, return an empty string for node_id."
        )
        human_content = (
            f"TEST SCENARIO:\n"
            f"  Menu / Navigation Context: {menu_name}\n"
            f"  Description: {scenario_desc}\n\n"
            f"AVAILABLE FIGMA FRAMES:\n{frames_list}"
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_content),
        ]

        print(f"[Predefined] Auto-discovering Figma node for '{menu_name}'...")
        try:
            result = self._mapping_llm.invoke(messages)
            if result.node_id:
                print(f"[Predefined] Auto-discovered: '{result.frame_name}' ({result.node_id}) — {result.reasoning}")
                return result.node_id
            else:
                print(f"[Predefined] LLM could not find a matching frame for '{menu_name}'.")
                return None
        except Exception as e:
            print(f"[Predefined] Auto-discovery failed: {e}")
            return None

    def pre_scenario_discovery(self, scenario: dict, output_dir: str) -> dict:
        """
        Called before each scenario execution.
        Returns Figma context dict to be merged into the initial AgentState.
        """
        figma_enabled = self.figma is not None

        if not figma_enabled:
            print("[Predefined][Figma] Figma integration disabled. Skipping discovery.")
            return {
                "figma_enabled": False,
                "figma_start_node_id": "",
                "figma_end_node_id": "",
                "figma_end_screenshot_b64": "",
                "figma_bridge_steps": [],
            }

        menu_name = scenario.get("navigation_context", "")
        sub_steps = scenario.get("sub_steps", [])
        scenario_desc = scenario.get("scenario_desc", "")

        # Priority 1: Manual map from figma_map.json
        figma_start_node_id = self.figma.find_flow_start_node(menu_name)

        # Priority 2: LLM auto-discovery
        if not figma_start_node_id:
            figma_start_node_id = self._auto_discover_figma_node(menu_name, scenario_desc)

        if not figma_start_node_id:
            print(f"[Predefined][Figma] Could not resolve a node for '{menu_name}'. Falling back to text-only.")
            return {
                "figma_enabled": False,
                "figma_start_node_id": "",
                "figma_end_node_id": "",
                "figma_end_screenshot_b64": "",
                "figma_bridge_steps": [],
            }

        figma_end_node_id = self.figma.trace_prototype_path(figma_start_node_id, sub_steps)

        if not figma_end_node_id:
            print("[Predefined][Figma] WARN: Prototype path tracing failed, falling back to text-only.")
            return {
                "figma_enabled": False,
                "figma_start_node_id": figma_start_node_id,
                "figma_end_node_id": "",
                "figma_end_screenshot_b64": "",
                "figma_bridge_steps": [],
            }

        figma_end_screenshot_b64 = self.figma.get_node_screenshot_b64(figma_end_node_id)

        gold_standard_path = os.path.join(output_dir, "figma_gold_standard.png")
        self.figma.save_screenshot_to_file(figma_end_node_id, gold_standard_path)

        return {
            "figma_enabled": True,
            "figma_start_node_id": figma_start_node_id,
            "figma_end_node_id": figma_end_node_id,
            "figma_end_screenshot_b64": figma_end_screenshot_b64,
            "figma_bridge_steps": [],
        }

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
