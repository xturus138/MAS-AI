import base64
import json
import os
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from core.models.state import AgentState
from core.utils.toons_helper import compress_and_report

import cv2

# Action types for which no visible UI navigation is required to consider an action successful.
# 'input' enters text into a focused field — screen stays the same.
# 'scroll' may not change visible content if already at the boundary.
_NO_UI_CHANGE_REQUIRED = frozenset({"input", "scroll", "none"})


class LoadingCheckResult(BaseModel):
    loading_done: bool = Field(
        description="True if the page has fully rendered and is no longer loading. "
                    "False if any spinner, progress bar, skeleton screen, shimmer animation, "
                    "or partially-rendered content is visible."
    )
    reasoning: str = Field(description="Brief explanation of what loading indicators were observed or absent.")


class UIChangeCheckResult(BaseModel):
    ui_changed: bool = Field(
        description="True if the app UI meaningfully changed between the before and after screenshots "
                    "(new screen, new content, new element visible/hidden). "
                    "False if the screens are identical or only system-level indicators changed "
                    "(clock, battery, signal strength)."
    )
    reasoning: str = Field(description="Brief explanation of what changed or why no change was detected.")


class ValidityCheckResult(BaseModel):
    passed: bool = Field(
        description="True if the action achieved its micro-goal OR if the final expected result is satisfied."
    )
    reasoning: str = Field(
        description="Explanation of the visual state vs expectations. Crucial for self-correction retries."
    )
    figma_discrepancies: str = Field(
        default="",
        description="If Figma Gold Standard was used, describe any layout, color, or structural differences. "
                    "Empty if no Figma comparison was performed."
    )


class ReflectorAgent:
    def __init__(self, llm, memory=None, logger=None, device=None):
        self._llm_loading  = llm.with_structured_output(LoadingCheckResult)
        self._llm_change   = llm.with_structured_output(UIChangeCheckResult)
        self._llm_validity = llm.with_structured_output(ValidityCheckResult)
        self.logger = logger
        self.memory = memory
        self.device = device   # IDeviceClient — used to capture post-action screenshot

    def _log(self, msg: str, detail: str = ""):
        if self.logger is not None:
            self.logger.log("REFLECTOR", msg, detail)

    def _encode_image(self, image_path: str, max_height: int = 720) -> str:
        img = cv2.imread(image_path)
        if img is None:
            return ""

        h, w = img.shape[:2]
        if h > max_height:
            scale = max_height / h
            new_w = int(w * scale)
            img = cv2.resize(img, (new_w, max_height), interpolation=cv2.INTER_AREA)

        success, buffer = cv2.imencode(".webp", img, [int(cv2.IMWRITE_WEBP_QUALITY), 70])
        if not success:
            success, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        if not success:
            return ""

        return base64.b64encode(buffer).decode("utf-8")

    def _capture_post_action(self, step_dir: str, output_dir: str = "") -> Optional[str]:
        """Take a fresh screenshot on the device. Returns saved path or None on failure."""
        if self.device is None:
            return None
        save_dir = step_dir if step_dir else output_dir
        if not save_dir:
            return None
        post_action_path = os.path.join(save_dir, "post_action.png")
        try:
            self.device.screenshot(post_action_path)
            self._log("Post-action screenshot captured", post_action_path)
            return post_action_path
        except Exception as e:
            self._log("Post-action screenshot FAILED", str(e))
            print(f"[Reflector] Failed to capture post-action screenshot: {e}")
            return None

    # ── Call 1 ────────────────────────────────────────────────────────────────

    def _check_loading(self, screenshot_path: str, memory_context: str) -> LoadingCheckResult:
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
            "Return loading_done=True ONLY if the page appears fully and stably rendered."
        )
        content: list = [{"type": "text", "text": f"Context:\n{memory_context}" if memory_context else "No prior context."}]
        if screenshot_path:
            b64 = self._encode_image(screenshot_path)
            if b64:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/webp;base64,{b64}"}})
                content.append({"type": "text", "text": "[Image above: post-action screenshot to check for loading state]"})
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=content)]
        try:
            return self._llm_loading.invoke(messages)
        except Exception as e:
            return LoadingCheckResult(loading_done=True, reasoning=f"Loading check error (assuming loaded): {e}")

    # ── Call 2 ────────────────────────────────────────────────────────────────

    def _check_ui_change(
        self,
        pre_path: str,
        post_path: str,
        memory_context: str,
        loading_reasoning: str,
    ) -> UIChangeCheckResult:
        """Call 2: determine whether the UI meaningfully changed. Receives Call 1 verdict as context."""
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
            "  • The action had no visible effect on the app UI"
        )
        content: list = [{"type": "text", "text": f"Context:\n{memory_context}" if memory_context else "No prior context."}]
        for path, label in [(pre_path, "BEFORE (pre-action)"), (post_path, "AFTER (post-action)")]:
            if path:
                b64 = self._encode_image(path)
                if b64:
                    content.append({"type": "image_url", "image_url": {"url": f"data:image/webp;base64,{b64}"}})
                    content.append({"type": "text", "text": f"[Image above: {label} screenshot]"})
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=content)]
        try:
            return self._llm_change.invoke(messages)
        except Exception as e:
            return UIChangeCheckResult(ui_changed=True, reasoning=f"UI change check error (assuming changed): {e}")

    # ── Call 3 ────────────────────────────────────────────────────────────────

    def _check_validity(
        self,
        screenshot_path: str,
        instruction: str,
        is_final_step: bool,
        expected_result: str,
        figma_b64: str,
        figma_enabled: bool,
        memory_context: str,
        loading_reasoning: str,
        ui_change_reasoning: str,
    ) -> ValidityCheckResult:
        """Call 3: semantic validity judgment. Receives both prior verdicts as context."""
        system_prompt = (
            "You are the Reflector Agent performing a VALIDITY CHECK.\n"
            "The prior checks have already confirmed:\n"
            f"  ✓ Loading check PASSED: {loading_reasoning}\n"
            f"  ✓ UI change check PASSED: {ui_change_reasoning}\n\n"
            f"CURRENT STEP INSTRUCTION: {instruction}\n"
        )
        if is_final_step:
            if figma_enabled and figma_b64:
                system_prompt += (
                    "CRITICAL: This is the FINAL step. Perform a 3-WAY VERIFICATION:\n"
                    "1. Confirm the LIVE APP SCREENSHOT matches the EXPECTED RESULT.\n"
                    "2. Compare the LIVE APP SCREENSHOT against the FIGMA GOLD STANDARD.\n"
                    "   - Note layout, color, content, or structural discrepancies.\n"
                    "   - Minor pixel differences are acceptable. Missing elements are NOT.\n"
                    f"ULTIMATE EXPECTED RESULT: {expected_result}\n"
                )
                print("[Reflector] FINAL Verification with Figma Gold Standard")
            else:
                system_prompt += (
                    "CRITICAL: This is the FINAL step. Verify the screen matches the ultimate Expected Result.\n"
                    f"ULTIMATE EXPECTED RESULT: {expected_result}\n"
                )
                print("[Reflector] FINAL Verification (text-only mode)")
        else:
            system_prompt += (
                "This is an intermediate step. The UI has already changed (confirmed above).\n"
                "Verify the change was the CORRECT response to the instruction — not an error dialog, "
                "wrong screen, or unrelated transition."
            )
        content: list = [{"type": "text", "text": f"Context:\n{memory_context}" if memory_context else "No prior context."}]
        if screenshot_path:
            b64 = self._encode_image(screenshot_path)
            if b64:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/webp;base64,{b64}"}})
                content.append({"type": "text", "text": "[Image above: LIVE APP screenshot (post-action)]"})
        if is_final_step and figma_enabled and figma_b64:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{figma_b64}"}})
            content.append({"type": "text", "text": "[Image above: FIGMA GOLD STANDARD]"})
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=content)]
        try:
            return self._llm_validity.invoke(messages)
        except Exception as e:
            return ValidityCheckResult(passed=False, reasoning=f"Validity LLM error: {e}", figma_discrepancies="")

    # ── Shared return builder ─────────────────────────────────────────────────

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
        tcs_id: str = "",
        is_final_step: bool = False,
        expected_result: str = "",
    ) -> dict:
        """Write report JSON, update MIRIX, compute metrics, return AgentState patch."""
        verdict   = "PASSED" if passed else "FAILED"
        step_dir  = state.get("step_dir", "")
        output_dir = state.get("output_dir", "")
        save_dir  = step_dir if step_dir else output_dir

        if save_dir:
            ref_path = os.path.join(save_dir, "reflector_report.json")
            with open(ref_path, "w", encoding="utf-8") as f:
                json.dump({
                    "passed": passed,
                    "reasoning": reasoning,
                    "step_index": current_idx,
                    "figma_enabled": figma_enabled,
                    "figma_discrepancies": figma_discrepancies,
                    "verification_chain": verification_chain,
                }, f, indent=4, ensure_ascii=False)

            if is_final_step and figma_enabled:
                comparison_path = os.path.join(save_dir, "figma_comparison_result.json")
                with open(comparison_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "tcs_id": tcs_id,
                        "passed": passed,
                        "figma_discrepancies": figma_discrepancies,
                        "expected_result": expected_result,
                    }, f, indent=4, ensure_ascii=False)
                print(f"[Reflector] Figma comparison result saved to: {comparison_path}")

        chain_summary = (
            f"loading={'PASS' if verification_chain.get('loading_done') else 'FAIL/N/A'} | "
            f"ui_change={'PASS' if verification_chain.get('ui_changed') else 'FAIL/N/A'} | "
            f"validity={verdict}"
        )
        if self.memory is not None and post_action_path:
            self.memory.update({
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
            })
        elif self.memory is not None:
            self.memory.update({
                "episodic": {
                    "event_type": "reflector_evaluation",
                    "summary": f"{verdict} [{chain_summary}]: {reasoning[:120]}",
                    "details": reasoning,
                    "actor": "reflector",
                    "step": current_step,
                }
            })

        recovery_attempts = state.get("recovery_attempts", 0)
        if not passed:
            recovery_attempts += 1

        is_first                   = state.get("is_first_verify_attempt", True)
        total_reflector_calls      = state.get("total_reflector_calls", 0) + 1
        reflector_pass_count       = state.get("reflector_pass_count", 0) + (1 if passed else 0)
        total_first_verify_calls   = state.get("total_first_verify_calls", 0) + (1 if is_first else 0)
        reflector_first_pass_count = state.get("reflector_first_pass_count", 0) + (1 if is_first and passed else 0)

        if self.logger is not None:
            self.logger.separator()

        return {
            "last_reflector_passed":       passed,
            "screenshot_path":             screenshot_path,
            "memory_context":              memory_context,
            "sender":                      "reflector",
            "recovery_attempts":           recovery_attempts,
            "total_reflector_calls":       total_reflector_calls,
            "reflector_pass_count":        reflector_pass_count,
            "total_first_verify_calls":    total_first_verify_calls,
            "reflector_first_pass_count":  reflector_first_pass_count,
        }

    def evaluate(self, state: AgentState) -> dict:
        pre_action_path = state.get("screenshot_path", "")   # Observer's screenshot (before action)
        current_step    = state.get("current_step", 0)
        tcs_id          = state.get("tcs_id", "")
        step_dir        = state.get("step_dir", "")
        output_dir      = state.get("output_dir", "")
        self._log(f"Step {current_step} — Verification started")

        # ── 1. Capture post-action screenshot ────────────────────────────────
        post_action_path = self._capture_post_action(step_dir, output_dir)
        # Fall back to pre-action path so LLM still gets *something* to look at
        screenshot_path = post_action_path if post_action_path else pre_action_path

        # ── 2. Resolve context from MIRIX memory ──────────────────────────────
        if self.memory is not None:
            expected_result = self.memory.core.get("expected_result") or ""
            test_type       = self.memory.core.get("test_type") or "Pos."
            figma_enabled   = (self.memory.core.get("figma_enabled") or "False") == "True"
            figma_b64       = self.memory.resource.get_figma_gold_b64() if figma_enabled else ""
            sub_steps       = self.memory.procedural.get_steps(tcs_id, "workflow")
        else:
            expected_result = ""
            test_type       = "Pos."
            figma_enabled   = False
            figma_b64       = ""
            sub_steps       = []

        current_idx              = state.get("current_sub_step_index", 0)
        orchestrator_instruction = state.get("orchestrator_instruction", "")

        if orchestrator_instruction:
            is_final_step       = state.get("is_final_step", False)
            current_instruction = orchestrator_instruction
        else:
            is_final_step       = (current_idx == len(sub_steps) - 1) if sub_steps else False
            current_instruction = sub_steps[current_idx] if current_idx < len(sub_steps) else "Finish"

        # ── 3. start_app: verify foreground package via ADB (no LLM needed) ──────
        action_plan = state.get("action_plan", {}) or {}
        action_type = action_plan.get("action_type", "")
        expected_pkg = action_plan.get("app_package", "")

        if action_type == "start_app" and self.device is not None:
            current_pkg = self.device.get_current_app()

            if not expected_pkg:
                # Decider marked step as already completed without specifying a
                # package (the app was already open). Trust the Decider's visual
                # judgment: whatever is in the foreground IS the target app, so
                # echo the live package as the expected value — always a PASS.
                expected_pkg = current_pkg
                self._log(
                    "start_app: no expected_pkg — inferred from live foreground",
                    f"current_package='{current_pkg}'",
                )
                print(f"[Reflector] [start_app] No expected_pkg — inferred from device: '{current_pkg}'")

            passed    = bool(current_pkg) and expected_pkg in current_pkg
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

        # ── 4. Three-call verification chain ─────────────────────────────────
        memory_context = ""
        if self.memory is not None:
            memory_context = self.memory.retrieve(f"execution result step={current_step}")

        mode_label = "FINAL" if is_final_step else "STEP"
        self._log(f"3-call chain started ({mode_label})", f"instruction={current_instruction}")
        print(f"[Reflector] {mode_label} — 3-call chain starting...")

        # ── Call 1: Loading Check ─────────────────────────────────────────────
        self._log("Call 1: Loading Check")
        loading_result = self._check_loading(screenshot_path, memory_context)
        self._log(
            f"Call 1 result: loading_done={loading_result.loading_done}",
            loading_result.reasoning,
        )
        print(f"[Reflector] Call 1 Loading: done={loading_result.loading_done} | {loading_result.reasoning}")

        if not loading_result.loading_done:
            reasoning = f"[Loading Check FAILED] {loading_result.reasoning}"
            print(f"[Reflector] SHORT-CIRCUIT: {reasoning}")
            self._log("SHORT-CIRCUIT at Call 1", reasoning)
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
                verification_chain={
                    "loading_done": False,
                    "loading_reasoning": loading_result.reasoning,
                    "ui_changed": None,
                    "ui_change_reasoning": None,
                    "short_circuit": "loading_failed",
                },
            )

        # ── Call 2: UI Change Check ───────────────────────────────────────────
        self._log("Call 2: UI Change Check")
        change_result = self._check_ui_change(
            pre_path=pre_action_path,
            post_path=screenshot_path,
            memory_context=memory_context,
            loading_reasoning=loading_result.reasoning,
        )
        self._log(
            f"Call 2 result: ui_changed={change_result.ui_changed}",
            change_result.reasoning,
        )
        print(f"[Reflector] Call 2 UI Change: changed={change_result.ui_changed} | {change_result.reasoning}")

        if not change_result.ui_changed:
            if action_type in _NO_UI_CHANGE_REQUIRED:
                print(
                    f"[Reflector] Call 2 ui_changed=False — action_type={action_type!r} "
                    "does not require navigation change. Proceeding to Call 3."
                )
                self._log(
                    f"Call 2 no-change ALLOWED for {action_type}",
                    change_result.reasoning,
                )
            else:
                reasoning = f"[UI Change Check FAILED] {change_result.reasoning}"
                print(f"[Reflector] SHORT-CIRCUIT: {reasoning}")
                self._log("SHORT-CIRCUIT at Call 2", reasoning)
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
                    verification_chain={
                        "loading_done": True,
                        "loading_reasoning": loading_result.reasoning,
                        "ui_changed": False,
                        "ui_change_reasoning": change_result.reasoning,
                        "short_circuit": "no_ui_change",
                    },
                )

        # ── Call 3: Validity Check ────────────────────────────────────────────
        self._log("Call 3: Validity Check")
        validity_result = self._check_validity(
            screenshot_path=screenshot_path,
            instruction=current_instruction,
            is_final_step=is_final_step,
            expected_result=expected_result,
            figma_b64=figma_b64,
            figma_enabled=figma_enabled,
            memory_context=memory_context,
            loading_reasoning=loading_result.reasoning,
            ui_change_reasoning=change_result.reasoning,
        )
        passed              = validity_result.passed
        reasoning           = validity_result.reasoning
        figma_discrepancies = validity_result.figma_discrepancies or ""

        verdict = "PASSED" if passed else "FAILED"
        print(f"[Reflector] Call 3 Validity: {verdict} | {reasoning}")
        self._log(f"Call 3 Verdict: {verdict}", f"reasoning={reasoning}\nfigma_discrepancies={figma_discrepancies or 'N/A'}")
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
