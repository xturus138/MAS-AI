import base64
import json
import os
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from core.models.state import AgentState
from core.utils.toons_helper import compress_and_report, prune_history_by_tokens

import cv2

class ReflectorResult(BaseModel):
    passed: bool = Field(description="True if the action achieved its micro-goal OR if the final expected result is satisfied.")
    reasoning: str = Field(description="Explanation of the visual state vs expectations. Crucial for self-correction retries.")

class ReflectorAgent:
    def __init__(self, llm):
        self.llm = llm.with_structured_output(ReflectorResult)

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
        expected_result = state.get("expected_result", "")
        test_type = state.get("test_type", "Pos.")
        sub_steps = state.get("sub_steps", [])
        current_idx = state.get("current_sub_step_index", 0)
        
        is_final_step = (current_idx == len(sub_steps) - 1)
        current_instruction = sub_steps[current_idx] if current_idx < len(sub_steps) else "Finish"

        history = list(state.get("action_history") or [])
        history = prune_history_by_tokens(history, max_tokens=3000)
        history_json = compress_and_report(history, "action_history", "reflector")

        system_instruction = (
            "You are the Reflector Agent in a self-correcting MAS AI framework.\n"
            "Your task is to verify if the UI state matches the intended outcome of the current test step.\n\n"
            f"CURRENT STEP INSTRUCTION: {current_instruction}\n"
        )
        
        if is_final_step:
            system_instruction += (
                "CRITICAL: This is the FINAL step. You MUST also verify if the screen matches the ultimate Expected Result from the test suite.\n"
                f"ULTIMATE EXPECTED RESULT: {expected_result}\n"
            )
        else:
            system_instruction += (
                "This is an intermediate step. Verify if the UI changed successfully in response to the last action.\n"
                "If the screen is frozen or the action didn't trigger a change, return passed=False."
            )

        content = [{"type": "text", "text": f"Recent Actions:\n{history_json}"}]

        if screenshot_path:
            try:
                base64_image = self._encode_image(screenshot_path)
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/webp;base64,{base64_image}"}
                })
            except:
                pass

        messages = [
            SystemMessage(content=system_instruction),
            HumanMessage(content=content)
        ]

        print(f"[Reflector] {'FINAL' if is_final_step else 'STEP'} Verification starting...")
        
        try:
            result = self.llm.invoke(messages)
            passed = result.passed
            reasoning = result.reasoning
        except Exception as e:
            passed = False
            reasoning = f"Evaluation LLM error: {str(e)}"
            
        print(f"[Reflector] Result: {'PASSED' if passed else 'FAILED'} | Reasoning: {reasoning}")
        
        output_dir = state.get("output_dir", "")
        if output_dir:
            ref_path = os.path.join(output_dir, "reflector_report.json")
            with open(ref_path, "w", encoding="utf-8") as f:
                json.dump({"passed": passed, "reasoning": reasoning, "step_index": current_idx}, f, indent=4, ensure_ascii=False)
        
        chat_entry = {
            "agent": "reflector",
            "step": state.get("current_step", 0),
            "content": f"RESPONSE:\nPassed: {passed}\nReasoning: {reasoning}"
        }
        new_chat_logs = state.get("chat_logs", []) + [chat_entry]

        return {
            "reflector_reasoning": reasoning,
            "last_reflector_passed": passed,
            "sender": "reflector",
            "chat_logs": new_chat_logs
        }
