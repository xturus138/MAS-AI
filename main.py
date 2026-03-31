# main.py
import config
from tools.device_connection import DeviceConnection
from tools.ui_tools import UITools
from core.llm_client import OpenRouterClient
from agents.observer_agent import ObserverAgent

def main():
    print("[*] Inisialisasi Sistem Multi-Agent...")
    
    # 1. Buat Koneksi ke Perangkat SATU KALI SAJA
    connection_manager = DeviceConnection(config.TARGET_DEVICE)
    d = connection_manager.connect() # 'd' adalah objek koneksi uiautomator2 aktif
    
    if not d:
        print("[!] Keluar dari program karena gagal terhubung ke perangkat.")
        return

    # 2. Inisialisasi Tools dengan memberikan koneksi 'd' yang sama
    ui_tools = UITools(d, config.OUTPUT_DIR)
    llm_client = OpenRouterClient(config.OPENROUTER_API_KEY, config.VISION_MODEL)
    
    # 3. Masukkan Tools ke dalam Observer Agent
    observer = ObserverAgent(ui_tools, llm_client)
    
    # 4. Jalankan Agent
    report = observer.observe()
    
    # 5. Tampilkan Hasil (Sama seperti sebelumnya)
    print("\n==========================================")
    print("LAPORAN AKHIR OBSERVER AGENT")
    print("==========================================")
    if report["status"] == "success":
        print(f"Screenshot         : {report['screenshot_path']}")
        print(f"Total Elemen UI    : {report['total_elements']}")
        print("-" * 42)
        print(f"DESKRIPSI LAYAR:")
        print(f"  {report['screen_description']}")
    else:
        print(f"Status: {report['status']}")
        print(f"Pesan : {report.get('message', 'Terjadi kesalahan')}")
    print("==========================================")

if __name__ == "__main__":
    main()