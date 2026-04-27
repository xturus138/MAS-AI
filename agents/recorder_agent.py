import os
import json
from core.models.state import AgentState

class RecorderAgent:
    def __init__(self):
        pass

    def record(self, state: AgentState) -> dict:
        # (Existing record code remains the same)
        output_dir = state.get("output_dir", "outputs")
        step_dir = state.get("step_dir", "")
        
        save_dir = step_dir if step_dir and os.path.exists(step_dir) else output_dir
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)

        script_file_path = os.path.join(save_dir, "interaction_script.json")
        chat_file_path = os.path.join(save_dir, "chat_logs.txt")

        history_action = state.get("action_history", [])
        chat_logs = state.get("chat_logs", [])

        script_content = {
            "scenario": state.get("scenario_desc", ""),
            "total_steps": len(history_action),
            "recording_status": "Success" if state.get("is_completed") else "In Progress/Failed",
            "actions": history_action
        }
        
        try:
            with open(script_file_path, "w", encoding="utf-8") as f:
                json.dump(script_content, f, indent=2)
        except Exception:
            pass

        if chat_logs:
            try:
                chat_str = "\n".join([f"[{log['agent'].upper()}] (Step {log.get('step', '?')})\n{log['content']}\n{'-'*40}" for log in chat_logs])
                with open(chat_file_path, "w", encoding="utf-8") as f:
                    f.write(chat_str)
            except Exception:
                pass

        return {"sender": "recorder"}

    def finalize_run_metrics(self, state: AgentState):
        """
        Generates a final metrics summary JSON for the entire test run.
        This is used for the Skripsi (Thesis) data collection.
        """
        output_dir = state.get("output_dir", "outputs")
        metrics_path = os.path.join(output_dir, "final_metrics.json")
        
        history = state.get("action_history", [])
        is_completed = state.get("is_completed", False)
        
        metrics = {
            "tcs_id": state.get("tcs_id", "Unknown"),
            "mode": "autonomous" if "task_goal" in state else "predefined",
            "status": "SUCCESS" if is_completed else "FAILED",
            "total_steps": len(history),
            "stagnation_count": state.get("stagnation_count", 0),
            "reflector_final_judgment": state.get("reflector_reasoning", "No judgment"),
            "figma_verified": state.get("figma_enabled", False),
            "last_reflector_passed": state.get("last_reflector_passed", False),
            "timestamp": state.get("timestamp", "")
        }

        try:
            with open(metrics_path, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=4)
            print(f"[Recorder] Final metrics saved to {metrics_path}")
        except Exception as e:
            print(f"[Recorder Error] Failed to save final metrics: {e}")
