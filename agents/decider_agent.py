import json
import os
from typing import Literal
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.types import Command
from core.models.state import AgentState
from core.utils.toons_helper import compress_and_report
from langchain_core.prompts import ChatPromptTemplate
from shared.prompts.decider_prompts import SYSTEM_PROMPT, FEW_SHOT_EXAMPLES
from core.utils.process_logger import LogLevel as _LL


class ActionPlan(BaseModel):
    """Chain-of-Thought: reasoning MUST be first field to force LLM to think before acting."""
    reasoning: str = Field(
        description="Step-by-step thinking: 1) Intent analysis 2) UI element mapping 3) Action selection 4) Target verification."
    )
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


# SYSTEM_PROMPT imported from shared.prompts.decider_prompts


class DeciderAgent:
    def __init__(self, llm, memory=None, logger=None, monitor=None):
        self.llm = llm.with_structured_output(ActionPlan)
        self.memory = memory
        self.logger = logger
        self.monitor = monitor
        # Build prompt with Chain of Thought + General Knowledge Prompting
        # Includes few-shot examples to lock output format
        prompt_messages = [("system", SYSTEM_PROMPT)]
        for role, content in FEW_SHOT_EXAMPLES:
            prompt_messages.append((role, content))
        prompt_messages.append(("human",
             "Session Memory Context:\n{memory_context}\n\n"
             "Screen Analysis:\n{observer_analysis}\n\n"
             "STEP INSTRUCTION: \"{current_sub_step}\"\n\n"
             "Output ONE ActionPlan for the STEP INSTRUCTION."))
        self.prompt = ChatPromptTemplate.from_messages(prompt_messages)

    def _log(self, msg: str, detail: str = "", level=None):
        if self.logger is not None:
            lvl = level if level is not None else _LL.INFO
            self.logger.log("DECIDER", msg, detail, level=lvl)

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
        self._log("Memory retrieval complete", level=_LL.DEBUG)

        messages = self.prompt.format_messages(
            memory_context=memory_context or "No memory context available.",
            observer_analysis=state.get("observer_analysis", "N/A"),
            current_sub_step=current_sub_step,
        )

        print(f"[Decider] Mapping Instruction: '{current_sub_step}'...")
        self._log("LLM call started (ActionPlan generation)", level=_LL.DEBUG)
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
