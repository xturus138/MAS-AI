import os
import json
import re
from typing import Optional, TYPE_CHECKING, Any
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage
from core.models.state import AgentState
from shared.prompts.predefined_orchestrator_prompts import (
    FIGMA_FLOW_SYSTEM_PROMPT,
    FIGMA_FLOW_EXAMPLES,
    BRIDGE_SYSTEM_PROMPT,
    BRIDGE_EXAMPLES,
)
from core.utils.process_logger import LogLevel as _LL
from core.utils.output_manager import build_step_dir

if TYPE_CHECKING:
    from adapters.figma.figma_adapter import FigmaAdapter
    from memory.meta_manager import MIRIXMemorySystem


class BridgePlan(BaseModel):
    """Chain-of-Thought: reasoning MUST be first field."""
    reasoning: str = Field(
        description="Analyze current vs target screen step-by-step before determining bridge steps."
    )
    bridge_steps: list = Field(
        description=(
            "Ordered list of navigation steps to move from the current screen "
            "to the required starting screen for the next scenario. "
            "Each step is a plain string instruction like 'click Back' or 'click Home button'."
        )
    )


class FigmaFlowPlan(BaseModel):
    """Chain-of-Thought: reasoning MUST be first field."""
    reasoning: str = Field(
        description="Analyze scenario context and Figma graph step-by-step before selecting path."
    )
    path_ids: list = Field(
        description=(
            "The ordered list of Figma Node IDs (e.g. ['10:5', '12:1']) that represent "
            "the full prototype flow from the start screen to the expected end screen "
            "for this scenario. Return an empty list if no path can be resolved."
        )
    )


# Note: BRIDGE_SYSTEM_PROMPT now imported from shared.prompts.predefined_orchestrator_prompts


class PredefinedOrchestrator:
    """
    Orchestrator for the Predefined (Scenario-Based) workflow.

    Responsibilities:
    - Manage step index and retry logic based on Reflector feedback.
    - Discover Figma nodes before each scenario.
    - Compute bridge navigation steps between consecutive scenarios.
    """

    def __init__(self, llm=None, figma_adapter=None, memory=None, logger=None):
        self.llm = llm
        self.figma: Optional["FigmaAdapter"] = figma_adapter
        self.memory: Optional["MIRIXMemorySystem"] = memory
        self.logger = logger
        self._bridge_llm = llm.with_structured_output(BridgePlan) if llm else None
        self._mapping_llm = llm.with_structured_output(FigmaFlowPlan) if llm else None

    def _log(self, msg: str, detail: str = "", level=None):
        if self.logger is not None:
            lvl = level if level is not None else _LL.INFO
            self.logger.log("ORCHESTRATOR", msg, detail, level=lvl)

    def _extract_json_from_llm_output(self, raw_output: str) -> Any:
        """Safely extract JSON from LLM output that may contain XML tags or extra text."""
        if not raw_output:
            return None

        cleaned = raw_output.strip()

        # Strategy 1: Content inside <thinking> tags
        if "<thinking>" in cleaned and "</thinking>" in cleaned:
            start = cleaned.find("<thinking>")
            end = cleaned.find("</thinking>")
            if start != -1 and end != -1:
                inner = cleaned[start + len("<thinking>"):end].strip()
                try:
                    return json.loads(inner)
                except json.JSONDecodeError:
                    pass
                cleaned = inner

        # Strategy 2: Extract JSON object via brace matching
        brace_depth = 0
        json_start = -1
        in_string = False
        escape_next = False

        for i, char in enumerate(cleaned):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue

            if char == '{':
                if brace_depth == 0:
                    json_start = i
                brace_depth += 1
            elif char == '}':
                brace_depth -= 1
                if brace_depth == 0 and json_start != -1:
                    candidate = cleaned[json_start:i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        continue

        # Strategy 3: Look for JSON array format
        if json_start == -1 and '[' in cleaned:
            bracket_depth = 0
            arr_start = -1
            for i, char in enumerate(cleaned):
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == '[':
                    if bracket_depth == 0:
                        arr_start = i
                    bracket_depth += 1
                elif char == ']':
                    bracket_depth -= 1
                    if bracket_depth == 0 and arr_start != -1:
                        candidate = cleaned[arr_start:i + 1]
                        try:
                            return json.loads(candidate)
                        except json.JSONDecodeError:
                            continue

        return None

    def _invoke_with_recovery(self, messages, model_class, structured_llm, max_retries: int = 2):
        """Invoke structured LLM with automatic JSON extraction retry."""
        last_error = None

        for attempt in range(max_retries):
            try:
                return structured_llm.invoke(messages)
            except Exception as e:
                error_str = str(e)
                last_error = e

                # Check if this is a JSON parsing error
                if "json_invalid" not in error_str and "Invalid JSON" not in error_str and "missing" not in error_str.lower():
                    raise  # Not a JSON/parsing error, re-raise

                # Try to get raw output for recovery
                if attempt < max_retries - 1:
                    try:
                        print(f"[Orchestrator] Attempting JSON recovery (attempt {attempt + 1})...")
                        # We use self.llm which is the base LLM without structured output
                        raw_response = self.llm.invoke(messages)
                        raw_text = raw_response.content if hasattr(raw_response, 'content') else str(raw_response)

                        # Try to extract JSON
                        extracted = self._extract_json_from_llm_output(raw_text)
                        if extracted:
                            print(f"[Orchestrator] Extracted JSON keys: {list(extracted.keys()) if isinstance(extracted, dict) else 'N/A'}")
                            # Parse manually and create model instance
                            if isinstance(extracted, dict):
                                # For FigmaFlowPlan
                                if model_class.__name__ == "FigmaFlowPlan":
                                    # Try multiple possible field names for reasoning and path_ids
                                    reasoning = (
                                        extracted.get("reasoning") or
                                        extracted.get("thinking") or
                                        extracted.get("analysis") or
                                        extracted.get("explanation") or
                                        "Auto-recovered JSON"
                                    )
                                    path_ids = extracted.get("path_ids")
                                    if path_ids is None:
                                        # Try alternative field names
                                        for key in extracted.keys():
                                            if isinstance(extracted[key], list) and len(extracted[key]) > 0:
                                                if isinstance(extracted[key][0], str) and ":" in str(extracted[key][0]):
                                                    path_ids = extracted[key]
                                                    print(f"[Orchestrator] Found path_ids under key '{key}': {path_ids}")
                                                    break
                                    path_ids = path_ids or []
                                    print(f"[Orchestrator] Creating FigmaFlowPlan with reasoning='{reasoning[:50]}...', path_ids={path_ids}")
                                    return FigmaFlowPlan(
                                        reasoning=reasoning,
                                        path_ids=path_ids
                                    )
                                # For BridgePlan
                                elif model_class.__name__ == "BridgePlan":
                                    reasoning = (
                                        extracted.get("reasoning") or
                                        extracted.get("thinking") or
                                        extracted.get("analysis") or
                                        extracted.get("explanation") or
                                        "Auto-recovered JSON"
                                    )
                                    bridge_steps = extracted.get("bridge_steps", [])
                                    print(f"[Orchestrator] Creating BridgePlan with reasoning='{reasoning[:50]}...'")
                                    return BridgePlan(
                                        reasoning=reasoning,
                                        bridge_steps=bridge_steps
                                    )
                        else:
                            print(f"[Orchestrator] JSON extraction returned None. Raw text preview: {raw_text[:200]}...")
                    except Exception as inner_e:
                        print(f"[Orchestrator] JSON recovery attempt {attempt + 1} failed: {inner_e}")

                # Modify prompt for retry - ask for cleaner output
                if attempt < max_retries - 1:
                    messages.append(SystemMessage(content=
                        "IMPORTANT: Return ONLY a valid JSON object with ALL required fields. No XML tags. No extra text."
                    ))

        # All retries exhausted
        raise last_error

    def pre_scenario_discovery(self, scenario: dict, output_dir: str) -> dict:
        """
        Analyzes the Figma prototype flow and test scenario to determine
        the start screen and the expected path.

        Returns figma_context dict that is passed to memory.init_session().
        The figma_end_screenshot_b64 is stored in Resource Memory, not AgentState.
        """
        figma_enabled = self.figma is not None
        if not figma_enabled:
            return {
                "figma_enabled": False,
                "figma_start_node_id": "",
                "figma_end_node_id": "",
                "figma_end_screenshot_b64": "",
            }

        menu_name = scenario.get("navigation_context", "")
        scenario_desc = scenario.get("scenario_desc", "")
        sub_steps_raw = "\n".join([f"- {s}" for s in scenario.get("sub_steps", [])])

        flow_summary = self.figma.get_flow_summary()

        human_content = (
            f"TEST SCENARIO:\n"
            f"  Menu Context: {menu_name}\n"
            f"  Description: {scenario_desc}\n"
            f"  Test Steps:\n{sub_steps_raw}\n\n"
            f"FIGMA PROTOTYPE GRAPH:\n{flow_summary}"
        )

        # Build messages with Few-Shot examples for Figma flow planning
        messages = [SystemMessage(content=FIGMA_FLOW_SYSTEM_PROMPT)]
        for role, content in FIGMA_FLOW_EXAMPLES:
            if role == "human":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(SystemMessage(content=content))
        messages.append(HumanMessage(content=human_content))

        print(f"[Predefined] Planning Figma flow for '{menu_name}'...")
        try:
            result = self._invoke_with_recovery(messages, FigmaFlowPlan, self._mapping_llm)

            if not result.path_ids:
                print("[Predefined] LLM could not resolve a Figma path. Falling back to text-only.")
                return {"figma_enabled": False, "figma_start_node_id": "", "figma_end_node_id": "", "figma_end_screenshot_b64": ""}

            start_id = result.path_ids[0]
            end_id = result.path_ids[-1]
            print(f"[Predefined] Flow Planned: {result.path_ids} ({result.reasoning})")

            figma_end_screenshot_b64 = self.figma.get_node_screenshot_b64(end_id)

            figma_dir = os.path.join(output_dir, "figma")
            os.makedirs(figma_dir, exist_ok=True)
            gold_standard_path = os.path.join(figma_dir, "gold_standard.png")
            self.figma.save_composite_gold_standard(result.path_ids, gold_standard_path)

            return {
                "figma_enabled": True,
                "figma_start_node_id": start_id,
                "figma_end_node_id": end_id,
                "figma_end_screenshot_b64": figma_end_screenshot_b64,
            }
        except Exception as e:
            print(f"[Predefined] Figma flow planning failed: {e}")
            return {"figma_enabled": False, "figma_start_node_id": "", "figma_end_node_id": "", "figma_end_screenshot_b64": ""}

    # ── Bridge Navigation ─────────────────────────────────────────────────────

    def compute_bridge(self, current_screen_description: str, next_start_node_id: str) -> list:
        """Compute minimal navigation steps from the current screen to the next scenario's start."""
        if not self.figma or not self._bridge_llm:
            return []

        next_context = self.figma.get_node_context(next_start_node_id)
        next_screen_name = next_context.get("document", {}).get("name", next_start_node_id)

        human_content = (
            f"CURRENT SCREEN (where the app is now):\n{current_screen_description}\n\n"
            f"REQUIRED STARTING SCREEN (for next scenario):\n{next_screen_name}\n"
            f"Figma Node ID: {next_start_node_id}"
        )

        # Build messages with Few-Shot examples for bridge navigation
        messages = [SystemMessage(content=BRIDGE_SYSTEM_PROMPT)]
        for role, content in BRIDGE_EXAMPLES:
            if role == "human":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(SystemMessage(content=content))
        messages.append(HumanMessage(content=human_content))

        print(f"[Predefined] Computing navigation bridge to '{next_screen_name}'...")
        try:
            result = self._bridge_llm.invoke(messages)
            print(f"[Predefined] Bridge plan: {result.bridge_steps}")
            return result.bridge_steps
        except Exception as e:
            print(f"[Predefined] Bridge computation failed: {e}")
            return []

    # ── LangGraph Node ────────────────────────────────────────────────────────

    def orchestrate(self, state: AgentState) -> dict:
        """LangGraph node: index-manager that advances or retries sub-steps."""
        tcs_id = state.get("tcs_id", "")
        current_idx = state.get("current_sub_step_index", 0)
        global_step = state.get("current_step", 0)
        output_dir = state.get("output_dir", "outputs")
        retry_count = state.get("step_retry_count", 0)

        last_passed = state.get("last_reflector_passed", True)
        sender = state.get("sender", "START")

        if self.logger is not None:
            self.logger.section(f"CYCLE {global_step} — ORCHESTRATOR (predefined)")
        self._log(
            f"Entered from sender={sender}  step_index={current_idx}  retry={retry_count}",
            f"last_reflector_passed={last_passed}"
        )

        print(f"[Orchestrator] Step {current_idx + 1} | from={sender} | reflector={'PASS' if last_passed else 'FAIL'} | retry={retry_count}")

        # Check if last failure was a system error (not a real validation failure)
        last_reasoning = state.get("last_reflector_reasoning", "")
        is_system_error = "[SYSTEM_ERROR]" in last_reasoning if last_reasoning else False

        # Advance or retry based on reflector outcome
        if sender == "reflector":
            if last_passed:
                current_idx += 1
                retry_count = 0
                self._log(f"Step {current_idx - 1} verified — advancing to index {current_idx}")
            elif is_system_error:
                # System error (e.g., LLM JSON parsing) - don't count as app failure
                print(f"[Orchestrator] ⚠ Reflector system error detected - not retrying app action")
                self._log(f"SYSTEM ERROR from Reflector — treating as technical failure, not app failure")
                # Continue to next step (don't retry the app action)
                current_idx += 1
                retry_count = 0
            else:
                retry_count += 1
                print(f"[Orchestrator] ⚠ Step failed — retry {retry_count}/3")
                self._log(f"Step FAILED — retry {retry_count}/3 for index {current_idx}")

        if retry_count > 3:
            print("[Orchestrator] ✗ Maximum retries (3) exceeded — aborting scenario.")
            self._log("ABORT — maximum retries (3) exceeded")
            if self.memory is not None:
                self.memory.update({
                    "episodic": {
                        "event_type": "orchestrator_decision",
                        "summary": "Maximum retries exceeded. Aborting scenario.",
                        "details": "",
                        "actor": "orchestrator",
                        "step": global_step,
                    }
                })
            return {
                "is_completed": True,
                "sender": "orchestrator",
                "stagnation_count": 99,
            }

        steps_completed_count = state.get("steps_completed_count", 0)
        if sender == "reflector" and last_passed:
            steps_completed_count += 1

        # Read sub_steps from Procedural Memory
        sub_steps = []
        if self.memory is not None:
            sub_steps = self.memory.procedural.get_steps(tcs_id, "workflow")

        update_data = {
            "current_sub_step_index": current_idx,
            "current_step": global_step + 1,
            "step_retry_count": retry_count,
            "sender": "orchestrator",
            "is_first_verify_attempt": (retry_count == 0),
            "steps_completed_count": steps_completed_count,
        }

        if current_idx < len(sub_steps):
            step_dir = build_step_dir(output_dir, current_idx + 1, retry_count)

            update_data["step_dir"] = step_dir
            update_data["is_completed"] = False
            print(f"[Predefined] Dispatching: {sub_steps[current_idx]}")
            self._log(f"→ Dispatching step {current_idx + 1}/{len(sub_steps)}", sub_steps[current_idx])

            if self.memory is not None:
                self.memory.update({
                    "episodic": {
                        "event_type": "orchestrator_decision",
                        "summary": f"Dispatching step {current_idx + 1}: {sub_steps[current_idx]}",
                        "details": "",
                        "actor": "orchestrator",
                        "step": global_step + 1,
                    }
                })
        else:
            completion_msg = f"All {len(sub_steps)} predefined sub-steps completed and verified successfully."
            update_data["is_completed"] = True
            print("[Predefined] All steps verified. Scenario success.")
            self._log("→ ALL STEPS COMPLETE — scenario success", completion_msg)

            if self.memory is not None:
                self.memory.update({
                    "episodic": {
                        "event_type": "orchestrator_decision",
                        "summary": completion_msg,
                        "details": "",
                        "actor": "orchestrator",
                        "step": global_step + 1,
                    }
                })

        return update_data
