import os
from typing import TYPE_CHECKING, Any, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from core.models.state import AgentState
from core.utils.output_manager import build_step_dir
from core.utils.process_logger import LogLevel as _LL
from shared.prompts.predefined_orchestrator_prompts import (
    FIGMA_FLOW_EXAMPLES,
    FIGMA_FLOW_SYSTEM_PROMPT,
)
from shared.utils.llm_utils import parse_json_from_llm_output as _parse_json_from_llm

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


class NavigationContextAssessment(BaseModel):
    matched: bool = Field(
        description="Whether the observed screen satisfies the required navigation context."
    )
    reason: str = Field(
        description="Evidence-bounded reason for the context assessment."
    )


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
        self._navigation_llm = (
            llm.with_structured_output(NavigationContextAssessment) if llm else None
        )

    def _log(self, msg: str, detail: str = "", level=None):
        if self.logger is not None:
            lvl = level if level is not None else _LL.INFO
            self.logger.log("ORCHESTRATOR", msg, detail, level=lvl)

    def _extract_json_from_llm_output(self, raw_output: str) -> Any:
        """Delegate to shared JSON parsing utility. Returns parsed dict/list or None."""
        return _parse_json_from_llm(raw_output)

    def _invoke_with_recovery(
        self, messages, model_class, structured_llm, max_retries: int = 2
    ):
        """Invoke structured LLM with automatic JSON extraction retry."""
        last_error = None

        for attempt in range(max_retries):
            try:
                result = structured_llm.invoke(messages)
                if result is not None:
                    return result
                print(
                    f"[Orchestrator] Structured LLM returned None, attempting recovery..."
                )
                last_error = Exception("Structured LLM returned None")
            except Exception as e:
                error_str = str(e)
                last_error = e

                if (
                    "json_invalid" not in error_str
                    and "Invalid JSON" not in error_str
                    and "missing" not in error_str.lower()
                ):
                    raise

                if attempt < max_retries - 1:
                    try:
                        print(
                            f"[Orchestrator] Attempting JSON recovery (attempt {attempt + 1})..."
                        )
                        raw_response = self.llm.invoke(messages)
                        raw_text = (
                            raw_response.content
                            if hasattr(raw_response, "content")
                            else str(raw_response)
                        )

                        extracted = self._extract_json_from_llm_output(raw_text)
                        if extracted:
                            print(
                                f"[Orchestrator] Extracted JSON keys: {list(extracted.keys()) if isinstance(extracted, dict) else 'N/A'}"
                            )
                            if isinstance(extracted, dict):
                                if model_class.__name__ == "FigmaFlowPlan":
                                    reasoning = (
                                        extracted.get("reasoning")
                                        or extracted.get("thinking")
                                        or extracted.get("analysis")
                                        or extracted.get("explanation")
                                        or "Auto-recovered JSON"
                                    )
                                    path_ids = extracted.get("path_ids")
                                    if path_ids is None:
                                        for key in extracted.keys():
                                            if (
                                                isinstance(extracted[key], list)
                                                and len(extracted[key]) > 0
                                            ):
                                                if isinstance(
                                                    extracted[key][0], str
                                                ) and ":" in str(extracted[key][0]):
                                                    path_ids = extracted[key]
                                                    print(
                                                        f"[Orchestrator] Found path_ids under key '{key}': {path_ids}"
                                                    )
                                                    break
                                    path_ids = path_ids or []
                                    print(
                                        f"[Orchestrator] Creating FigmaFlowPlan with reasoning='{reasoning[:50]}...', path_ids={path_ids}"
                                    )
                                    return FigmaFlowPlan(
                                        reasoning=reasoning, path_ids=path_ids
                                    )
                                elif model_class.__name__ == "BridgePlan":
                                    reasoning = (
                                        extracted.get("reasoning")
                                        or extracted.get("thinking")
                                        or extracted.get("analysis")
                                        or extracted.get("explanation")
                                        or "Auto-recovered JSON"
                                    )
                                    bridge_steps = extracted.get("bridge_steps", [])
                                    print(
                                        f"[Orchestrator] Creating BridgePlan with reasoning='{reasoning[:50]}...'"
                                    )
                                    return BridgePlan(
                                        reasoning=reasoning, bridge_steps=bridge_steps
                                    )
                        else:
                            print(
                                f"[Orchestrator] JSON extraction returned None. Raw text preview: {raw_text[:200]}..."
                            )
                    except Exception as inner_e:
                        print(
                            f"[Orchestrator] JSON recovery attempt {attempt + 1} failed: {inner_e}"
                        )

                if attempt < max_retries - 1:
                    messages.append(
                        AIMessage(
                            content="IMPORTANT: Return ONLY a valid JSON object with ALL required fields. No XML tags. No extra text."
                        )
                    )

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

        messages = [SystemMessage(content=FIGMA_FLOW_SYSTEM_PROMPT)]
        for role, content in FIGMA_FLOW_EXAMPLES:
            if role == "human":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))
        messages.append(HumanMessage(content=human_content))

        print(f"[Predefined] Planning Figma flow for '{menu_name}'...")
        try:
            result = self._invoke_with_recovery(
                messages, FigmaFlowPlan, self._mapping_llm
            )

            if not result.path_ids:
                print(
                    "[Predefined] LLM could not resolve a Figma path. Falling back to text-only."
                )
                return {
                    "figma_enabled": False,
                    "figma_start_node_id": "",
                    "figma_end_node_id": "",
                    "figma_end_screenshot_b64": "",
                }

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
            return {
                "figma_enabled": False,
                "figma_start_node_id": "",
                "figma_end_node_id": "",
                "figma_end_screenshot_b64": "",
            }

    def compute_bridge(
        self, current_screen_description: str, next_start_node_id: str
    ) -> list:
        """Compute minimal navigation steps from the current screen to the next scenario's start."""
        if not self.figma or not self._bridge_llm:
            return []
        next_context = self.figma.get_node_context(next_start_node_id)
        next_screen_name = next_context.get("document", {}).get(
            "name", next_start_node_id
        )
        return self.plan_recovery_transition(
            observation_text=current_screen_description,
            required_context=str(next_screen_name),
            figma_context={"figma_start_node_id": next_start_node_id},
        )

    def assess_navigation_context(
        self, *, observation_text: str, required_context: str
    ) -> dict[str, Any]:
        """Assess the live observation against workbook navigation text."""
        if self._navigation_llm is None:
            raise RuntimeError("Navigation context cannot be verified without an orchestrator LLM.")
        result = self._navigation_llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Assess only whether the observed Android screen satisfies the required "
                        "starting navigation context. Do not infer unobserved state."
                    )
                ),
                HumanMessage(
                    content=(
                        f"OBSERVED SCREEN:\n{observation_text}\n\n"
                        f"REQUIRED NAVIGATION CONTEXT:\n{required_context}"
                    )
                ),
            ]
        )
        if result is None:
            raise RuntimeError("Navigation context assessment returned no result.")
        return {"matched": bool(result.matched), "reason": str(result.reason)}

    def plan_recovery_transition(
        self,
        *,
        observation_text: str,
        required_context: str,
        figma_context: dict[str, Any] | None = None,
    ) -> list[str]:
        """Plan operational navigation from text; Figma details are optional hints."""
        if self._bridge_llm is None:
            raise RuntimeError("Navigation recovery cannot be planned without an orchestrator LLM.")
        figma_context = figma_context or {}
        figma_hint = str(figma_context.get("figma_start_node_id") or "not available")
        result = self._bridge_llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Plan the smallest operational Android navigation transition. "
                        "These are setup actions, never QA test steps."
                    )
                ),
                HumanMessage(
                    content=(
                        f"CURRENT SCREEN:\n{observation_text}\n\n"
                        f"REQUIRED NAVIGATION CONTEXT:\n{required_context}\n\n"
                        f"OPTIONAL FIGMA START NODE:\n{figma_hint}"
                    )
                ),
            ]
        )
        if result is None:
            raise RuntimeError("Navigation recovery planning returned no result.")
        return [str(step).strip() for step in result.bridge_steps if str(step).strip()]

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
            f"last_reflector_passed={last_passed}",
        )

        print(
            f"[Orchestrator] Step {current_idx + 1} | from={sender} | reflector={'PASS' if last_passed else 'FAIL'} | retry={retry_count}"
        )

        last_reasoning = state.get("last_reflector_reasoning", "")
        is_system_error = (
            "[SYSTEM_ERROR]" in last_reasoning if last_reasoning else False
        )
        technical_error_history = list(state.get("technical_error_history", []))

        if sender == "reflector":
            if last_passed:
                current_idx += 1
                retry_count = 0
                self._log(
                    f"Step {current_idx - 1} verified — advancing to index {current_idx}"
                )
            elif is_system_error:
                print(
                    f"[Orchestrator] ⚠ Reflector system error detected - not retrying app action"
                )
                self._log(
                    f"SYSTEM ERROR from Reflector — treating as technical failure, not app failure"
                )
                entry = {"step": global_step, "reason": last_reasoning}
                if entry not in technical_error_history:
                    technical_error_history.append(entry)
                return {
                    "is_completed": True,
                    "sender": "orchestrator",
                    "failure_reason": last_reasoning,
                    "technical_error_history": technical_error_history,
                }
            else:
                retry_count += 1
                print(f"[Orchestrator] ⚠ Step failed — retry {retry_count}/3")
                self._log(
                    f"Step FAILED — retry {retry_count}/3 for index {current_idx}"
                )

        if retry_count > 3:
            print("[Orchestrator] ✗ Maximum retries (3) exceeded — aborting scenario.")
            self._log("ABORT — maximum retries (3) exceeded")
            if self.memory is not None:
                self.memory.update(
                    {
                        "episodic": {
                            "event_type": "orchestrator_decision",
                            "summary": "Maximum retries exceeded. Aborting scenario.",
                            "details": "",
                            "actor": "orchestrator",
                            "step": global_step,
                        }
                    }
                )
            return {
                "is_completed": True,
                "sender": "orchestrator",
                "retry_exhausted": True,
                "failure_reason": "Maximum QA verification retries exceeded.",
                "technical_error_history": technical_error_history,
            }

        steps_completed_count = state.get("steps_completed_count", 0)
        if sender == "reflector" and last_passed:
            steps_completed_count += 1

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
            "technical_error_history": technical_error_history,
            "retry_exhausted": state.get("retry_exhausted", False),
        }

        if current_idx < len(sub_steps):
            step_dir = build_step_dir(output_dir, current_idx + 1, retry_count)

            update_data["step_dir"] = step_dir
            update_data["is_completed"] = False
            print(f"[Predefined] Dispatching: {sub_steps[current_idx]}")
            self._log(
                f"→ Dispatching step {current_idx + 1}/{len(sub_steps)}",
                sub_steps[current_idx],
            )

            if self.memory is not None:
                self.memory.update(
                    {
                        "episodic": {
                            "event_type": "orchestrator_decision",
                            "summary": f"Dispatching step {current_idx + 1}: {sub_steps[current_idx]}",
                            "details": "",
                            "actor": "orchestrator",
                            "step": global_step + 1,
                        }
                    }
                )
        else:
            completion_msg = f"All {len(sub_steps)} predefined sub-steps completed and verified successfully."
            update_data["is_completed"] = True
            print("[Predefined] All steps verified. Scenario success.")
            self._log("→ ALL STEPS COMPLETE — scenario success", completion_msg)

            if self.memory is not None:
                self.memory.update(
                    {
                        "episodic": {
                            "event_type": "orchestrator_decision",
                            "summary": completion_msg,
                            "details": "",
                            "actor": "orchestrator",
                            "step": global_step + 1,
                        }
                    }
                )

        return update_data
