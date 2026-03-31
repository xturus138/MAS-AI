from pydantic import BaseModel, Field
from typing import List, Optional

# STEP 1 DEFINISI STRUKTUR STATE GLOBAL //
class OrchestratorState(BaseModel):
    task_goal: str = Field(description="Tujuan akhir pengguna")
    current_step: int = Field(default=0, description="Langkah ke berapa saat ini")
    screenshot_path: str = Field(default="", description="Path gambar layar terbaru")
    ui_elements_summary: str = Field(default="", description="Ringkasan elemen UI (XML)")
    observer_analysis: str = Field(default="", description="Hasil pemahaman Observer")
    orchestrator_instruction: str = Field(default="", description="Perintah untuk Executor")
    execution_result: str = Field(default="", description="Hasil dari tindakan Executor")
    is_completed: bool = Field(default=False, description="Apakah tujuan sudah tercapai")
    action_history: List[str] = Field(default_factory=list, description="Sejarah tindakan")