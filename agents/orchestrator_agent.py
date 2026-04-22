import os
from core.models.state import AgentState

class OrchestratorAgent:
    def __init__(self):
        pass

    def orchestrate(self, state: AgentState) -> dict:
        sub_steps = state.get("sub_steps", [])
        current_idx = state.get("current_sub_step_index", 0)
        global_step = state.get("current_step", 0)
        output_dir = state.get("output_dir", "outputs")
        retry_count = state.get("step_retry_count", 0)
        
        last_passed = state.get("last_reflector_passed", True)
        sender = state.get("sender", "START")

        if sender in ["reflector", "recorder"]:
            if last_passed:
                current_idx += 1
                retry_count = 0
            else:
                retry_count += 1
                print(f"[Orchestrator] Step failure detected. Retry attempt {retry_count}/3 for index {current_idx}")

        if retry_count > 3:
            print("[Orchestrator] Maximum retries exceeded for current step. Aborting scenario.")
            return {
                "is_completed": True,
                "sender": "orchestrator",
                "stagnation_count": 99
            }

        update_data = {
            "current_sub_step_index": current_idx,
            "current_step": global_step + 1,
            "step_retry_count": retry_count,
            "sender": "orchestrator"
        }

        if current_idx < len(sub_steps):
            step_dir = os.path.join(output_dir, f"step_{current_idx + 1}")
            if retry_count > 0:
                step_dir = os.path.join(output_dir, f"step_{current_idx + 1}_retry_{retry_count}")
            
            if not os.path.exists(step_dir):
                os.makedirs(step_dir)
            
            update_data["step_dir"] = step_dir
            update_data["is_completed"] = False
            print(f"[Orchestrator] Dispatching: {sub_steps[current_idx]}")
        else:
            update_data["is_completed"] = True
            print("[Orchestrator] All steps verified. Scenario success.")
            
        return update_data
