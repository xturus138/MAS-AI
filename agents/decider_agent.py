# agents/decider_agent.py
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from core.state import AgentState

# STEP 1 DEFINISI OUTPUT DAN LOGIKA DECIDER AGENT //
class DeciderDecision(BaseModel):
    is_completed: bool = Field(description="True jika tujuan user telah tercapai")
    next_instruction: str = Field(description="Instruksi spesifik untuk Executor jika belum selesai. Misal: 'Klik tombol profil di koordinat 100, 200'")

class DeciderAgent:
    def __init__(self, llm):
        self.llm = llm.with_structured_output(DeciderDecision)

    def decide(self, state: AgentState) -> AgentState:
        prompt = (
            f"Tujuan Akhir: {state.task_goal}\n"
            f"Informasi Layar: {state.observer_analysis}\n"
            f"Riwayat Tindakan: {state.action_history}\n\n"
            f"TUGAS: Berikan instruksi ke Executor.\n"
            f"ATURAN: Gunakan koordinat @x,y yang disediakan oleh Observer. "
            f"JANGAN menebak koordinat jika tidak ada dalam analisis layar."
        )
        
        message = HumanMessage(content=prompt)
        decision = self.llm.invoke([message])
        
        state.is_completed = decision.is_completed
        state.decider_instruction = decision.next_instruction
        return state
