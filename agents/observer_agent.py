import base64
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from core.state import AgentState

class ObserverOutput(BaseModel):
    screen_description: str = Field(description="Brief description of the current screen")
    key_elements_found: str = Field(description="Key elements visible on the screen")

class ObserverAgent:
    def __init__(self, llm, tools):
        self.llm = llm.with_structured_output(ObserverOutput)
        # tools is a list containing [take_screenshot, get_ui_hierarchy]
        self.take_screenshot = tools[0]
        self.get_ui_hierarchy = tools[1]

    def _encode_image(self, image_path):
        with open(image_path, "rb") as img:
            return base64.b64encode(img.read()).decode('utf-8')

    def analyze(self, state: AgentState) -> dict:
        print(f"\n--- CYCLE {state['current_step'] + 1} | [Observer] Analyzing screen... ---")
        
        # Use separate tools
        img_path = self.take_screenshot.invoke({})
        xml_summary = self.get_ui_hierarchy.invoke({})

        img_b64 = self._encode_image(img_path)
        prompt = (
            f"User Goal: {state['task_goal']}\n"
            f"XML Analysis: {xml_summary}\n\n"
            f"Task: Identify key elements to achieve the goal.\n"
            f"MANDATORY: Mention @x,y coordinates for every element you find in 'key_elements_found'."
        )

        message = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
        ])

        result = self.llm.invoke([message])
        analysis = f"Screen: {result.screen_description}. Found: {result.key_elements_found}"
        print(f"[Observer] {analysis}")

        return {
            "screenshot_path": img_path,
            "ui_elements_summary": xml_summary,
            "observer_analysis": analysis,
            "current_step": state["current_step"] + 1,
        }