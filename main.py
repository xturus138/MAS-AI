import config
from core.llm_client import get_shared_llm
from core.state import AgentState
from core.device_connection import DeviceConnection
from tools.observer_tools import ObserverTools
from tools.executor_tools import ExecutorTools
from agents.observer_agent import ObserverAgent
from agents.decider_agent import DeciderAgent
from agents.executor_agent import ExecutorAgent

# STEP 1 ALUR KERJA SISTEM DENGAN PEMISAHAN TOOLS PER AGENT //
def run_workflow():
    print("[*] Memulai Multi-Agent System...")
    
    device_session = DeviceConnection(config.TARGET_DEVICE).connect()
    shared_llm = get_shared_llm()
    
    obs_tools = ObserverTools(device_session, config.OUTPUT_DIR)
    exe_tools = ExecutorTools(device_session)
    
    observer = ObserverAgent(shared_llm, obs_tools)
    decider = DeciderAgent(shared_llm)
    executor = ExecutorAgent(shared_llm, exe_tools.get_tools())
    
    state = AgentState(
        task_goal="Buka keranjang dan  hapus Nitendo Switch dari keranjang"
    )
    
    max_steps = 5
    while state.current_step < max_steps and not state.is_completed:
        state.current_step += 1
        print(f"\n--- SIKLUS {state.current_step} ---")
        
        state = observer.analyze(state)
        print(f"[Observer] : {state.observer_analysis}")
        
        state = decider.decide(state)
        print(f"[Decider] Selesai?: {state.is_completed}")
        
        if state.is_completed:
            break
            
        print(f"[Decider] Perintah : {state.decider_instruction}")
        
        state = executor.execute(state)
        print(f"[Executor] Hasil        : {state.execution_result}")

    print("\n=== WORKFLOW SELESAI ===")
    print(f"Status Akhir: {'Sukses' if state.is_completed else 'Terhenti (Max Steps)'}")
    print("Riwayat Tindakan:")
    for history in state.action_history:
        print(f" - {history}")

if __name__ == "__main__":
    run_workflow()