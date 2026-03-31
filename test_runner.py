import json
import config
from tools.device_connection import DeviceConnection
from tools.ui_tools import UITools
from core.llm_client import get_llm
from agents.observer_agent import ObserverAgent
from agents.decider_agent import DeciderAgent

def run_simulation():
    # 1. SETUP USER INPUT
    simulated_user_input = {
        "target_app_id": "com.shopee.id",
        "task_goal": "Mencari Profile Saya dan Mengedit Nama Saya"
    }

    # 2. INITIALIZE CONNECTION & TOOLS
    connection_manager = DeviceConnection(config.TARGET_DEVICE)
    d = connection_manager.connect()
    if not d:
        return
    ui_tools = UITools(d, config.OUTPUT_DIR)
    
    # 3. INITIALIZE LANGCHAIN LLM
    llm = get_llm()
    
    # 4. INITIALIZE AGENTS
    observer = ObserverAgent(ui_tools)
    decider = DeciderAgent(llm)
    
    # 5. EXECUTE OBSERVER (PERCEPTION)
    print("[*] Running Observer Agent...")
    state = observer.observe()
    
    # 6. EXECUTE DECIDER (REASONING)
    print("[*] Running Decider Agent...")
    decision = decider.decide(state, simulated_user_input["task_goal"])
    
    # 7. PRINT RESULTS
    print("\n=== SYSTEM REPORT ===")
    print(f"Screenshot: {state['screenshot_path']}")
    print(f"Elements Found: {len(state['elements'])}")
    json_path = state['screenshot_path'].replace(".png", ".json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(state['elements'], f, indent=4)
    print(f"Details Saved: {json_path}")
    if decision:
        print(f"Screen Name: {decision.current_screen_name}")
        print(f"Goal Achieved: {decision.is_goal_achieved}")
        print(f"Reasoning: {decision.reasoning}")
        print(f"Next Action: {decision.next_action}")

if __name__ == "__main__":
    run_simulation()