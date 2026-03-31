# agents/observer_agent.py
from pydantic import BaseModel, Field

# --------------------------------------------------------------
# 1. Definisikan Format Output yang Diharapkan dari AI (Pydantic)
# --------------------------------------------------------------
class ScreenAnalysis(BaseModel):
    current_screen_name: str = Field(description="Nama dari layar saat ini (misal: 'Beranda WhatsApp', 'Chat Terkunci')")
    is_goal_achieved: bool = Field(description="True jika tujuan user saat ini sudah terpenuhi di layar ini, False jika belum")
    reasoning: str = Field(description="Alasan singkat mengapa tujuan tercapai atau belum tercapai")
    next_action: str = Field(description="Saran satu langkah logis selanjutnya yang harus dilakukan user untuk mencapai tujuan")

class ObserverAgent:
    def __init__(self, device_tools, llm_client, task_goal="Hanya amati layar ini"):
        self.tools = device_tools
        self.llm = llm_client
        self.task_goal = task_goal

    def observe(self):
        print("\n--- MEMULAI SIKLUS OBSERVASI ---")
        print(f"[*] Instruksi User saat ini: '{self.task_goal}'")
        
        screenshot_path = self.tools.capture_screenshot()
        ui_elements = self.tools.get_ui_elements()
        
        if not screenshot_path or not ui_elements:
            return {"status": "failed", "message": "Gagal mengambil data dari perangkat."}

        interactive_elements = []
        for el in ui_elements:
            if el['clickable'] or 'EditText' in el['class'] or 'Button' in el['class']:
                label = el['text'] or el['description'] or "(no label)"
                interactive_elements.append({
                    "class": el['class'],
                    "label": label,
                    "bounds": el['bounds']
                })

        # Kita rangkum sedikit elemen UI-nya untuk membantu AI berpikir
        # Ambil 15 elemen pertama saja agar prompt tidak terlalu penuh
        ui_summary = "\n".join([f"- {el['class']}: '{el['label']}'" for el in interactive_elements[:15]])

        prompt_text = (
            f"You are an AI analyzing a mobile screen to help a user.\n"
            f"User's Goal: '{self.task_goal}'\n\n"
            f"Here are some interactive elements on screen:\n{ui_summary}\n\n"
            f"Analyze the image and the elements, then provide your assessment."
        )
        
        print("[*] Menghubungi AI untuk inferensi terstruktur...")
        
        # --------------------------------------------------------------
        # 2. Panggil LLM dengan Pydantic Model
        # --------------------------------------------------------------
        structured_analysis = self.llm.analyze_screen_structured(
            screenshot_path, 
            prompt_text, 
            ScreenAnalysis
        )

        return {
            "status": "success",
            "screenshot_path": screenshot_path,
            "total_elements": len(interactive_elements),
            "ai_analysis": structured_analysis, # Hasilnya sekarang berbentuk Object!
            "elements": interactive_elements
        }