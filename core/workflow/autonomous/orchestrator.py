import os
from typing import TYPE_CHECKING, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import Command
from pydantic import BaseModel, Field

from core.models.state import AgentState
from core.utils.output_manager import build_step_dir
from core.utils.process_logger import LogLevel as _LL
from shared.prompts.orchestrator_prompts import FEW_SHOT_EXAMPLES

if TYPE_CHECKING:
    from memory.meta_manager import MIRIXMemorySystem


class AutonomousPlan(BaseModel):
    """Chain-of-Thought: reasoning MUST be first field to force LLM to analyze before deciding."""

    reasoning: str = Field(
        description="Analyze SENDER and action history step-by-step before selecting the next action."
    )
    action_type: str = Field(
        description="The judge's decision: 'OBSERVE', 'DECIDE', 'EXECUTE', 'VERIFY', or 'COMPLETE'."
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


AUTONOMOUS_SYSTEM_PROMPT = """You are the Orchestrator Agent in a MAS AI Android testing framework.

Your goal is to achieve the following TASK: "{task_goal}"

You must satisfy the ULTIMATE EXPECTED RESULT: "{expected_result}"
Do NOT declare COMPLETE or set is_completed=True unless the ULTIMATE EXPECTED RESULT is fully met.

REASONING PROCESS (Chain of Thought):
Before selecting the next agent, you MUST analyze the situation step-by-step:
1. What was the last agent (SENDER) and what did they report/achieve?
2. Did the last action succeed or fail based on the action history and reflector feedback?
3. What is the logical next step to make progress toward the ULTIMATE EXPECTED RESULT?

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
    - OUT: verification judgment
- 'COMPLETE'
    - Purpose: To signal that the ULTIMATE EXPECTED RESULT has been fully satisfied and finalize the run.

MANDATORY DISPATCH RULES — follow these exactly, they override all other reasoning:
1. SENDER=executor → You MUST dispatch OBSERVE next. NEVER dispatch EXECUTE or DECIDE after EXECUTE without an OBSERVE in between. The screen state has changed and MUST be re-read.
2. SENDER=observer → You SHOULD dispatch DECIDE next (unless this OBSERVE was a recovery re-check after failed VERIFY, in which case dispatch DECIDE to replan).
3. SENDER=decider → You SHOULD dispatch EXECUTE next to carry out the action plan.
4. After a full OBSERVE→DECIDE→EXECUTE→OBSERVE cycle that confirms progress: dispatch VERIFY to validate the result against the ULTIMATE EXPECTED RESULT.
5. SENDER=reflector AND passed=True → If task is fully complete, dispatch COMPLETE. If more sub-tasks remain, dispatch OBSERVE to continue.
6. SENDER=reflector AND passed=False → dispatch OBSERVE to re-evaluate the screen, then recover.

CRITICAL RULE: If the SENDER is 'reflector' and the Reflector FAILED, you MUST continue the workflow
to recover — DO NOT dispatch COMPLETE until the ULTIMATE EXPECTED RESULT is met.

IMPORTANT: The DECIDE agent produces exactly ONE physical action per call. Write next_step_instruction as a single atomic action (e.g., "Tap the FAB button"), not a multi-step sequence.
"""


class AutonomousOrchestrator:
    """
    Orchestrator for the Autonomous (Goal-Based) workflow.

    Responsibilities:
    - Use an LLM to plan the next step based on the current screen, history,
      and optionally the Figma Gold Standard.
    - Discover Figma nodes before each scenario to provide a visual baseline.
    """

    def __init__(self, llm=None, figma_adapter=None, memory=None, logger=None):
        self.llm = llm
        self.figma = figma_adapter
        self.memory: Optional["MIRIXMemorySystem"] = memory
        self.logger = logger
        self._planner_llm = llm.with_structured_output(AutonomousPlan) if llm else None
        self._mapping_llm = llm.with_structured_output(FigmaFlowPlan) if llm else None

    def _log(self, msg: str, detail: str = "", level=None):
        if self.logger is not None:
            lvl = level if level is not None else _LL.INFO
            self.logger.log("ORCHESTRATOR", msg, detail, level=lvl)

    def pre_scenario_discovery(self, scenario: dict, output_dir: str) -> dict:
        """
        Fair Experiment: Provide Autonomous mode with the same Figma Gold Standard
        as Predefined mode.

        Returns figma_context dict passed to memory.init_session().
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

        print(f"[Autonomous] Planning Figma flow for '{menu_name}'...")
        try:
            result = self._mapping_llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_content),
                ]
            )

            if not result.path_ids:
                print(
                    "[Autonomous] LLM could not resolve a Figma path. Falling back to text-only."
                )
                return {
                    "figma_enabled": False,
                    "figma_start_node_id": "",
                    "figma_end_node_id": "",
                    "figma_end_screenshot_b64": "",
                }

            start_id = result.path_ids[0]
            end_id = result.path_ids[-1]
            print(f"[Autonomous] Flow Planned: {result.path_ids} ({result.reasoning})")

            figma_end_screenshot_b64 = self.figma.get_node_screenshot_b64(end_id)
            figma_dir = os.path.join(output_dir, "figma")
            os.makedirs(figma_dir, exist_ok=True)
            gold_standard_path = os.path.join(figma_dir, "gold_standard.png")
            self.figma.save_composite_gold_standard(result.path_ids, gold_standard_path)

            return {
                "figma_enabled": True,
                "figma_start_node_id": start_id,
                "figma_end_node_id": end_id,
                "figma_end_screenshot_b64": figma_end_screenshot_b64,
            }
        except Exception as e:
            print(f"[Autonomous] Figma flow planning failed: {e}")
            return {
                "figma_enabled": False,
                "figma_start_node_id": "",
                "figma_end_node_id": "",
                "figma_end_screenshot_b64": "",
            }

    def orchestrate(self, state: AgentState) -> dict:
        """LangGraph node: LLM-driven planner that generates the next subgoal."""
        tcs_id = state.get("tcs_id", "")
        global_step = state.get("current_step", 0)
        output_dir = state.get("output_dir", "outputs")
        sender = state.get("sender", "START")
        last_reflector_passed = state.get("last_reflector_passed", True)

        if self.logger is not None:
            self.logger.section(f"CYCLE {global_step} — ORCHESTRATOR (autonomous)")
        self._log(
            f"Entered from sender={sender}",
            f"last_reflector_passed={last_reflector_passed}",
        )

        steps_completed_count = state.get("steps_completed_count", 0)
        if sender == "reflector" and last_reflector_passed:
            steps_completed_count += 1

        task_goal = ""
        expected_result = ""
        figma_info = ""
        reference_path = ""
        reflector_feedback = ""
        recent_episodes_str = "None"

        if self.memory is not None:
            task_goal = (
                self.memory.core.get("task_goal")
                or self.memory.core.get("scenario_desc")
                or ""
            )
            expected_result = self.memory.core.get("expected_result") or ""
            figma_enabled = (self.memory.core.get("figma_enabled") or "False") == "True"

            if figma_enabled:
                figma_info = f"\nFIGMA DESIGN AWARENESS: You have a Gold Standard screenshot for the final goal state."

            sub_steps = self.memory.procedural.get_steps(tcs_id, "workflow")
            if sub_steps:
                numbered = "\n".join(
                    [f"  {i + 1}. {s}" for i, s in enumerate(sub_steps)]
                )
                reference_path = (
                    f"\nREFERENCE TEST PATH (defined by the test designer):\n{numbered}\n"
                    f"These steps describe the expected human tester behavior for this scenario. "
                    f"You are not required to follow them."
                )

            if sender == "reflector" and not last_reflector_passed:
                last_ref = self.memory.episodic.last_by_actor("reflector")
                if last_ref:
                    reflector_feedback = (
                        f"\n\n[!] REFLECTOR FEEDBACK — VERIFICATION FAILED:\n"
                        f"{last_ref.details or last_ref.summary}\n"
                        f"You MUST continue the workflow to recover. Do NOT dispatch COMPLETE yet."
                    )

            recent = self.memory.episodic.last(10)
            if recent:
                exec_eps = [
                    ep for ep in recent if ep.actor in ("executor", "reflector")
                ][-5:]
                if exec_eps:
                    lines = [
                        f"  step={ep.step} [{ep.actor}] {ep.event_type}: {ep.summary}"
                        for ep in exec_eps
                    ]
                    recent_episodes_str = "\n".join(lines)

        raw_observer_analysis = state.get("observer_analysis", "No analysis yet.")
        observer_analysis_step = state.get("observer_analysis_step", -1)

        steps_stale = (
            global_step - observer_analysis_step if observer_analysis_step >= 0 else 0
        )
        if steps_stale > 1:
            staleness_label = f"[WARNING: STALE — captured {steps_stale} steps ago. Dispatch OBSERVE first to refresh.]\n"
        else:
            staleness_label = ""
        observer_analysis = staleness_label + raw_observer_analysis

        human_content = (
            f"SENDER (Agent who just finished): {sender}\n"
            f"TASK GOAL: {task_goal}{reference_path}{figma_info}"
            f"{reflector_feedback}\n\n"
            f"CURRENT SCREEN ANALYSIS:\n{observer_analysis}\n\n"
            f"RECENT ACTION HISTORY (last 5):\n{recent_episodes_str}"
        )

        messages = [
            SystemMessage(
                content=AUTONOMOUS_SYSTEM_PROMPT.format(
                    task_goal=task_goal,
                    expected_result=expected_result,
                )
            ),
        ]
        for role, content in FEW_SHOT_EXAMPLES:
            if role == "human":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=human_content))

        print("[Autonomous] Planning next step...")
        self._log("LLM call started (AutonomousPlan generation)")
        try:
            plan = None
            last_plan_error = None
            for _attempt in range(2):
                try:
                    plan = self._planner_llm.invoke(messages)
                    if plan is not None:
                        break
                except Exception as _plan_e:
                    last_plan_error = _plan_e
                    err_str = str(_plan_e)
                    # Only retry on JSON/parsing errors; re-raise others immediately
                    if (
                        "json_invalid" not in err_str
                        and "Invalid JSON" not in err_str
                        and "missing" not in err_str.lower()
                    ):
                        raise
                    if _attempt == 0:
                        print(
                            f"[Autonomous] JSON parse error on planning, retrying once: {_plan_e}"
                        )
                        messages.append(
                            AIMessage(
                                content="IMPORTANT: Return ONLY a valid JSON object with ALL required fields. No XML tags."
                            )
                        )
            if plan is None:
                raise last_plan_error or Exception(
                    "Planner returned None after retries"
                )

            step_dir = build_step_dir(output_dir, global_step + 1)

            print(f"[Autonomous] JUDGMENT: {plan.action_type.upper()}")
            print(
                f"[Autonomous] Plan: '{plan.next_step_instruction}' | Completed: {plan.is_completed}"
            )
            self._log(
                f"→ JUDGMENT: {plan.action_type.upper()}  completed={plan.is_completed}",
                f"instruction={plan.next_step_instruction}\nreasoning={plan.reasoning}",
            )

            node_map = {
                "OBSERVE": "observer_node",
                "DECIDE": "decider_node",
                "EXECUTE": "executor_node",
                "ACT": "executor_node",
                "VERIFY": "reflector_node",
            }
            target_node = node_map.get(plan.action_type.upper(), "observer_node")

            is_first_verify = not (sender == "reflector" and not last_reflector_passed)

            if plan.is_completed or plan.action_type.upper() == "COMPLETE":
                target_node = "__end__"

            last_calls = state.get("last_agent_calls", [])
            last_calls.append(plan.action_type.upper())
            last_calls = last_calls[-5:]

            is_looping = (
                len(last_calls) >= 3
                and last_calls[-1] == last_calls[-2] == last_calls[-3]
            )

            if is_looping:
                print(
                    f"[Autonomous] KILL SWITCH: Detected loop of 3 {plan.action_type.upper()} calls. Stopping."
                )
                self._log(
                    f"KILL SWITCH — loop of 3 {plan.action_type.upper()} calls detected"
                )
                if self.memory is not None:
                    self.memory.update(
                        {
                            "episodic": {
                                "event_type": "orchestrator_decision",
                                "summary": f"KILL SWITCH: Loop of 3 {plan.action_type.upper()} calls.",
                                "details": "",
                                "actor": "orchestrator",
                                "step": global_step,
                            }
                        }
                    )
                return Command(
                    goto="__end__",
                    update={
                        "is_completed": False,
                        "sender": "orchestrator",
                        "stagnation_count": state.get("stagnation_count", 0) + 3,
                    },
                )

            if global_step >= 35:
                print(
                    f"[Autonomous] KILL SWITCH: Global step limit (35) reached. Stopping."
                )
                return Command(
                    goto="__end__",
                    update={
                        "is_completed": False,
                        "sender": "orchestrator",
                        "stagnation_count": state.get("stagnation_count", 0) + 3,
                    },
                )

            print(f"[Autonomous] DISPATCHING TO: {target_node}")

            if self.memory is not None:
                self.memory.update(
                    {
                        "episodic": {
                            "event_type": "orchestrator_decision",
                            "summary": f"Dispatch {plan.action_type.upper()}: {plan.next_step_instruction[:120]}",
                            "details": plan.reasoning,
                            "actor": "orchestrator",
                            "step": global_step + 1,
                        }
                    }
                )

            is_final = plan.is_completed or plan.action_type.upper() == "COMPLETE"
            return Command(
                goto=target_node,
                update={
                    "orchestrator_instruction": plan.next_step_instruction,
                    "current_sub_step_index": 0,
                    "current_step": global_step + 1,
                    "is_completed": is_final,
                    "is_final_step": is_final,
                    "next_agent": plan.action_type.upper(),
                    "last_agent_calls": last_calls,
                    "step_dir": step_dir,
                    "sender": "orchestrator",
                    "is_first_verify_attempt": is_first_verify,
                    "steps_completed_count": steps_completed_count,
                },
            )
        except Exception as e:
            print(f"[Autonomous] Planning failed: {e}")
            self._log("Planning failed — aborting run", str(e), level=_LL.ERROR)
            return Command(
                goto="__end__",
                update={
                    "is_completed": False,
                    "sender": "orchestrator",
                },
            )
