import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.models.state import AgentState
from core.utils.output_writer import write_step_summary
from core.utils.process_logger import LogLevel as _LL
from core.utils.toons_helper import compress_and_report
from shared import config
from shared.prompts.reflector_prompts import (
    DIRECTIONAL_STIMULUS,
    FINAL_STEP_STIMULUS,
    LOADING_STIMULUS,
    UI_CHANGE_STIMULUS,
)
from shared.utils.llm_utils import encode_image as _encode_image_shared
from shared.utils.llm_utils import extract_json_str_from_llm_output

# Input can succeed without a large visual transition (for example a masked field),
# while scroll can legitimately stop at a boundary. Both still continue to the
# semantic validity check instead of failing at the coarse UI-change gate.
_NO_UI_CHANGE_REQUIRED = frozenset({"input", "scroll", "none"})


class LoadingCheckResult(BaseModel):
    """Chain-of-Thought: reasoning MUST be first field."""

    reasoning: str = Field(
        description="Step-by-step analysis of loading indicators before final verdict."
    )
    loading_done: bool = Field(
        description="True if the page has fully rendered and is no longer loading. "
        "False if any spinner, progress bar, skeleton screen, shimmer animation, "
        "or partially-rendered content is visible."
    )


class UIChangeCheckResult(BaseModel):
    """Chain-of-Thought: reasoning MUST be first field."""

    reasoning: str = Field(
        description="Step-by-step comparison of before/after screenshots before final verdict."
    )
    ui_changed: bool = Field(
        description="True if the app UI meaningfully changed between the before and after screenshots "
        "(new screen, new content, new element visible/hidden). "
        "False if the screens are identical or only system-level indicators changed "
        "(clock, battery, signal strength)."
    )


class ValidityCheckResult(BaseModel):
    """Chain-of-Thought: reasoning MUST be first field."""

    reasoning: str = Field(
        description="Step-by-step evaluation of visual state vs expectations before final verdict."
    )
    passed: bool = Field(
        description="True if the action achieved its micro-goal OR if the final expected result is satisfied."
    )
    figma_discrepancies: str = Field(
        default="",
        description="If Figma Gold Standard was used, describe any layout, color, or structural differences. "
        "Empty if no Figma comparison was performed.",
    )


class ReflectorAgent:
    def __init__(self, llm, memory=None, logger=None, device=None):
        self.base_llm = llm
        self._llm_loading = llm.with_structured_output(LoadingCheckResult)
        self._llm_change = llm.with_structured_output(UIChangeCheckResult)
        self._llm_validity = llm.with_structured_output(ValidityCheckResult)
        self.logger = logger
        self.memory = memory
        self.device = device

    def _log(self, msg: str, detail: str = "", level=None):
        if self.logger is not None:
            lvl = level if level is not None else _LL.INFO
            self.logger.log("REFLECTOR", msg, detail, level=lvl)

    def _encode_image(self, image_path: str, max_height: int = 720) -> str:
        """Delegate to shared image encoding utility."""
        return _encode_image_shared(image_path, max_height)

    def _capture_post_action(
        self, step_dir: str, output_dir: str = ""
    ) -> Optional[str]:
        """Take a fresh screenshot on the device. Returns saved path or None on failure."""
        if self.device is None:
            return None
        save_dir = step_dir if step_dir else output_dir
        if not save_dir:
            return None
        post_action_path = os.path.join(save_dir, "post_action.png")
        try:
            self.device.screenshot(post_action_path)
            self._log(
                "Post-action screenshot captured", post_action_path, level=_LL.DEBUG
            )
            return post_action_path
        except Exception as e:
            self._log("Post-action screenshot FAILED", str(e), level=_LL.ERROR)
            print(f"[Reflector] Failed to capture post-action screenshot: {e}")
            return None

    def _check_loading(
        self, screenshot_path: str, memory_context: str
    ) -> LoadingCheckResult:
        """Call 1: determine if the page is still loading."""
        system_prompt = (
            "You are the Reflector Agent performing a LOADING CHECK.\n"
            "Examine the screenshot and determine whether the app page has fully loaded.\n\n"
            "Return loading_done=False if you see ANY of:\n"
            "  • Spinner or circular progress indicator\n"
            "  • Linear progress bar\n"
            "  • Skeleton screen (grey placeholder shapes)\n"
            "  • Shimmer animation\n"
            "  • Partially-rendered list (items appear one by one)\n"
            "  • Blank or mostly-white content area that should have content\n\n"
            "Return loading_done=True ONLY if the page appears fully and stably rendered.\n"
            + LOADING_STIMULUS
        )
        content: list = [
            {
                "type": "text",
                "text": f"Context:\n{memory_context}"
                if memory_context
                else "No prior context.",
            }
        ]
        if screenshot_path:
            b64 = self._encode_image(screenshot_path)
            if b64:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/webp;base64,{b64}"},
                    }
                )
                content.append(
                    {
                        "type": "text",
                        "text": "[Image above: post-action screenshot to check for loading state]",
                    }
                )
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=content)]
        backoff = 1.0
        for attempt in range(4):
            try:
                result = self._llm_loading.invoke(messages)
                if result is not None:
                    return result
                return LoadingCheckResult(
                    loading_done=True,
                    reasoning="Loading check returned None (assuming loaded)",
                )
            except Exception as e:
                if self._is_rate_limit_error(e) and attempt < 3:
                    print(
                        f"[Reflector] Loading check rate limited, retrying in {backoff:.1f}s..."
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 16.0)
                    continue
                return LoadingCheckResult(
                    loading_done=True,
                    reasoning=f"Loading check error (assuming loaded): {e}",
                )

    def _check_ui_change(
        self,
        pre_path: str,
        post_path: str,
        memory_context: str,
        loading_reasoning: str = "",
        parallel_mode: bool = False,
    ) -> UIChangeCheckResult:
        """Call 2: determine whether the UI meaningfully changed.

        Args:
            pre_path: Path to before screenshot
            post_path: Path to after screenshot
            memory_context: Memory context string
            loading_reasoning: Result from loading check (empty if parallel_mode=True)
            parallel_mode: If True, runs independently without loading context
        """
        if parallel_mode:
            system_prompt = (
                "You are the Reflector Agent performing a UI CHANGE CHECK.\n"
                "Compare the BEFORE screenshot (pre-action) and the AFTER screenshot (post-action).\n"
                "Assume the page is fully loaded unless you see clear loading indicators.\n\n"
                "Return ui_changed=True if the app UI meaningfully changed:\n"
                "  • New screen or view appeared\n"
                "  • New content, list items, or elements became visible\n"
                "  • A form field was filled, a button state changed, a dialog appeared\n\n"
                "Return ui_changed=False if:\n"
                "  • Screens are visually identical\n"
                "  • ONLY system-level indicators changed (clock, battery, signal, notification bar)\n"
                "  • The action had no visible effect on the app UI\n"
                + UI_CHANGE_STIMULUS
            )
        else:
            system_prompt = (
                "You are the Reflector Agent performing a UI CHANGE CHECK.\n"
                "The page has already been confirmed as FULLY LOADED (loading check passed).\n\n"
                f"Loading check result: {loading_reasoning}\n\n"
                "Compare the BEFORE screenshot (pre-action) and the AFTER screenshot (post-action).\n"
                "Return ui_changed=True if the app UI meaningfully changed:\n"
                "  • New screen or view appeared\n"
                "  • New content, list items, or elements became visible\n"
                "  • A form field was filled, a button state changed, a dialog appeared\n\n"
                "Return ui_changed=False if:\n"
                "  • Screens are visually identical\n"
                "  • ONLY system-level indicators changed (clock, battery, signal, notification bar)\n"
                "  • The action had no visible effect on the app UI\n"
                + UI_CHANGE_STIMULUS
            )
        content: list = [
            {
                "type": "text",
                "text": f"Context:\n{memory_context}"
                if memory_context
                else "No prior context.",
            }
        ]
        for path, label in [
            (pre_path, "BEFORE (pre-action)"),
            (post_path, "AFTER (post-action)"),
        ]:
            if path:
                b64 = self._encode_image(path)
                if b64:
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/webp;base64,{b64}"},
                        }
                    )
                    content.append(
                        {"type": "text", "text": f"[Image above: {label} screenshot]"}
                    )
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=content)]
        backoff = 1.0
        for attempt in range(4):
            try:
                result = self._llm_change.invoke(messages)
                if result is not None:
                    return result
                return UIChangeCheckResult(
                    ui_changed=True,
                    reasoning="UI change check returned None (assuming changed)",
                )
            except Exception as e:
                if self._is_rate_limit_error(e) and attempt < 3:
                    print(
                        f"[Reflector] UI change check rate limited, retrying in {backoff:.1f}s..."
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 16.0)
                    continue
                return UIChangeCheckResult(
                    ui_changed=True,
                    reasoning=f"UI change check error (assuming changed): {e}",
                )

    def _extract_json_from_llm_output(self, raw_output: str) -> Optional[str]:
        """Delegate to shared JSON extraction utility."""
        return extract_json_str_from_llm_output(raw_output)

    @staticmethod
    def _is_rate_limit_error(error: Exception) -> bool:
        """Check if an exception is a 429 rate-limit error."""
        err_str = str(error)
        return (
            "429" in err_str
            or "rate" in err_str.lower()
            or "too many requests" in err_str.lower()
        )

    def _invoke_with_json_recovery(
        self, messages, max_retries: int = 2
    ) -> ValidityCheckResult:
        """Invoke structured LLM with automatic JSON extraction retry.

        If the LLM returns malformed JSON (e.g., with XML tags), attempt to
        extract the JSON and retry parsing before giving up.
        Rate-limit (429) errors are retried with exponential backoff separately.

        Args:
            messages: LangChain message list.
            max_retries: Number of retry attempts.
        """
        last_error = None
        rate_limit_backoff = 1.0

        for attempt in range(max_retries):
            try:
                result = self._llm_validity.invoke(messages)
                if result is not None:
                    return result
                print(
                    f"[Reflector] Structured LLM returned None, attempting recovery..."
                )
            except Exception as e:
                last_error = e

                if self._is_rate_limit_error(e):
                    if attempt < max_retries - 1:
                        print(
                            f"[Reflector] Rate limited (429), retrying in {rate_limit_backoff:.1f}s (attempt {attempt + 1})..."
                        )
                        time.sleep(rate_limit_backoff)
                        rate_limit_backoff = min(rate_limit_backoff * 2, 16.0)
                        continue
                    break

                error_str = str(e)

                if "json_invalid" not in error_str and "Invalid JSON" not in error_str:
                    break

                if attempt < max_retries - 1:
                    try:
                        print(
                            f"[Reflector] Attempting JSON recovery (attempt {attempt + 1})..."
                        )
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
                                or data.get("explanation")
                                or "Auto-recovered JSON"
                            )

                            return ValidityCheckResult(
                                reasoning=reasoning,
                                passed=data.get("passed", False),
                                figma_discrepancies=data.get("figma_discrepancies", ""),
                            )
                    except Exception as inner_e:
                        print(
                            f"[Reflector] JSON recovery attempt {attempt + 1} failed: {inner_e}"
                        )

                if attempt < max_retries - 1:
                    from langchain_core.messages import AIMessage

                    reminder = AIMessage(
                        content="IMPORTANT: Return ONLY a valid JSON object. No XML tags. No extra text."
                    )
                    messages = messages + [reminder]

        return ValidityCheckResult(
            passed=False,
            reasoning=f"[SYSTEM_ERROR] Failed to parse LLM output after {max_retries} attempts: {last_error}",
            figma_discrepancies="",
        )

    def _check_validity(
        self,
        screenshot_path: str,
        instruction: str,
        is_final_step: bool,
        expected_result: str,
        figma_b64: str,
        figma_enabled: bool,
        memory_context: str,
        general_knowledge: str,
        loading_reasoning: str,
        ui_change_reasoning: str,
    ) -> ValidityCheckResult:
        """Call 3: semantic validity judgment. Receives both prior verdicts as context."""
        stimulus = DIRECTIONAL_STIMULUS.format(
            general_knowledge=general_knowledge
            if general_knowledge
            else "No relevant prior UI knowledge."
        )
        system_prompt = (
            "You are the Reflector Agent performing a STRICT VALIDITY CHECK.\n"
            "The prior checks have already confirmed:\n"
            f"  ✓ Loading check PASSED: {loading_reasoning}\n"
            f"  ✓ UI change check PASSED: {ui_change_reasoning}\n\n"
            f"CURRENT STEP INSTRUCTION: {instruction}\n"
        )
        if is_final_step:
            if figma_enabled and figma_b64:
                system_prompt += (
                    FINAL_STEP_STIMULUS.format(
                        general_knowledge=general_knowledge
                        if general_knowledge
                        else "No relevant prior UI knowledge."
                    )
                    + f"\nULTIMATE EXPECTED RESULT: {expected_result}\n"
                )
                print("[Reflector] FINAL Verification with Figma Gold Standard")
            else:
                system_prompt += (
                    "CRITICAL: This is the FINAL step. Verify the screen matches the ultimate Expected Result.\n"
                    + stimulus
                    + f"\nULTIMATE EXPECTED RESULT: {expected_result}\n"
                )
                print("[Reflector] FINAL Verification (text-only mode)")
        else:
            system_prompt += (
                "This is an intermediate step. The UI has already changed (confirmed above).\n"
                "Verify the change was the CORRECT response to the instruction — not an error dialog, "
                "wrong screen, or unrelated transition.\n" + stimulus
            )
        content: list = [
            {
                "type": "text",
                "text": f"Context:\n{memory_context}"
                if memory_context
                else "No prior context.",
            }
        ]
        if screenshot_path:
            b64 = self._encode_image(screenshot_path)
            if b64:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/webp;base64,{b64}"},
                    }
                )
                content.append(
                    {
                        "type": "text",
                        "text": "[Image above: LIVE APP screenshot (post-action)]",
                    }
                )
        if is_final_step and figma_enabled and figma_b64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{figma_b64}"},
                }
            )
            content.append(
                {"type": "text", "text": "[Image above: FIGMA GOLD STANDARD]"}
            )
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=content)]
        return self._invoke_with_json_recovery(messages)

    def _build_return(
        self,
        *,
        state: dict,
        passed: bool,
        reasoning: str,
        figma_discrepancies: str,
        screenshot_path: str,
        post_action_path: Optional[str],
        current_step: int,
        current_idx: int,
        figma_enabled: bool,
        memory_context: str,
        verification_chain: dict,
        instruction: str = "",
        tcs_id: str = "",
        is_final_step: bool = False,
        expected_result: str = "",
    ) -> dict:
        """Write report JSON, update MIRIX, compute metrics, return AgentState patch."""
        verdict = "PASSED" if passed else "FAILED"
        step_dir = state.get("step_dir", "")
        output_dir = state.get("output_dir", "")
        save_dir = step_dir if step_dir else output_dir

        is_system_error = "[SYSTEM_ERROR]" in reasoning

        if save_dir:
            ref_path = os.path.join(save_dir, "reflector_report.json")
            with open(ref_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "passed": passed,
                        "is_system_error": is_system_error,
                        "reasoning": reasoning,
                        "step_index": current_idx,
                        "figma_enabled": figma_enabled,
                        "figma_discrepancies": figma_discrepancies,
                        "verification_chain": verification_chain,
                    },
                    f,
                    indent=4,
                    ensure_ascii=False,
                )

            action_plan = state.get("action_plan", {}) or {}
            write_step_summary(
                step_dir=save_dir,
                step_number=current_step,
                instruction=instruction
                or state.get("orchestrator_instruction", "")
                or "",
                action_type=action_plan.get("action_type", ""),
                target_widget_id=action_plan.get("target_id", -1),
                verdict=verdict,
                has_screenshot=bool(
                    post_action_path or state.get("screenshot_path", "")
                ),
            )

            if is_final_step and figma_enabled:
                comparison_path = os.path.join(save_dir, "figma_comparison_result.json")
                with open(comparison_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "tcs_id": tcs_id,
                            "passed": passed,
                            "figma_discrepancies": figma_discrepancies,
                            "expected_result": expected_result,
                        },
                        f,
                        indent=4,
                        ensure_ascii=False,
                    )
                print(
                    f"[Reflector] Figma comparison result saved to: {comparison_path}"
                )

        chain_summary = (
            f"loading={'PASS' if verification_chain.get('loading_done') else 'FAIL/N/A'} | "
            f"ui_change={'PASS' if verification_chain.get('ui_changed') else 'FAIL/N/A'} | "
            f"validity={verdict}"
        )
        if self.memory is not None and post_action_path:
            self.memory.update(
                {
                    "resource": {
                        "title": f"post_action_step_{current_step}",
                        "summary": f"Post-action screenshot after step {current_step}",
                        "resource_type": "screenshot",
                        "path": post_action_path,
                        "step": current_step,
                    },
                    "episodic": {
                        "event_type": "reflector_evaluation",
                        "summary": f"{verdict} [{chain_summary}]: {reasoning[:120]}",
                        "details": reasoning,
                        "actor": "reflector",
                        "step": current_step,
                    },
                }
            )
        elif self.memory is not None:
            self.memory.update(
                {
                    "episodic": {
                        "event_type": "reflector_evaluation",
                        "summary": f"{verdict} [{chain_summary}]: {reasoning[:120]}",
                        "details": reasoning,
                        "actor": "reflector",
                        "step": current_step,
                    }
                }
            )

        recovery_attempts = state.get("recovery_attempts", 0)
        if not passed:
            recovery_attempts += 1

        is_first = state.get("is_first_verify_attempt", True)
        total_reflector_calls = state.get("total_reflector_calls", 0) + 1
        reflector_pass_count = state.get("reflector_pass_count", 0) + (
            1 if passed else 0
        )
        total_first_verify_calls = state.get("total_first_verify_calls", 0) + (
            1 if is_first else 0
        )
        reflector_first_pass_count = state.get("reflector_first_pass_count", 0) + (
            1 if is_first and passed else 0
        )

        if self.logger is not None:
            self.logger.separator()

        return {
            "last_reflector_passed": passed,
            "last_reflector_reasoning": reasoning,
            "screenshot_path": screenshot_path,
            "memory_context": memory_context,
            "sender": "reflector",
            "recovery_attempts": recovery_attempts,
            "total_reflector_calls": total_reflector_calls,
            "reflector_pass_count": reflector_pass_count,
            "total_first_verify_calls": total_first_verify_calls,
            "reflector_first_pass_count": reflector_first_pass_count,
        }

    def evaluate(self, state: AgentState) -> dict:
        # Uses Directional Stimulus Prompting (see reflector_prompts.py)
        # to focus LLM evaluation on critical aspects while ignoring noise.
        pre_action_path = state.get("screenshot_path", "")
        current_step = state.get("current_step", 0)
        tcs_id = state.get("tcs_id", "")
        step_dir = state.get("step_dir", "")
        output_dir = state.get("output_dir", "")
        self._log(f"Step {current_step} — Verification started")

        post_action_path = self._capture_post_action(step_dir, output_dir)
        screenshot_path = post_action_path if post_action_path else pre_action_path

        if self.memory is not None:
            expected_result = self.memory.core.get("expected_result") or ""
            test_type = self.memory.core.get("test_type") or "Pos."
            figma_enabled = (self.memory.core.get("figma_enabled") or "False") == "True"
            figma_b64 = (
                self.memory.resource.get_figma_gold_b64() if figma_enabled else ""
            )
            sub_steps = self.memory.procedural.get_steps(tcs_id, "workflow")
        else:
            expected_result = ""
            test_type = "Pos."
            figma_enabled = False
            figma_b64 = ""
            sub_steps = []

        current_idx = state.get("current_sub_step_index", 0)
        orchestrator_instruction = state.get("orchestrator_instruction", "")

        if orchestrator_instruction:
            is_final_step = state.get("is_final_step", False)
            current_instruction = orchestrator_instruction
        else:
            is_final_step = (current_idx == len(sub_steps) - 1) if sub_steps else False
            current_instruction = (
                sub_steps[current_idx] if current_idx < len(sub_steps) else "Finish"
            )

        action_plan = state.get("action_plan", {}) or {}
        action_type = action_plan.get("action_type", "")
        expected_pkg = action_plan.get("app_package", "")

        if action_type == "start_app" and self.device is not None:
            current_pkg = self.device.get_current_app()

            if not expected_pkg:
                expected_pkg = current_pkg
                self._log(
                    "start_app: no expected_pkg — inferred from live foreground",
                    f"current_package='{current_pkg}'",
                    level=_LL.DEBUG,
                )
                print(
                    f"[Reflector] [start_app] No expected_pkg — inferred from device: '{current_pkg}'"
                )

            passed = bool(current_pkg) and expected_pkg in current_pkg
            reasoning = (
                f"ADB foreground check: current='{current_pkg}' expected='{expected_pkg}' "
                f"→ {'PASS' if passed else 'FAIL'}"
            )
            verdict = "PASSED" if passed else "FAILED"
            print(f"[Reflector] [start_app] {reasoning}")
            self._log(f"start_app foreground check: {verdict}", reasoning)

            return self._build_return(
                state=state,
                passed=passed,
                reasoning=reasoning,
                figma_discrepancies="",
                screenshot_path=screenshot_path,
                post_action_path=post_action_path,
                current_step=current_step,
                current_idx=current_idx,
                figma_enabled=False,
                memory_context=state.get("memory_context", ""),
                instruction=current_instruction,
                verification_chain={
                    "loading_done": None,
                    "loading_reasoning": None,
                    "ui_changed": None,
                    "ui_change_reasoning": None,
                    "short_circuit": "start_app_adb",
                    "expected_package": expected_pkg,
                    "current_package": current_pkg,
                },
            )

        memory_context = ""
        general_knowledge = "No relevant prior UI knowledge."
        if self.memory is not None:
            memory_context = self.memory.retrieve(
                f"execution result step={current_step}"
            )
            labels = self.memory.retrieve_with_labels(
                f"execution result step={current_step}", max_per_store=3
            )
            semantic = labels.get("semantic", "")
            vault = labels.get("vault", "")
            parts = [p for p in (semantic, vault) if p]
            if parts:
                general_knowledge = "\n\n".join(parts)

        mode_label = "FINAL" if is_final_step else "STEP"
        self._log(
            f"3-call chain started ({mode_label})", f"instruction={current_instruction}"
        )
        print(f"[Reflector] {mode_label} — 3-call chain starting...")

        if config.PARALLEL_REFLECTOR_CHECKS and pre_action_path:
            self._log(
                "PARALLEL MODE: Running Call 1 (Loading) + Call 2 (UI Change) concurrently",
                level=_LL.DEBUG,
            )
            print(f"[Reflector] PARALLEL MODE: Starting Call 1 + Call 2...")

            with ThreadPoolExecutor(max_workers=2) as executor:
                future_loading = executor.submit(
                    self._check_loading, screenshot_path, memory_context
                )
                future_ui_change = executor.submit(
                    self._check_ui_change,
                    pre_action_path,
                    screenshot_path,
                    memory_context,
                    "",
                    True,
                )

                loading_result = future_loading.result()
                change_result = future_ui_change.result()

            self._log(
                f"Call 1 result: loading_done={loading_result.loading_done}",
                loading_result.reasoning,
                level=_LL.DEBUG,
            )
            print(f"[Reflector] Call 1 Loading: done={loading_result.loading_done}")
            self._log(
                f"Call 2 result: ui_changed={change_result.ui_changed}",
                change_result.reasoning,
                level=_LL.DEBUG,
            )
            print(f"[Reflector] Call 2 UI Change: changed={change_result.ui_changed}")

            if not loading_result.loading_done:
                reasoning = f"[Loading Check FAILED] {loading_result.reasoning}"
                print(f"[Reflector] SHORT-CIRCUIT: {reasoning}")
                self._log("SHORT-CIRCUIT at Call 1", reasoning, level=_LL.DEBUG)
                return self._build_return(
                    state=state,
                    passed=False,
                    reasoning=reasoning,
                    figma_discrepancies="",
                    screenshot_path=screenshot_path,
                    post_action_path=post_action_path,
                    current_step=current_step,
                    current_idx=current_idx,
                    figma_enabled=figma_enabled,
                    memory_context=memory_context,
                    instruction=current_instruction,
                    verification_chain={
                        "loading_done": False,
                        "loading_reasoning": loading_result.reasoning,
                        "ui_changed": change_result.ui_changed,
                        "ui_change_reasoning": change_result.reasoning,
                        "short_circuit": "loading_failed",
                    },
                )

            if (
                not change_result.ui_changed
                and action_type not in _NO_UI_CHANGE_REQUIRED
            ):
                reasoning = f"[UI Change Check FAILED] {change_result.reasoning}"
                print(f"[Reflector] SHORT-CIRCUIT: {reasoning}")
                self._log("SHORT-CIRCUIT at Call 2", reasoning, level=_LL.DEBUG)
                return self._build_return(
                    state=state,
                    passed=False,
                    reasoning=reasoning,
                    figma_discrepancies="",
                    screenshot_path=screenshot_path,
                    post_action_path=post_action_path,
                    current_step=current_step,
                    current_idx=current_idx,
                    figma_enabled=figma_enabled,
                    memory_context=memory_context,
                    instruction=current_instruction,
                    verification_chain={
                        "loading_done": True,
                        "loading_reasoning": loading_result.reasoning,
                        "ui_changed": False,
                        "ui_change_reasoning": change_result.reasoning,
                        "short_circuit": "no_ui_change",
                    },
                )
        else:
            self._log("SEQUENTIAL MODE: Running Call 1 then Call 2", level=_LL.DEBUG)
            loading_result = self._check_loading(screenshot_path, memory_context)
            self._log(
                f"Call 1 result: loading_done={loading_result.loading_done}",
                loading_result.reasoning,
                level=_LL.DEBUG,
            )
            print(
                f"[Reflector] Call 1 Loading: done={loading_result.loading_done} | {loading_result.reasoning}"
            )

            if not loading_result.loading_done:
                reasoning = f"[Loading Check FAILED] {loading_result.reasoning}"
                print(f"[Reflector] SHORT-CIRCUIT: {reasoning}")
                self._log("SHORT-CIRCUIT at Call 1", reasoning, level=_LL.DEBUG)
                return self._build_return(
                    state=state,
                    passed=False,
                    reasoning=reasoning,
                    figma_discrepancies="",
                    screenshot_path=screenshot_path,
                    post_action_path=post_action_path,
                    current_step=current_step,
                    current_idx=current_idx,
                    figma_enabled=figma_enabled,
                    memory_context=memory_context,
                    instruction=current_instruction,
                    verification_chain={
                        "loading_done": False,
                        "loading_reasoning": loading_result.reasoning,
                        "ui_changed": None,
                        "ui_change_reasoning": None,
                        "short_circuit": "loading_failed",
                    },
                )

            self._log("Call 2: UI Change Check", level=_LL.DEBUG)
            change_result = self._check_ui_change(
                pre_path=pre_action_path,
                post_path=screenshot_path,
                memory_context=memory_context,
                loading_reasoning=loading_result.reasoning,
            )
            self._log(
                f"Call 2 result: ui_changed={change_result.ui_changed}",
                change_result.reasoning,
                level=_LL.DEBUG,
            )
            print(
                f"[Reflector] Call 2 UI Change: changed={change_result.ui_changed} | {change_result.reasoning}"
            )

            if (
                not change_result.ui_changed
                and action_type not in _NO_UI_CHANGE_REQUIRED
            ):
                reasoning = f"[UI Change Check FAILED] {change_result.reasoning}"
                print(f"[Reflector] SHORT-CIRCUIT: {reasoning}")
                self._log("SHORT-CIRCUIT at Call 2", reasoning, level=_LL.DEBUG)
                return self._build_return(
                    state=state,
                    passed=False,
                    reasoning=reasoning,
                    figma_discrepancies="",
                    screenshot_path=screenshot_path,
                    post_action_path=post_action_path,
                    current_step=current_step,
                    current_idx=current_idx,
                    figma_enabled=figma_enabled,
                    memory_context=memory_context,
                    instruction=current_instruction,
                    verification_chain={
                        "loading_done": True,
                        "loading_reasoning": loading_result.reasoning,
                        "ui_changed": False,
                        "ui_change_reasoning": change_result.reasoning,
                        "short_circuit": "no_ui_change",
                    },
                )

        self._log("Call 3: Validity Check", level=_LL.DEBUG)
        validity_result = self._check_validity(
            screenshot_path=screenshot_path,
            instruction=current_instruction,
            is_final_step=is_final_step,
            expected_result=expected_result,
            figma_b64=figma_b64,
            figma_enabled=figma_enabled,
            memory_context=memory_context,
            general_knowledge=general_knowledge,
            loading_reasoning=loading_result.reasoning,
            ui_change_reasoning=change_result.reasoning,
        )
        passed = validity_result.passed
        reasoning = validity_result.reasoning
        figma_discrepancies = validity_result.figma_discrepancies or ""

        verdict = "PASSED" if passed else "FAILED"
        print(f"[Reflector] Call 3 Validity: {verdict} | {reasoning}")
        self._log(
            f"Call 3 Verdict: {verdict}",
            f"reasoning={reasoning}\nfigma_discrepancies={figma_discrepancies or 'N/A'}",
        )
        if figma_discrepancies:
            print(f"[Reflector] Figma Discrepancies: {figma_discrepancies}")

        return self._build_return(
            state=state,
            passed=passed,
            reasoning=reasoning,
            figma_discrepancies=figma_discrepancies,
            screenshot_path=screenshot_path,
            post_action_path=post_action_path,
            current_step=current_step,
            current_idx=current_idx,
            figma_enabled=figma_enabled,
            memory_context=memory_context,
            instruction=current_instruction,
            verification_chain={
                "loading_done": True,
                "loading_reasoning": loading_result.reasoning,
                "ui_changed": True,
                "ui_change_reasoning": change_result.reasoning,
                "short_circuit": None,
            },
            tcs_id=tcs_id,
            is_final_step=is_final_step,
            expected_result=expected_result,
        )
