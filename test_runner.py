import config
from core.llm_client import get_shared_llm
from core.state import OrchestratorState
from core.device_connection import DeviceConnection
from tools.observer_tools import ObserverTools
from tools.executor_tools import ExecutorTools
from agents.observer_agent import ObserverAgent
from agents.orchestrator_agent import OrchestratorAgent
from agents.executor_agent import ExecutorAgent

# STEP 1 ALUR KERJA ORCHESTRATOR DENGAN PEMISAHAN TOOLS PER AGENT //
def run_workflow():
    print("[*] Memulai Multi-Agent Orchestrator System...")
    
    device_session = DeviceConnection(config.TARGET_DEVICE).connect()
    shared_llm = get_shared_llm()
    
    obs_tools = ObserverTools(device_session, config.OUTPUT_DIR)
    exe_tools = ExecutorTools(device_session)
    
    observer = ObserverAgent(shared_llm, obs_tools)
    orchestrator = OrchestratorAgent(shared_llm)
    executor = ExecutorAgent(shared_llm, exe_tools.get_tools())
    
    state = OrchestratorState(
        task_goal="Masuk ke menu Keranjang Belanja (Cart)"
    )
    
    max_steps = 5
    while state.current_step < max_steps and not state.is_completed:
        state.current_step += 1
        print(f"\n--- SIKLUS {state.current_step} ---")
        
        state = observer.analyze(state)
        print(f"[Observer] : {state.observer_analysis}")
        
        state = orchestrator.decide(state)
        print(f"[Orchestrator] Selesai?: {state.is_completed}")
        
        if state.is_completed:
            break
            
        print(f"[Orchestrator] Perintah : {state.orchestrator_instruction}")
        
        state = executor.execute(state)
        print(f"[Executor] Hasil        : {state.execution_result}")

    print("\n=== WORKFLOW SELESAI ===")
    print(f"Status Akhir: {'Sukses' if state.is_completed else 'Terhenti (Max Steps)'}")
    print("Riwayat Tindakan:")
    for history in state.action_history:
        print(f" - {history}")

if __name__ == "__main__":
    run_workflow()