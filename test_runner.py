# test_runner.py
import config
from tools.device_connection import DeviceConnection
from tools.ui_tools import UITools
from core.llm_client import OpenRouterClient
from agents.observer_agent import ObserverAgent

def run_simulation():
    print("==========================================")
    print("MENGJALANKAN SIMULASI INPUT USER")
    print("==========================================")

    simulated_user_input = {
        "target_app_id": "com.whatsapp",
        "task_goal": "Mencari kontak bernama 'Rafa' dan mengirim pesan 'Halo'",
        "expected_action": "Buka aplikasi dan cari icon pencarian"
    }

    print(f"[*] Skenario Target App : {simulated_user_input['target_app_id']}")
    print(f"[*] Skenario Goal User  : {simulated_user_input['task_goal']}\n")

    # 2. Inisialisasi Koneksi dan Tools
    connection_manager = DeviceConnection(config.TARGET_DEVICE)
    d = connection_manager.connect()
    
    if not d:
        print("[!] Keluar dari simulasi karena gagal terhubung ke perangkat.")
        return

    ui_tools = UITools(d, config.OUTPUT_DIR)
    llm_client = OpenRouterClient(config.OPENROUTER_API_KEY, config.VISION_MODEL)
    
    # 3. Masukkan Tools dan GOAL USER ke dalam Agent
    agent = ObserverAgent(ui_tools, llm_client, task_goal=simulated_user_input["task_goal"])
    
    # 4. Jalankan Agent
    report = agent.observe()
    
    # 5. Tampilkan Hasil Simulasi
    print("\n==========================================")
    print("HASIL OBSERVASI AI BERDASARKAN INPUT USER")
    print("==========================================")
    if report["status"] == "success":
        print(f"Screenshot Path    : {report['screenshot_path']}")
        print(f"Total Elemen Aktif : {report['total_elements']}")
        print("-" * 42)
        analysis = report['ai_analysis']
        if analysis:
            print("ANALISIS TERSTRUKTUR DARI AI:")
            print(f"  > Nama Layar    : {analysis.current_screen_name}")
            print(f"  > Target Selesai: {analysis.is_goal_achieved}")
            print(f"  > Analisis      : {analysis.reasoning}")
            print(f"  > Saran Next    : {analysis.next_action}")
        else:
            print("[!] AI gagal memberikan analisis terstruktur.")
        print("-" * 42)
    else:
        print(f"Status Error: {report.get('message', 'Terjadi kesalahan')}")
    print("==========================================")

if __name__ == "__main__":
    run_simulation()