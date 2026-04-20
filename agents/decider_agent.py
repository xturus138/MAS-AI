from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
from core.models.state import AgentState


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

Your role is to receive the current screen state from the Observer and produce exactly ONE structured ActionPlan for the Executor.

HOW TO SELECT A TARGET:
1. Use the 'Screen Analysis' and 'Available UI Elements' to understand the UI semantics and layout.
2. Match the 'Subgoal' (from Orchestrator) to the most appropriate functional element.
3. Use that element's ID as the 'target_id'.

OUTPUT RULES:
- Produce exactly ONE ActionPlan.
- target_id MUST be an integer ID taken directly from the provided list, or -1.
- DO NOT guess or invent IDs outside the list.
- For 'input': set text_payload and target_id to the input field's ID.
- For 'scroll': set scroll_direction, target_id = -1.
- For 'start_app': set app_package.
- Set is_completed=True ONLY when the full goal is done."""


class DeciderAgent:
    def __init__(self, llm):
        self.llm = llm.with_structured_output(ActionPlan)

    def decide(self, state: AgentState) -> Command:
        history_text = "\n".join(state["action_history"]) if state["action_history"] else "None"
        subgoal = state.get("current_subgoal", "") or "Determine and execute the next best action toward the goal."

        human_prompt = (
            f"Goal: {state['task_goal']}\n\n"
            f"Subgoal (what to do NOW): {subgoal}\n\n"
            f"Screen Analysis (Semantic Map):\n{state.get('observer_analysis', 'N/A')}\n\n"
            f"Available UI Elements (ID | Class | Text):\n{state['ui_elements_summary']}\n\n"
            f"Action History:\n{history_text}\n\n"
            f"Select the element that matches the Subgoal and output ONE ActionPlan."
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ]

        print("[Decider] Thinking about the next action...")
        plan = self.llm.invoke(messages)

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
