import os
import json
from core.models.state import AgentState

class RecorderAgent:
    def __init__(self):
        pass

    def record(self, state: AgentState) -> dict:
        output_dir = state.get("output_dir", "outputs")
        step_dir = state.get("step_dir", "")
        
        # Determine where to save logs (to the step dir if available, else root output dir)
        save_dir = step_dir if step_dir and os.path.exists(step_dir) else output_dir
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)

        script_file_path = os.path.join(save_dir, "interaction_script.json")
        chat_file_path = os.path.join(save_dir, "chat_logs.txt")

        history_action = state.get("action_history", [])
        chat_logs = state.get("chat_logs", [])

        # 1. Serialize Action History
        script_content = {
            "scenario": state.get("scenario_desc", ""),
            "total_steps": len(history_action),
            "recording_status": "Success" if state.get("is_completed") else "In Progress/Failed",
            "actions": history_action
        }
        
        try:
            with open(script_file_path, "w", encoding="utf-8") as f:
                json.dump(script_content, f, indent=2)
            print(f"[Recorder] Serialized action history to {script_file_path}")
        except Exception as e:
            print(f"[Recorder Error] Failed to write script: {e}")

        # 2. Serialize Chat Logs
        if chat_logs:
            try:
                chat_str = "\n".join([f"[{log['agent'].upper()}] (Step {log.get('step', '?')})\n{log['content']}\n{'-'*40}" for log in chat_logs])
                with open(chat_file_path, "w", encoding="utf-8") as f:
                    f.write(chat_str)
                print(f"[Recorder] Exported chat logs to {chat_file_path}")
            except Exception as e:
                print(f"[Recorder Error] Failed to write chat logs: {e}")

        return {
            "sender": "recorder"
        }
