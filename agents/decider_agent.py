import json
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
from core.models.state import AgentState
from core.utils.toons_helper import compress_and_report


class ActionPlan(BaseModel):
    action_type: Literal[
        "click", "long_click", "input", "scroll",
        "press_back", "press_home", "press_enter", "start_app"
    ]
    intent: str = Field(
        description="Brief description of what this action aims to achieve toward the overall goal."
    )
    target_id: int = Field(
        description="The integer ID of the widget from the Observer's list. Use -1 if no specific widget."
    )
    text_payload: str = Field(
        default="",
        description="Text to type into the input field. Required if action_type is 'input', empty otherwise."
    )
    scroll_direction: str = Field(
        default="",
        description="Scroll direction: 'up' | 'down' | 'left' | 'right'. Required if action_type is 'scroll'."
    )
    app_package: str = Field(
        default="",
        description="App package name (e.g. 'com.tokopedia.tkpd'). Required if action_type is 'start_app'."
    )
    is_completed: bool = Field(
        description="True if the overall goal has been fully achieved and no further actions are needed."
    )


SYSTEM_PROMPT = """You are the Decider Agent in an Android GUI testing multi-agent system.

Your role: Given the current screen state, output exactly ONE ActionPlan for the Executor.

RULES:
- target_id MUST be an integer ID from the SEMANTIC_MAP, or -1.
- PREFER 'input' for typing. Set text_payload and target_id to the input field's ID. NEVER try to "click" individual keyboard keys.
- For 'scroll': set scroll_direction, target_id = -1.
- For 'start_app': set app_package.
- Set is_completed=True ONLY when the full goal is achieved."""


class DeciderAgent:
    def __init__(self, llm):
        self.llm = llm.with_structured_output(ActionPlan)

    def decide(self, state: AgentState) -> Command:
        # Compress action history with TOONS — uniform dict keys enable tabular compression.
        history_window = (state["action_history"] or [])[-10:]
        history_json = compress_and_report(history_window, "action_history", "decider") if history_window else "[]"
        subgoal = state.get("current_subgoal", "") or "Determine and execute the next best action toward the goal."

        human_prompt = (
            f"Goal: {state['task_goal']}\n"
            f"Subgoal: {subgoal}\n\n"
            f"Screen Analysis (Semantic Map):\n{state.get('observer_analysis', 'N/A')}\n\n"
            f"Recent Actions: {history_json}\n\n"
            f"Output ONE ActionPlan."
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ]

        print("[Decider] Thinking about the next action...")
        plan = self.llm.invoke(
            messages,
            config={"tags": ["decider", f"step_{state.get('current_step', 0)}"]}
        )

        status = "COMPLETED" if plan.is_completed else (
            f"type={plan.action_type} | target_id={plan.target_id} | intent={plan.intent}"
        )
        print(f"[Decider] {status}")

        # Hand control back to the Orchestrator
        return Command(
            goto="orchestrator_node",
            update={
                "action_plan": plan.model_dump(),
                "is_completed": plan.is_completed,
                "sender": "decider",
            },
        )
