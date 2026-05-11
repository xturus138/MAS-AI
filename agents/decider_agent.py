import json
import os
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
from core.models.state import AgentState
from core.utils.toons_helper import compress_and_report, prune_history_by_tokens
from langchain_core.prompts import ChatPromptTemplate

class ActionPlan(BaseModel):
    action_type: Literal[
        "click", "long_click", "input", "scroll",
        "press_back", "press_home", "press_enter", "start_app"
    ]
    intent: str = Field(
        description="Brief description of what this action aims to achieve toward the step instruction."
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
        description="Set to True if No Action can be safely determined."
    )

SYSTEM_PROMPT = """You are the Decider Agent in an Android GUI testing multi-agent system.

You are acting as a User Persona: {user_role}.
Navigation Context: {navigation_context}
Current Scenario: {scenario_desc}

Your task: You MUST translate this specific step instruction into exactly ONE ActionPlan.
STEP INSTRUCTION: "{current_sub_step}"

RULES:
- target_id MUST be an integer ID from the SEMANTIC_MAP, or -1.
- PREFER 'input' for typing. Set text_payload and target_id to the input field's ID.
- For 'scroll': set scroll_direction, target_id = -1.
- Set is_completed=True ONLY when the STEP INSTRUCTION cannot be mapped to any actions."""

class DeciderAgent:
    def __init__(self, llm):
        self.llm = llm.with_structured_output(ActionPlan)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", "Screen Analysis:\n{observer_analysis}\n\n"
                      "Recent Actions:\n{history_json}\n\n"
                      "Previous Attempt Feedback (if failed):\n{reflector_reasoning}\n\n"
                      "Output ONE ActionPlan for the STEP INSTRUCTION.")
        ])

    def decide(self, state: AgentState) -> Command:
        history = list(state.get("action_history") or [])
        history = prune_history_by_tokens(history, max_tokens=3000)
        history_json = compress_and_report(history, "action_history", "decider") if history else "[]"
        
        current_idx = state.get("current_sub_step_index", 0)
        sub_steps = state.get("sub_steps", [])
        orchestrator_instruction = state.get("orchestrator_instruction", "")
        current_sub_step = orchestrator_instruction if orchestrator_instruction else (
            sub_steps[current_idx] if current_idx < len(sub_steps) else "Finish Scenario"
        )

        messages = self.prompt.format_messages(
            user_role=state.get('user_role', 'N/A'),
            navigation_context=state.get('navigation_context', 'N/A'),
            scenario_desc=state.get('scenario_desc', 'N/A'),
            current_sub_step=current_sub_step,
            observer_analysis=state.get('observer_analysis', 'N/A'),
            history_json=history_json,
            reflector_reasoning=state.get('reflector_reasoning', 'None')
        )

        print(f"[Decider] Mapping Instruction: '{current_sub_step}'...")
        plan = self.llm.invoke(
            messages,
            config={"tags": ["decider", f"step_{state.get('current_step', 0)}"]}
        )

        step_dir = state.get("step_dir", "")
        if step_dir:
            plan_path = os.path.join(step_dir, "action_plan.json")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan.model_dump(), f, indent=4, ensure_ascii=False)

        status = "COMPLETED" if plan.is_completed else f"type={plan.action_type} | tid={plan.target_id}"
        print(f"[Decider] {status}")

        chat_entry = {
            "agent": "decider",
            "step": state.get("current_step", 0),
            "content": f"RESPONSE:\n{plan.model_dump_json(indent=2)}"
        }
        new_chat_logs = state.get("chat_logs", []) + [chat_entry]

        return {
            "action_plan": plan.model_dump(),
            "is_completed": plan.is_completed,
            "sender": "decider",
            "chat_logs": new_chat_logs
        }
