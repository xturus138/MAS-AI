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
        self.take_screenshot = tools[0]
        self.get_ui_hierarchy = tools[1]

    def _encode_image(self, image_path):
        with open(image_path, "rb") as img:
            return base64.b64encode(img.read()).decode('utf-8')

    def analyze(self, state: AgentState) -> dict:
        print(f"\n--- CYCLE {state['current_step'] + 1} | [Observer] Analyzing screen... ---")
        
        
        print("[Observer] Taking screenshot...")
        img_path = self.take_screenshot.invoke({})
        
        print("[Observer] Fetching UI hierarchy...")
        xml_summary = self.get_ui_hierarchy.invoke({})

        print(f"[Observer] Sending screenshot to Local LLM (Cycle {state['current_step'] + 1})...")

        img_b64 = self._encode_image(img_path)
        prompt = (
            f"User Goal: {state['task_goal']}\n"
            f"XML Analysis: {xml_summary}\n\n"
            f"Task: Identify key elements to achieve the goal.\n"
            f"MANDATORY: Mention @x,y coordinates for every element you find in 'key_elements_found'.\n\n"
            f"OUTPUT INSTRUCTION: Output ONLY a valid JSON object matching the schema. "
            f"Do NOT include any conversational text, introductory remarks, or 'Here is the analysis'. "
            f"The response must begin with '{{' and end with '}}'."
        )

        message = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
        ])

        result = self.llm.invoke([message])
        print(f"[Observer] Analysis: {result.screen_description}")
        analysis = f"Screen: {result.screen_description}. Found: {result.key_elements_found}"

        return {
            "screenshot_path": img_path,
            "ui_elements_summary": xml_summary,
            "observer_analysis": analysis,
            "current_step": state["current_step"] + 1,
        }