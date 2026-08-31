import json
import os
import re
import time
from typing import Literal, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langgraph.types import Command
from pydantic import BaseModel, Field

from core.models.state import AgentState
from core.utils.process_logger import LogLevel as _LL
from core.utils.toons_helper import compress_and_report
from shared.prompts.decider_prompts import FEW_SHOT_EXAMPLES, SYSTEM_PROMPT
from shared.utils.llm_utils import extract_json_str_from_llm_output


class ActionPlan(BaseModel):
    """Chain-of-Thought: reasoning MUST be first field to force LLM to think before acting."""

    reasoning: str = Field(
        description="Step-by-step thinking: 1) Intent analysis 2) UI element mapping 3) Action selection 4) Target verification."
    )
    action_type: Literal[
        "click",
        "long_click",
        "input",
        "scroll",
        "press_back",
        "press_home",
        "press_enter",
        "start_app",
        "none",
    ]
    intent: str = Field(
        description="Brief description of what this action aims to achieve toward the step instruction."
    )
    target_id: int = Field(
        description="The integer ID of the widget from the Observer's list. Use -1 if no specific widget."
    )
    text_payload: str = Field(
        default="",
        description="Text to type into the input field. Required if action_type is 'input', empty otherwise.",
    )
    scroll_direction: str = Field(
        default="",
        description="Scroll direction: 'up' | 'down' | 'left' | 'right'. Required if action_type is 'scroll'.",
    )
    app_package: str = Field(
        default="",
        description="App package name (e.g. 'com.tokopedia.tkpd'). Required if action_type is 'start_app'.",
    )
    is_completed: bool = Field(
        description="Set to True if No Action can be safely determined."
    )


class DeciderAgent:
    def __init__(self, llm, memory=None, logger=None, monitor=None):
        self.base_llm = llm
        self.llm = llm.with_structured_output(ActionPlan)
        self.memory = memory
        self.logger = logger
        self.monitor = monitor
        prompt_messages = [("system", SYSTEM_PROMPT)]
        for role, content in FEW_SHOT_EXAMPLES:
            prompt_messages.append((role, content))
        prompt_messages.append(
            (
                "human",
                "Session Memory Context:\n{memory_context}\n\n"
                "Screen Analysis:\n{observer_analysis}\n\n"
                'STEP INSTRUCTION: "{current_sub_step}"\n\n'
                "Output ONE ActionPlan for the STEP INSTRUCTION.",
            )
        )
        self.prompt = ChatPromptTemplate.from_messages(prompt_messages)

    def _log(self, msg: str, detail: str = "", level=None):
        if self.logger is not None:
            lvl = level if level is not None else _LL.INFO
            self.logger.log("DECIDER", msg, detail, level=lvl)

    def _extract_json_from_llm_output(self, raw_output: str) -> Optional[str]:
        """Delegate to shared JSON extraction utility."""
        return extract_json_str_from_llm_output(raw_output)

    def _extract_instruction_text(self, instruction: str) -> str:
        """Extract intended input text from Indonesian/English test instruction."""
        quoted = re.search(r'["“”\']([^"“”\']+)["“”\']', instruction)
        if quoted:
            return quoted.group(1).strip()

        patterns = [
            r"(?:memasukkan|masukkan|input|type|enter)\s+(?:konten|isi|judul|teks|text)?\s*[:：]?\s*(.+)$",
            r"(?:isi|judul)\s*[:：]\s*(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, instruction, flags=re.IGNORECASE)
            if match:
                return match.group(1).strip().strip(".").strip()
        return ""

    def _is_input_instruction(self, instruction: str) -> bool:
        return bool(
            re.search(
                r"\b(memasukkan|masukkan|input|type|enter|ketik)\b",
                instruction,
                flags=re.IGNORECASE,
            )
        )

    def _widget_text(self, widget: dict) -> str:
        return str(widget.get("text") or widget.get("label") or "").strip()

    def _find_input_widget(
        self, widgets: list[dict], preferred_id: int = -1
    ) -> Optional[dict]:
        if preferred_id != -1:
            preferred = next((w for w in widgets if w.get("id") == preferred_id), None)
            if preferred and preferred.get("role") == "input":
                return preferred

        focused_input = next(
            (
                w
                for w in widgets
                if w.get("role") == "input" and w.get("state", {}).get("focused")
            ),
            None,
        )
        if focused_input:
            return focused_input

        return next(
            (w for w in widgets if w.get("role") == "input" and w.get("actionable")),
            None,
        )

    def _find_done_widget(self, widgets: list[dict]) -> Optional[dict]:
        resource_keywords = ("send_button", "done_button", "save_button")
        exact_done_labels = {"selesai", "done", "save", "simpan", "kirim"}

        for widget in widgets:
            resource_id = str(widget.get("resource_id") or "").lower()
            if any(keyword in resource_id for keyword in resource_keywords):
                return widget

        for widget in widgets:
            label = self._widget_text(widget).strip().lower()
            if label in exact_done_labels:
                return widget
        return None

    def _guard_click_plan(
        self, plan: ActionPlan, instruction: str, widgets: list[dict]
    ) -> ActionPlan:
        """Resolve common unmapped completion clicks like Selesai/Done/Save."""
        if plan.action_type != "click" or plan.target_id != -1:
            return plan
        if not re.search(
            r"\b(selesai|done|save|simpan)\b", instruction, flags=re.IGNORECASE
        ):
            return plan

        target_widget = self._find_done_widget(widgets)
        if not target_widget:
            return plan

        return ActionPlan(
            reasoning=(
                f"Click-target guard: instruction asks for a completion action, and widget "
                f"[{target_widget.get('id')}] ({self._widget_text(target_widget) or target_widget.get('resource_id')}) "
                "matches Selesai/Done/Save."
            ),
            action_type="click",
            intent=plan.intent,
            target_id=int(target_widget.get("id", -1)),
            text_payload="",
            scroll_direction="",
            app_package="",
            is_completed=False,
        )

    def _guard_input_plan(
        self, plan: ActionPlan, instruction: str, widgets: list[dict]
    ) -> ActionPlan:
        """Prevent false completion when desired text appears outside editable input."""
        if not self._is_input_instruction(instruction):
            return plan

        payload = plan.text_payload.strip() or self._extract_instruction_text(
            instruction
        )
        if not payload:
            return plan

        target_widget = self._find_input_widget(widgets, plan.target_id)
        if not target_widget:
            return plan

        target_text = self._widget_text(target_widget)
        target_has_payload = payload.lower() in target_text.lower()

        if plan.action_type == "none" or plan.is_completed:
            if not target_has_payload:
                return ActionPlan(
                    reasoning=(
                        f"Input-step guard: instruction requires typing {payload!r}. "
                        f"Desired text is not present in editable input [{target_widget.get('id')}]; "
                        "text elsewhere on screen does not complete an input step."
                    ),
                    action_type="input",
                    intent=f"Enter required text into editable input: {payload}",
                    target_id=int(target_widget.get("id", -1)),
                    text_payload=payload,
                    scroll_direction="",
                    app_package="",
                    is_completed=False,
                )
        return plan

    @staticmethod
    def _is_rate_limit_error(error: Exception) -> bool:
        err_str = str(error)
        return (
            "429" in err_str
            or "rate" in err_str.lower()
            or "too many requests" in err_str.lower()
        )

    def _invoke_with_recovery(self, messages, current_step: int) -> ActionPlan:
        """Invoke structured LLM with automatic JSON extraction retry.

        Rate-limit (429) errors are retried with exponential backoff.
        """
        last_error = None
        rate_limit_backoff = 1.0

        for attempt in range(2):
            try:
                result = self.llm.invoke(
                    messages, config={"tags": ["decider", f"step_{current_step}"]}
                )
                if result is not None:
                    return result
                print(f"[Decider] Structured LLM returned None, attempting recovery...")
            except Exception as e:
                last_error = e

                if self._is_rate_limit_error(e):
                    if attempt < 1:
                        print(
                            f"[Decider] Rate limited (429), retrying in {rate_limit_backoff:.1f}s..."
                        )
                        time.sleep(rate_limit_backoff)
                        rate_limit_backoff = min(rate_limit_backoff * 2, 16.0)
                        continue
                    print(f"[Decider] Rate limited after retries: {e}")
                    break

                error_str = str(e)

                if "json_invalid" not in error_str and "Invalid JSON" not in error_str:
                    raise

                if attempt == 0:
                    try:
                        print(f"[Decider] Attempting JSON recovery...")
                        raw_response = self.base_llm.invoke(messages)
                        raw_text = (
                            raw_response.content
                            if hasattr(raw_response, "content")
                            else str(raw_response)
                        )

                        extracted = self._extract_json_from_llm_output(raw_text)
                        if extracted:
                            data = json.loads(extracted)
                            reasoning = (
                                data.get("reasoning")
                                or data.get("thinking")
                                or data.get("analysis")
                                or "Auto-recovered JSON"
                            )
                            return ActionPlan(
                                reasoning=reasoning,
                                action_type=data.get("action_type", "none"),
                                intent=data.get(
                                    "intent", "Recovered from malformed JSON"
                                ),
                                target_id=data.get("target_id", -1),
                                text_payload=data.get("text_payload", ""),
                                scroll_direction=data.get("scroll_direction", ""),
                                app_package=data.get("app_package", ""),
                                is_completed=data.get("is_completed", False),
                            )
                    except Exception as inner_e:
                        print(f"[Decider] JSON recovery attempt failed: {inner_e}")

        print(f"[Decider] Failed to parse LLM output, using fallback: {last_error}")
        return ActionPlan(
            reasoning=f"LLM output parsing failed after recovery attempts: {last_error}",
            action_type="none",
            intent="Fallback due to LLM output format error",
            target_id=-1,
            text_payload="",
            scroll_direction="",
            app_package="",
            is_completed=True,
        )

    def _try_deterministic_fast_path(
        self, instruction: str, widgets: list[dict]
    ) -> Optional[ActionPlan]:
        """Fast-path rule matching: if instruction is an unambiguous direct action
        (e.g., Click 'Login' or Input 'xyz'), match directly against widgets to save LLM call.
        Reference: AutoDroid (Wen et al., 2023) §4.2 Memory-guided action pruning.
        """
        inst_clean = instruction.strip()

        # 1. System actions
        if re.search(r"^(press\s+back|kembali|back)$", inst_clean, flags=re.IGNORECASE):
            return ActionPlan(
                reasoning="Fast-path rule match: System back navigation.",
                action_type="press_back",
                intent="Press back button",
                target_id=-1,
                is_completed=False,
            )

        # 2. Input actions: e.g. Masukkan "halo" ke input field
        if self._is_input_instruction(inst_clean):
            payload = self._extract_instruction_text(inst_clean)
            if payload:
                input_widget = self._find_input_widget(widgets)
                if input_widget:
                    w_id = int(input_widget.get("id", -1))
                    return ActionPlan(
                        reasoning=f"Fast-path rule match: input text into widget [{w_id}].",
                        action_type="input",
                        intent=f"Input text '{payload}'",
                        target_id=w_id,
                        text_payload=payload,
                        is_completed=False,
                    )

        # 3. Direct Click actions: e.g. Klik "Login", Ketuk "Kirim", Click "Settings"
        click_match = re.search(
            r"^(?:klik|ketuk|click|tap|pilih|select)\s+[\"“”\']?([^\"“”\'\n\r]+)[\"“”\']?$",
            inst_clean,
            flags=re.IGNORECASE,
        )
        if click_match:
            target_text = click_match.group(1).strip().lower()
            # Find widget with exact or high-confidence substring label match
            for w in widgets:
                w_text = self._widget_text(w).strip().lower()
                w_res = str(w.get("resource_id") or "").lower()
                if not w_text and not w_res:
                    continue
                if target_text == w_text or (len(target_text) > 3 and target_text in w_text) or target_text in w_res:
                    w_id = int(w.get("id", -1))
                    return ActionPlan(
                        reasoning=f"Fast-path rule match: exact/high-confidence label '{target_text}' on widget [{w_id}].",
                        action_type="click",
                        intent=f"Click on {target_text}",
                        target_id=w_id,
                        is_completed=False,
                    )

        return None

    def decide(self, state: AgentState) -> Command:
        current_step = state.get("current_step", 0)
        orchestrator_instruction = state.get("orchestrator_instruction", "")
        tcs_id = state.get("tcs_id", "")

        if orchestrator_instruction:
            current_sub_step = orchestrator_instruction
        elif self.memory is not None:
            idx = state.get("current_sub_step_index", 0)
            sub_steps = self.memory.procedural.get_steps(tcs_id, "workflow")
            current_sub_step = (
                sub_steps[idx] if idx < len(sub_steps) else "Finish Scenario"
            )
        else:
            current_sub_step = "Finish Scenario"

        self._log(f"Step {current_step} — Instruction: {current_sub_step}")

        memory_context = state.get("memory_context", "")
        general_knowledge = "No relevant prior UI knowledge."
        if self.memory is not None:
            memory_context = self.memory.retrieve(current_sub_step)
            labels = self.memory.retrieve_with_labels(current_sub_step, max_per_store=3)
            semantic = labels.get("semantic", "")
            vault = labels.get("vault", "")
            parts = [p for p in (semantic, vault) if p]
            if parts:
                general_knowledge = "\n\n".join(parts)
        self._log("Memory retrieval complete", level=_LL.DEBUG)

        widgets = state.get("widgets", [])

        # Fast-path optimization (Wen et al., 2023 - AutoDroid §4.2)
        fast_plan = self._try_deterministic_fast_path(current_sub_step, widgets)
        if fast_plan is not None:
            print(f"[Decider] Fast-path rule matched for '{current_sub_step}' (LLM call skipped).")
            self._log(
                f"Fast-path rule matched: action={fast_plan.action_type}",
                f"target_id={fast_plan.target_id}\nreasoning={fast_plan.reasoning}",
                level=_LL.INFO,
            )
            plan = fast_plan
        else:
            messages = self.prompt.format_messages(
                memory_context=memory_context or "No memory context available.",
                general_knowledge=general_knowledge,
                observer_analysis=state.get("observer_analysis", "N/A"),
                current_sub_step=current_sub_step,
            )

            print(f"[Decider] Mapping Instruction: '{current_sub_step}'...")
            self._log("LLM call started (ActionPlan generation)", level=_LL.DEBUG)
            plan = self._invoke_with_recovery(messages, current_step)
            if plan is None:
                plan = ActionPlan(
                    reasoning="Decider LLM returned None — fallback",
                    action_type="none",
                    intent="Fallback",
                    target_id=-1,
                    text_payload="",
                    scroll_direction="",
                    app_package="",
                    is_completed=True,
                )

        for guard_name, guard_fn in (
            ("Input-step guard", self._guard_input_plan),
            ("Click-target guard", self._guard_click_plan),
        ):
            guarded_plan = guard_fn(plan, current_sub_step, widgets)
            if guarded_plan != plan:
                self._log(
                    f"{guard_name} corrected ActionPlan",
                    f"before={plan.model_dump_json()}\nafter={guarded_plan.model_dump_json()}",
                    level=_LL.WARN,
                )
                plan = guarded_plan

        step_dir = state.get("step_dir", "")
        if step_dir:
            plan_path = os.path.join(step_dir, "action_plan.json")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan.model_dump(), f, indent=4, ensure_ascii=False)

        status = (
            "COMPLETED (no action)"
            if plan.is_completed
            else f"type={plan.action_type} | tid={plan.target_id}"
        )
        print(f"[Decider] {status}")
        self._log(
            f"ActionPlan: {status}",
            f"intent={plan.intent}\n"
            f"text_payload={plan.text_payload!r}\n"
            f"scroll_direction={plan.scroll_direction!r}\n"
            f"app_package={plan.app_package!r}",
        )

        if self.memory is not None:
            self.memory.update(
                {
                    "episodic": {
                        "event_type": "decision",
                        "summary": f"{plan.action_type} on widget {plan.target_id}: {plan.intent}",
                        "details": plan.model_dump_json(),
                        "actor": "decider",
                        "step": current_step,
                    }
                }
            )

        if self.logger is not None:
            self.logger.separator()

        if self.monitor is not None and not plan.is_completed:
            widgets = state.get("widgets", [])
            target_widget = next(
                (w for w in widgets if w.get("id") == plan.target_id), {}
            )
            self.monitor.on_decider(target_widget)

        technical_error_history = list(state.get("technical_error_history", []))
        if (
            "LLM output parsing failed" in plan.reasoning
            or "Decider LLM returned None" in plan.reasoning
        ):
            entry = {"step": current_step, "reason": plan.reasoning}
            if entry not in technical_error_history:
                technical_error_history.append(entry)

        return {
            "action_plan": plan.model_dump(),
            "is_completed": plan.is_completed,
            "memory_context": memory_context,
            "sender": "decider",
            "technical_error_history": technical_error_history,
        }
