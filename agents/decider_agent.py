import base64
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage

# 1. DEFINE LANGCHAIN STRUCTURED OUTPUT
class ActionDecision(BaseModel):
    current_screen_name: str = Field(
        description=(
            "A short snake_case identifier for the current screen, "
            "e.g. 'home_feed', 'product_detail', 'profile_overview', 'checkout'. "
            "Do NOT use spaces or capital letters."
        )
    )
    is_goal_achieved: bool = Field(
        description=(
            "Set to True ONLY if the user's goal has been fully and completely accomplished "
            "based on what is currently visible on screen. Set to False if any step remains."
        )
    )
    reasoning: str = Field(
        description=(
            "A concise step-by-step explanation of: (1) what the current screen shows, "
            "(2) how it relates to the user's goal, and (3) why the chosen next_action is appropriate. "
            "Do NOT repeat the goal verbatim. Keep it under 3 sentences."
        )
    )
    next_action: str = Field(
        description=(
            "A single, concrete UI action to perform next. Use the format: "
            "'tap <element_label>', 'type \"<text>\" into <element_label>', or 'scroll <direction>'. "
            "Only describe ONE action. If the goal is achieved, output 'none'."
        )
    )

class DeciderAgent:
    def __init__(self, llm):
        # 2. INITIALIZE DECIDER WITH LANGCHAIN LLM
        self.llm = llm

    def _encode_image(self, image_path):
        # 3. ENCODE IMAGE TO BASE64
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def decide(self, observation_state: dict, task_goal: str):
        # 4. PREPARE CONTEXT
        ui_summary = "\n".join([f"- {el['class']}: '{el['label']}'" for el in observation_state["elements"][:15]])
        prompt = (
            f"User Goal: '{task_goal}'\n\n"
            f"UI Elements:\n{ui_summary}\n\n"
            f"Analyze the UI and determine the next action."
        )

        # 5. PREPARE LANGCHAIN MESSAGE WITH IMAGE
        base64_image = self._encode_image(observation_state["screenshot_path"])
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
            ]
        )

        # 6. INVOKE LLM WITH STRUCTURED OUTPUT
        structured_llm = self.llm.with_structured_output(ActionDecision)
        try:
            decision = structured_llm.invoke([message])
            return decision
        except Exception as e:
            print(f"Decider Error: {e}")
            return None