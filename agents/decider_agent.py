from typing import Literal, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from core.models.state import AgentState
from core.ports.llm_port import ILLMClient


class ActionPlan(BaseModel):
    action_type: Literal[
        "click", "long_click", "input", "scroll",
        "press_back", "press_home", "press_enter", "start_app"
    ]
    intent: str = Field(
        description="Brief description of what this action aims to achieve toward the overall goal."
    )
    target_description: str = Field(
        description="Description of the target widget matched or predicted from Observer output."
    )
    target_x: int = Field(
        description="Final adjusted X coordinate for click or input actions. Use 0 if not applicable."
    )
    target_y: int = Field(
        description="Final adjusted Y coordinate for click or input actions. Use 0 if not applicable."
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
        description="True if the overall goal has been fully achieved and no further actions are needed."
    )


SYSTEM_PROMPT = """You are the Decider Agent in an Android GUI testing multi-agent system.

Your role is to receive the current screen state from the Observer and produce exactly ONE structured ActionPlan for the Executor to carry out.

The Executor is a pure rule-based dispatcher. It cannot interpret natural language, reason about the UI, or handle ambiguity. Every coordinate and parameter you provide must be final, absolute, and immediately executable.

Before filling in the output fields, execute these three steps mentally:

STEP 1 - WIDGET MATCHING:
Scan the Observer's element list (format: ID:element_id | @x,y | ClassName | ID:resource_id | 'label').
Identify the element that best matches the intent of the next required action.
Use its @x,y as the target_x and target_y. The x,y provided by the Observer are PRE-COMPUTED CENTER COORDINATES; use them exactly as given.

STEP 2 - WIDGET PREDICTION (apply if Step 1 fails):
If no element in the list clearly matches, use spatial reasoning and visual context to predict a logical coordinate.

STEP 3 - WIDGET LOCATION ADJUSTMENT:
Verify whether the click point needs to shift to the actual functional element.
Example: If the target is a text label "Search:", the click must land on the input box beside it, not the label itself.

OUTPUT RULES:
- Produce exactly ONE ActionPlan per response.
- target_x and target_y must be integers ready for direct ADB execution.
- If the overall goal is fully achieved, set is_completed=True.
- Do NOT use abstract or high-level instructions. 
- For 'input' actions: set text_payload to the exact text and target_x/target_y to the input field's coordinates.
- For 'scroll' actions: set scroll_direction to 'up', 'down', 'left', or 'right'.
- For 'start_app' actions: set app_package to the full Android package name.
- FINAL RULE: Your response must be ONLY the raw JSON object. Do not include markdown code blocks, conversational text, or any preamble. The response must be immediately parseable as JSON. """


class DeciderAgent:
    def __init__(self, llm):
        self.llm = llm.with_structured_output(ActionPlan)

    def decide(self, state: AgentState) -> dict:
        history_text = "\n".join(state["action_history"]) if state["action_history"] else "None"

        human_prompt = (
            f"Goal: {state['task_goal']}\n\n"
            f"Current Screen Analysis:\n{state['observer_analysis']}\n\n"
            f"Available UI Elements:\n{state['ui_elements_summary']}\n\n"
            f"Action History:\n{history_text}\n\n"
            f"Apply the three-step Widget Location process and produce the next ActionPlan."
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=human_prompt),
        ]

        print("[Decider] Thinking about the next action...")
        plan = self.llm.invoke(messages)

        status = "COMPLETED" if plan.is_completed else (
            f"type={plan.action_type} | target=({plan.target_x},{plan.target_y}) | intent={plan.intent}"
        )
        print(f"[Decider] {status}")

        return {
            "action_plan": plan.model_dump(),
            "is_completed": plan.is_completed,
        }
