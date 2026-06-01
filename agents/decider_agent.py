import json
import os
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
from core.models.state import AgentState
from core.utils.toons_helper import compress_and_report
from langchain_core.prompts import ChatPromptTemplate


class ActionPlan(BaseModel):
    action_type: Literal[
        "click", "long_click", "input", "scroll",
        "press_back", "press_home", "press_enter", "start_app", "none"
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

Your task: translate the given step instruction into exactly ONE ActionPlan.

RULES:
- target_id MUST be an integer ID from the SEMANTIC_MAP, or -1.
- For typing text into any field: ALWAYS use 'input' directly. The executor internally clicks/focuses the widget before typing — NEVER issue a separate 'click' to focus before 'input'. One action only.
- Set text_payload to the exact text to type and target_id to the input field's widget ID.
- For 'scroll': set scroll_direction, target_id = -1.
- Set is_completed=True ONLY when the STEP INSTRUCTION cannot be mapped to any actions. In this case, use 'none' as action_type."""


class DeciderAgent:
    def __init__(self, llm, memory=None, logger=None, monitor=None):
        self.llm = llm.with_structured_output(ActionPlan)
        self.memory = memory
        self.logger = logger
        self.monitor = monitor
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human",
             "Session Memory Context:\n{memory_context}\n\n"
             "Screen Analysis:\n{observer_analysis}\n\n"
             "STEP INSTRUCTION: \"{current_sub_step}\"\n\n"
             "Output ONE ActionPlan for the STEP INSTRUCTION.")
        ])

    def _log(self, msg: str, detail: str = ""):
        if self.logger is not None:
            self.logger.log("DECIDER", msg, detail)

    def decide(self, state: AgentState) -> Command:
        current_step = state.get("current_step", 0)
        orchestrator_instruction = state.get("orchestrator_instruction", "")
        tcs_id = state.get("tcs_id", "")

        # Resolve current instruction: autonomous uses orchestrator_instruction directly;
        # predefined falls back to procedural memory sub_steps at current index.
        if orchestrator_instruction:
            current_sub_step = orchestrator_instruction
        elif self.memory is not None:
            idx = state.get("current_sub_step_index", 0)
            sub_steps = self.memory.procedural.get_steps(tcs_id, "workflow")
            current_sub_step = sub_steps[idx] if idx < len(sub_steps) else "Finish Scenario"
        else:
            current_sub_step = "Finish Scenario"

        self._log(f"Step {current_step} — Instruction: {current_sub_step}")

        # ── Active Retrieval ──────────────────────────────────────────────────
        memory_context = state.get("memory_context", "")
        if self.memory is not None:
            memory_context = self.memory.retrieve(current_sub_step)
        self._log("Memory retrieval complete")

        messages = self.prompt.format_messages(
            memory_context=memory_context or "No memory context available.",
            observer_analysis=state.get("observer_analysis", "N/A"),
            current_sub_step=current_sub_step,
        )

        print(f"[Decider] Mapping Instruction: '{current_sub_step}'...")
        self._log("LLM call started (ActionPlan generation)")
        plan = self.llm.invoke(
            messages,
            config={"tags": ["decider", f"step_{current_step}"]}
        )

        step_dir = state.get("step_dir", "")
        if step_dir:
            plan_path = os.path.join(step_dir, "action_plan.json")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan.model_dump(), f, indent=4, ensure_ascii=False)

        status = "COMPLETED (no action)" if plan.is_completed else f"type={plan.action_type} | tid={plan.target_id}"
        print(f"[Decider] {status}")
        self._log(
            f"ActionPlan: {status}",
            f"intent={plan.intent}\n"
            f"text_payload={plan.text_payload!r}\n"
            f"scroll_direction={plan.scroll_direction!r}\n"
            f"app_package={plan.app_package!r}"
        )

        # ── Memory Update ─────────────────────────────────────────────────────
        if self.memory is not None:
            self.memory.update({
                "episodic": {
                    "event_type": "decision",
                    "summary": f"{plan.action_type} on widget {plan.target_id}: {plan.intent}",
                    "details": plan.model_dump_json(),
                    "actor": "decider",
                    "step": current_step,
                }
            })

        if self.logger is not None:
            self.logger.separator()

        if self.monitor is not None and not plan.is_completed:
            widgets = state.get("widgets", [])
            target_widget = next(
                (w for w in widgets if w.get("id") == plan.target_id), {}
            )
            self.monitor.on_decider(target_widget)

        return {
            "action_plan": plan.model_dump(),
            "is_completed": plan.is_completed,
            "memory_context": memory_context,
            "sender": "decider",
        }
