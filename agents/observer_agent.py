import base64
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from core.state import OrchestratorState

# STEP 1 DEFINISI OUTPUT DAN LOGIKA OBSERVER AGENT DENGAN TOOLS MANDIRI //
class ObserverOutput(BaseModel):
    screen_description: str = Field(description="Deskripsi singkat layar saat ini")
    key_elements_found: str = Field(description="Elemen penting apa saja yang terlihat")

class ObserverAgent:
    def __init__(self, llm, tools):
        self.llm = llm.with_structured_output(ObserverOutput)
        self.tools = tools

    def _encode_image(self, image_path):
        with open(image_path, "rb") as img:
            return base64.b64encode(img.read()).decode('utf-8')

    def analyze(self, state: OrchestratorState) -> OrchestratorState:
        img_path, xml_summary = self.tools.capture_state()
        state.screenshot_path = img_path
        state.ui_elements_summary = xml_summary

        img_b64 = self._encode_image(state.screenshot_path)
        prompt = (
            f"Tujuan User: {state.task_goal}\n"
            f"Struktur XML:\n{state.ui_elements_summary}\n\n"
            f"Analisis layar ini dan sebutkan elemen penting yang terlihat."
        )
        
        message = HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
        ])
        
        result = self.llm.invoke([message])
        state.observer_analysis = f"Layar: {result.screen_description}. Terlihat: {result.key_elements_found}"
        return state