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
    - Use an LLM to plan the next step based on the current screen and history.
    - No Figma dependency — decisions are driven purely by real-time UI analysis.
    - No bridge navigation — the agent navigates continuously toward the goal.
    """

    def __init__(self, llm=None):
        self.llm = llm
        self._planner_llm = llm.with_structured_output(AutonomousPlan) if llm else None

    def orchestrate(self, state: AgentState) -> dict:
        """LangGraph node: LLM-driven planner that generates the next subgoal."""
        task_goal        = state.get("task_goal", "")
        observer_analysis = state.get("observer_analysis", "No analysis yet.")
        history          = state.get("action_history", [])
        global_step      = state.get("current_step", 0)
        output_dir       = state.get("output_dir", "outputs")

        human_content = (
            f"TASK GOAL: {task_goal}\n\n"
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
