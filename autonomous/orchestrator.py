import os
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from core.models.state import AgentState


# ---------------------------------------------------------------------------
# Pydantic Model
# ---------------------------------------------------------------------------

class AutonomousPlan(BaseModel):
    next_step_instruction: str = Field(
        description=(
            "The next concrete instruction for the agents to perform "
            "(e.g. 'Click the Login button')."
        )
    )
    is_completed: bool = Field(
        description="Set to True if the overall task goal has been achieved."
    )
    reasoning: str = Field(
        description="Brief explanation of why this step was chosen toward the goal."
    )


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

AUTONOMOUS_SYSTEM_PROMPT = """You are the Orchestrator Agent in a MAS AI Android testing framework.

Your goal is to achieve the following TASK: "{task_goal}"

Based on the CURRENT SCREEN analysis and the ACTION HISTORY, decide the NEXT single concrete step to take.
If the overall task goal is fully achieved, set is_completed=True.
"""


# ---------------------------------------------------------------------------
# AutonomousOrchestrator
# ---------------------------------------------------------------------------

class AutonomousOrchestrator:
    """
    Orchestrator for the Autonomous (Goal-Based) workflow.

    Responsibilities:
    - Use an LLM to plan the next step based on the current screen, history, 
      and optionally the Figma Gold Standard.
    - Discover Figma nodes before each scenario to provide a visual baseline.
    """

    def __init__(self, llm=None, figma_adapter=None):
        self.llm = llm
        self.figma = figma_adapter
        self._planner_llm = llm.with_structured_output(AutonomousPlan) if llm else None
        self._mapping_llm = llm.with_structured_output(FigmaMappingPlan) if llm else None # Added

    def _auto_discover_figma_node(self, menu_name: str, scenario_desc: str) -> Optional[str]:
        """Ask the LLM to match the scenario's menu context to a Figma frame."""
        if not self.figma or not self._mapping_llm:
            return None

        frames = self.figma.get_all_frames()
        if not frames:
            print("[Autonomous] No frames returned from Figma, cannot auto-discover.")
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

        print(f"[Autonomous] Auto-discovering Figma node for '{menu_name}'...")
        try:
            result = self._mapping_llm.invoke(messages)
            if result.node_id:
                print(f"[Autonomous] Auto-discovered: '{result.frame_name}' ({result.node_id}) — {result.reasoning}")
                return result.node_id
            else:
                print(f"[Autonomous] LLM could not find a matching frame for '{menu_name}'.")
                return None
        except Exception as e:
            print(f"[Autonomous] Auto-discovery failed: {e}")
            return None

    def pre_scenario_discovery(self, scenario: dict, output_dir: str) -> dict:
        """
        Fair Experiment: Provide Autonomous mode with the same Figma Gold Standard 
        as the Predefined mode.
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
        sub_steps = scenario.get("sub_steps", []) # Optional for autonomous, but helps tracing end node
        scenario_desc = scenario.get("scenario_desc", "")

        figma_start_node_id = self.figma.find_flow_start_node(menu_name)
        if not figma_start_node_id:
            figma_start_node_id = self._auto_discover_figma_node(menu_name, scenario_desc)

        if not figma_start_node_id:
            return {"figma_enabled": False}

        # Even in autonomous, we trace the 'expected' path from the scenario to find the Gold Standard
        figma_end_node_id = self.figma.trace_prototype_path(figma_start_node_id, sub_steps)

        if not figma_end_node_id:
            return {"figma_enabled": False, "figma_start_node_id": figma_start_node_id}

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

    def orchestrate(self, state: AgentState) -> dict:
        """LangGraph node: LLM-driven planner that generates the next subgoal."""
        task_goal        = state.get("task_goal", "")
        observer_analysis = state.get("observer_analysis", "No analysis yet.")
        history          = state.get("action_history", [])
        global_step      = state.get("current_step", 0)
        output_dir       = state.get("output_dir", "outputs")
        
        # Fair Experiment: Provide awareness of the Figma Gold Standard if available
        figma_enabled = state.get("figma_enabled", False)
        figma_info = ""
        if figma_enabled:
            figma_info = f"\nFIGMA DESIGN AWARENESS: You have a Gold Standard screenshot for the final goal state."

        human_content = (
            f"TASK GOAL: {task_goal}{figma_info}\n\n"
            f"CURRENT SCREEN ANALYSIS:\n{observer_analysis}\n\n"
            f"ACTION HISTORY (last 5):\n{history[-5:] if history else 'None'}"
        )

        messages = [
            SystemMessage(content=AUTONOMOUS_SYSTEM_PROMPT.format(task_goal=task_goal)),
            HumanMessage(content=human_content),
        ]

        print("[Autonomous] Planning next step...")
        try:
            plan = self._planner_llm.invoke(messages)

            step_dir = os.path.join(output_dir, f"step_{global_step + 1}")
            if not os.path.exists(step_dir):
                os.makedirs(step_dir)

            print(f"[Autonomous] Plan: '{plan.next_step_instruction}' | Completed: {plan.is_completed}")

            return {
                "sub_steps":             [plan.next_step_instruction],
                "current_sub_step_index": 0,
                "current_step":          global_step + 1,
                "is_completed":          plan.is_completed,
                "orchestrator_reasoning": plan.reasoning,
                "step_dir":              step_dir,
                "sender":                "orchestrator",
            }
        except Exception as e:
            print(f"[Autonomous] Planning failed: {e}")
            return {"is_completed": True, "sender": "orchestrator"}
