import os
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command
from core.models.state import AgentState


# ---------------------------------------------------------------------------
# Pydantic Model
# ---------------------------------------------------------------------------

class AutonomousPlan(BaseModel):
    action_type: str = Field(
        description="The judge's decision: 'OBSERVE', 'DECIDE', 'EXECUTE', 'VERIFY', 'RECORD', or 'COMPLETE'."
    )
    next_step_instruction: str = Field(
        description=(
            "If EXECUTE: The concrete instruction (e.g. 'Click Login'). "
            "If OBSERVE: What to look for. If COMPLETE: Summary."
        )
    )
    is_completed: bool = Field(
        description="Set to True only if the overall task goal has been achieved."
    )
    reasoning: str = Field(
        description="Brief explanation of the judgment."
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



AUTONOMOUS_SYSTEM_PROMPT = """You are the Orchestrator Agent in a MAS AI Android testing framework.

Your goal is to achieve the following TASK: "{task_goal}"

You must satisfy the ULTIMATE EXPECTED RESULT: "{expected_result}"
Do NOT declare COMPLETE or set is_completed=True unless the ULTIMATE EXPECTED RESULT is fully met.

As the central judge, you decide which agent to invoke next based on their specialized purposes and technical I/O:

- 'OBSERVE'
    - Purpose: To convert the visual screen state into a machine-readable semantic map.
    - IN: Screenshot
    - OUT: `observer_analysis`
- 'DECIDE'
    - Purpose: To translate the semantic map into a specific, structured technical plan.
    - IN: `observer_analysis`
    - OUT: `action_plan` (exactly ONE physical action)
- 'EXECUTE'
    - Purpose: To transform the technical plan into physical interaction with the Android device.
    - IN: `action_plan`
    - OUT: `execution_result`
- 'VERIFY'
    - Purpose: To critique the `execution_result` against the `task_goal` AND the ULTIMATE EXPECTED RESULT.
    - IN: `execution_result`
    - OUT: `reflector_reasoning`
- 'RECORD'
    - Purpose: To save the current `action_history` and dialogue into persistent report files.
    - IN: `action_history`
    - OUT: Interaction script and chat logs
- 'COMPLETE'
    - Purpose: To signal that the ULTIMATE EXPECTED RESULT has been fully satisfied and finalize the run.

MANDATORY DISPATCH RULES — follow these exactly, they override all other reasoning:
1. SENDER=executor → You MUST dispatch OBSERVE next. NEVER dispatch EXECUTE or DECIDE after EXECUTE without an OBSERVE in between. The screen state has changed and MUST be re-read.
2. SENDER=observer → You SHOULD dispatch DECIDE next (unless this OBSERVE was a recovery re-check after failed VERIFY, in which case dispatch DECIDE to replan).
3. SENDER=decider → You SHOULD dispatch EXECUTE next to carry out the action plan.
4. After a full OBSERVE→DECIDE→EXECUTE→OBSERVE cycle that confirms progress: dispatch VERIFY to validate the result against the ULTIMATE EXPECTED RESULT.
5. SENDER=reflector AND passed=True → If task is fully complete, dispatch RECORD then COMPLETE. If more sub-tasks remain, dispatch OBSERVE to continue.
6. SENDER=reflector AND passed=False → dispatch OBSERVE to re-evaluate the screen, then recover.

CRITICAL RULE: If the SENDER is 'reflector' and the Reflector FAILED, you MUST continue the workflow
to recover — DO NOT dispatch to RECORD or COMPLETE until the ULTIMATE EXPECTED RESULT is met.

IMPORTANT: The DECIDE agent produces exactly ONE physical action per call. Write next_step_instruction as a single atomic action (e.g., "Tap the FAB button"), not a multi-step sequence.
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
        self._mapping_llm = llm.with_structured_output(FigmaMappingPlan) if llm else None

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

        try:
            print(f"[Autonomous] Auto-discovering Figma node for '{menu_name}'...")
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

        # LLM auto-discovery (The Orchestrator is the judge)
        figma_start_node_id = self._auto_discover_figma_node(menu_name, scenario_desc)

        if not figma_start_node_id:
            return {"figma_enabled": False}

        # Even in autonomous, we trace the 'expected' path from the scenario to find the Gold Standard
        # trace_prototype_path returns a list of node IDs — extract the final destination node.
        path_ids = self.figma.trace_prototype_path(figma_start_node_id, sub_steps)

        if not path_ids:
            return {"figma_enabled": False, "figma_start_node_id": figma_start_node_id}

        figma_end_node_id = path_ids[-1]

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
        task_goal         = state.get("task_goal", "")
        expected_result   = state.get("expected_result", "")
        raw_observer_analysis = state.get("observer_analysis", "No analysis yet.")
        observer_analysis_step = state.get("observer_analysis_step", -1)
        history           = state.get("action_history", [])
        global_step       = state.get("current_step", 0)
        output_dir        = state.get("output_dir", "outputs")
        sender            = state.get("sender", "START")
        last_reflector_passed = state.get("last_reflector_passed", True)
        reflector_reasoning   = state.get("reflector_reasoning", "")

        # Warn orchestrator when screen analysis is from a prior step
        steps_stale = global_step - observer_analysis_step if observer_analysis_step >= 0 else 0
        if steps_stale > 1:
            staleness_label = f"[WARNING: STALE — captured {steps_stale} steps ago. Dispatch OBSERVE first to refresh.]\n"
        else:
            staleness_label = ""
        observer_analysis = staleness_label + raw_observer_analysis

        # Fair Experiment: Provide awareness of the Figma Gold Standard if available
        figma_enabled = state.get("figma_enabled", False)
        figma_info = ""
        if figma_enabled:
            figma_info = f"\nFIGMA DESIGN AWARENESS: You have a Gold Standard screenshot for the final goal state."

        sub_steps = state.get("sub_steps", [])
        reference_path = ""
        if sub_steps:
            numbered = "\n".join([f"  {i+1}. {s}" for i, s in enumerate(sub_steps)])
            reference_path = (
                f"\nREFERENCE TEST PATH (defined by the test designer):\n{numbered}\n"
                f"These steps describe the expected human tester behavior for this scenario. "
                f"You are not required to follow them."
            )

        # Inject Reflector failure feedback when self-correction is needed
        reflector_feedback = ""
        if sender == "reflector" and not last_reflector_passed and reflector_reasoning:
            reflector_feedback = (
                f"\n\n[!] REFLECTOR FEEDBACK — VERIFICATION FAILED:\n"
                f"{reflector_reasoning}\n"
                f"You MUST continue the workflow to recover. Do NOT dispatch RECORD or COMPLETE yet."
            )

        human_content = (
            f"SENDER (Agent who just finished): {sender}\n"
            f"TASK GOAL: {task_goal}{reference_path}{figma_info}"
            f"{reflector_feedback}\n\n"
            f"CURRENT SCREEN ANALYSIS:\n{observer_analysis}\n\n"
            f"ACTION HISTORY (last 5):\n{history[-5:] if history else 'None'}"
        )

        messages = [
            SystemMessage(content=AUTONOMOUS_SYSTEM_PROMPT.format(
                task_goal=task_goal,
                expected_result=expected_result,
            )),
            HumanMessage(content=human_content),
        ]

        print("[Autonomous] Planning next step...")
        try:
            plan = self._planner_llm.invoke(messages)

            step_dir = os.path.join(output_dir, f"step_{global_step + 1}")
            if not os.path.exists(step_dir):
                os.makedirs(step_dir)

            print(f"[Autonomous] JUDGMENT: {plan.action_type.upper()}")
            print(f"[Autonomous] Plan: '{plan.next_step_instruction}' | Completed: {plan.is_completed}")

            # Map action_type to target graph nodes
            node_map = {
                "OBSERVE": "observer_node",
                "DECIDE":  "decider_node",
                "EXECUTE": "executor_node",
                "ACT":     "executor_node",
                "VERIFY":  "reflector_node",
                "RECORD":  "recorder_node",
            }
            target_node = node_map.get(plan.action_type.upper(), "observer_node")
            if plan.is_completed or plan.action_type == "COMPLETE":
                target_node = "__end__"

            # Loop Detection Kill Switch
            last_calls = state.get("last_agent_calls", [])
            last_calls.append(plan.action_type.upper())
            last_calls = last_calls[-5:]

            is_looping = False
            if len(last_calls) >= 3:
                if last_calls[-1] == last_calls[-2] == last_calls[-3]:
                    is_looping = True

            if is_looping:
                print(f"[Autonomous] KILL SWITCH: Detected loop of 3 {plan.action_type.upper()} calls. Stopping.")
                return Command(
                    goto="__end__",
                    update={
                        "is_completed": False,
                        "orchestrator_reasoning": f"Stagnation detected: Loop of 3 {plan.action_type.upper()} calls.",
                        "sender": "orchestrator",
                        "stagnation_count": state.get("stagnation_count", 0) + 3
                    }
                )

            # Global Step Limit Kill Switch
            # Each physical action requires at minimum 3 orchestrator steps (OBSERVE→DECIDE→EXECUTE).
            # A 5-step scenario needs ~35 orchestrator steps when VERIFY and RECORD are included.
            if global_step >= 35:
                print(f"[Autonomous] KILL SWITCH: Global step limit (35) reached. Stopping.")
                return Command(
                    goto="__end__",
                    update={
                        "is_completed": False,
                        "orchestrator_reasoning": "Global step limit (35) exceeded. Run aborted for safety.",
                        "sender": "orchestrator",
                        "stagnation_count": state.get("stagnation_count", 0) + 3
                    }
                )

            print(f"[Autonomous] DISPATCHING TO: {target_node}")

            is_final = plan.is_completed or plan.action_type == "COMPLETE"
            return Command(
                goto=target_node,
                update={
                    "orchestrator_instruction": plan.next_step_instruction,
                    "current_sub_step_index": 0,
                    "current_step":          global_step + 1,
                    "is_completed":          is_final,
                    "is_final_step":         is_final,
                    "orchestrator_reasoning": plan.reasoning,
                    "next_agent":            plan.action_type.upper(),
                    "last_agent_calls":      last_calls,
                    "step_dir":              step_dir,
                    "sender":                "orchestrator",
                }
            )
        except Exception as e:
            print(f"[Autonomous] Planning failed: {e}")
            return Command(
                goto="__end__",
                update={
                    "is_completed": True, 
                    "orchestrator_reasoning": f"Planning failed: {str(e)}",
                    "sender": "orchestrator"
                }
            )
