import base64
import json
import os
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from core.models.state import AgentState
from core.utils.toons_helper import compress_and_report

import cv2


class ReflectorResult(BaseModel):
    passed: bool = Field(description="True if the action achieved its micro-goal OR if the final expected result is satisfied.")
    reasoning: str = Field(description="Explanation of the visual state vs expectations. Crucial for self-correction retries.")
    figma_discrepancies: str = Field(default="", description="If Figma Gold Standard was used, describe any layout, color, or structural differences found between the live app and the Figma design. Empty if no Figma comparison was performed.")


class ReflectorAgent:
    def __init__(self, llm, memory=None, logger=None):
        self.llm = llm.with_structured_output(ReflectorResult)
        self.logger = logger
        self.memory = memory

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

    def evaluate(self, state: AgentState) -> dict:
        screenshot_path = state.get("screenshot_path", "")
        current_step = state.get("current_step", 0)
        tcs_id = state.get("tcs_id", "")
        self._log(f"Step {current_step} — Verification started")

        # ── Resolve context from MIRIX memory (fallback to state for non-MIRIX callers) ──
        if self.memory is not None:
            expected_result = self.memory.core.get("expected_result") or ""
            test_type = self.memory.core.get("test_type") or "Pos."
            figma_enabled = (self.memory.core.get("figma_enabled") or "False") == "True"
            figma_b64 = self.memory.resource.get_figma_gold_b64() if figma_enabled else ""
            sub_steps = self.memory.procedural.get_steps(tcs_id, "workflow")
        else:
            expected_result = ""
            test_type = "Pos."
            figma_enabled = False
            figma_b64 = ""
            sub_steps = []

        current_idx = state.get("current_sub_step_index", 0)
        orchestrator_instruction = state.get("orchestrator_instruction", "")

        # Autonomous mode trusts orchestrator's is_final_step signal.
        # Predefined mode derives it from the sub_steps index.
        if orchestrator_instruction:
            is_final_step = state.get("is_final_step", False)
            current_instruction = orchestrator_instruction
        else:
            is_final_step = (current_idx == len(sub_steps) - 1) if sub_steps else False
            current_instruction = sub_steps[current_idx] if current_idx < len(sub_steps) else "Finish"

        system_instruction = (
            "You are the Reflector Agent in a self-correcting MAS AI framework.\n"
            "Your task is to verify if the UI state matches the intended outcome of the current test step.\n\n"
            f"CURRENT STEP INSTRUCTION: {current_instruction}\n"
        )

        if is_final_step:
            if figma_enabled and figma_b64:
                system_instruction += (
                    "CRITICAL: This is the FINAL step. Perform a 3-WAY VERIFICATION:\n"
                    "1. Confirm the LIVE APP SCREENSHOT matches the EXPECTED RESULT from the test suite.\n"
                    "2. Compare the LIVE APP SCREENSHOT against the FIGMA GOLD STANDARD SCREENSHOT.\n"
                    "   - Note any layout, color, content, or structural discrepancies.\n"
                    "   - Minor pixel differences are acceptable. Major missing elements are NOT.\n"
                    f"ULTIMATE EXPECTED RESULT: {expected_result}\n"
                )
                print("[Reflector] FINAL Verification with Figma Gold Standard")
            else:
                system_instruction += (
                    "CRITICAL: This is the FINAL step. You MUST also verify if the screen matches the ultimate Expected Result from the test suite.\n"
                    f"ULTIMATE EXPECTED RESULT: {expected_result}\n"
                )
                print("[Reflector] FINAL Verification (text-only mode)")
        else:
            system_instruction += (
                "This is an intermediate step. Verify if the UI changed successfully in response to the last action.\n"
                "If the screen is frozen or the action didn't trigger a change, return passed=False."
            )

        # ── Active Retrieval: inject recent action context ─────────────────────
        memory_context = ""
        if self.memory is not None:
            memory_context = self.memory.retrieve(f"execution result step={current_step}")

        content = [{"type": "text", "text": f"Recent Action Context:\n{memory_context}" if memory_context else "No memory context."}]

        if screenshot_path:
            try:
                base64_image = self._encode_image(screenshot_path)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/webp;base64,{base64_image}"},
                })
                content.append({"type": "text", "text": "[Image above: LIVE APP screenshot]"})
            except Exception:
                pass

        if is_final_step and figma_enabled and figma_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{figma_b64}"},
            })
            content.append({"type": "text", "text": "[Image above: FIGMA GOLD STANDARD - the intended design for this end state]"})

        messages = [
            SystemMessage(content=system_instruction),
            HumanMessage(content=content)
        ]

        mode_label = "FINAL" if is_final_step else "STEP"
        figma_label = " + Figma Gold Standard" if (is_final_step and figma_enabled and figma_b64) else ""
        self._log(
            f"LLM call started ({mode_label} verification{figma_label})",
            f"instruction={current_instruction}\nexpected_result={expected_result[:200]}"
        )
        print(f"[Reflector] {mode_label} Verification starting...")

        try:
            result = self.llm.invoke(messages)
            passed = result.passed
            reasoning = result.reasoning
            figma_discrepancies = getattr(result, "figma_discrepancies", "")
        except Exception as e:
            passed = False
            reasoning = f"Evaluation LLM error: {str(e)}"
            figma_discrepancies = ""

        verdict = "PASSED" if passed else "FAILED"
        print(f"[Reflector] Result: {verdict} | Reasoning: {reasoning}")
        self._log(
            f"Verdict: {verdict}",
            f"reasoning={reasoning}\nfigma_discrepancies={figma_discrepancies or 'N/A'}"
        )
        if figma_discrepancies:
            print(f"[Reflector] Figma Discrepancies: {figma_discrepancies}")

        # ── Persist report to disk ─────────────────────────────────────────────
        output_dir = state.get("output_dir", "")
        step_dir = state.get("step_dir", "")
        save_dir = step_dir if step_dir else output_dir
        if save_dir:
            ref_path = os.path.join(save_dir, "reflector_report.json")
            with open(ref_path, "w", encoding="utf-8") as f:
                json.dump({
                    "passed": passed,
                    "reasoning": reasoning,
                    "step_index": current_idx,
                    "figma_enabled": figma_enabled,
                    "figma_discrepancies": figma_discrepancies,
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

        # ── Memory Update ─────────────────────────────────────────────────────
        if self.memory is not None:
            self.memory.update({
                "episodic": {
                    "event_type": "reflector_evaluation",
                    "summary": f"{'PASSED' if passed else 'FAILED'}: {reasoning[:150]}",
                    "details": reasoning,
                    "actor": "reflector",
                    "step": current_step,
                }
            })

        # ── Metric tracking ───────────────────────────────────────────────────
        recovery_attempts = state.get("recovery_attempts", 0)
        if not passed:
            recovery_attempts += 1

        total_reflector_calls = state.get("total_reflector_calls", 0) + 1
        reflector_pass_count = state.get("reflector_pass_count", 0) + (1 if passed else 0)
        is_first = state.get("is_first_verify_attempt", True)
        total_first_verify_calls = state.get("total_first_verify_calls", 0) + (1 if is_first else 0)
        reflector_first_pass_count = state.get("reflector_first_pass_count", 0) + (1 if is_first and passed else 0)

        if self.logger is not None:
            self.logger.separator()

        return {
            "last_reflector_passed": passed,
            "memory_context": memory_context,
            "sender": "reflector",
            "recovery_attempts": recovery_attempts,
            "total_reflector_calls": total_reflector_calls,
            "reflector_pass_count": reflector_pass_count,
            "total_first_verify_calls": total_first_verify_calls,
            "reflector_first_pass_count": reflector_first_pass_count,
        }
