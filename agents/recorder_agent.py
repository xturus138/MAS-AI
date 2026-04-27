import os
import json
import datetime
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
        """
        output_dir = state.get("output_dir", "outputs")
        metrics_path = os.path.join(output_dir, "final_metrics.json")
        session_id = state.get("session_id", "")
        
        history = state.get("action_history", [])
        is_completed = state.get("is_completed", False)
        stagnation = state.get("stagnation_count", 0)
        
        # 1. Sum up tokens and cost from logs
        total_tokens = 0
        total_cost_usd = 0.0
        if session_id:
            log_dir = os.path.join("outputs", "llm_logs", session_id)
            if os.path.exists(log_dir):
                for filename in os.listdir(log_dir):
                    if filename.endswith(".json"):
                        try:
                            with open(os.path.join(log_dir, filename), "r", encoding="utf-8") as f:
                                log_data = json.load(f)
                                # Support both old field name and new
                                total_tokens += (
                                    log_data.get("total_tokens")
                                    or log_data.get("token_count_estimate")
                                    or 0
                                )
                                total_cost_usd += log_data.get("cost_usd", 0.0)
                        except Exception:
                            continue

        # 2. Calculate Duration
        start_time = state.get("start_time", 0)
        end_time = state.get("end_time", 0)
        duration = end_time - start_time if end_time > start_time else 0

        # 3. Build Metrics
        status = "SUCCESS" if is_completed else "FAILED"
        if stagnation >= 3:
            status = "STAGNATED"

        # Calculate Tool Precision Rate
        total_actions = len(history)
        failed_actions = sum(1 for h in history if str(h.get("r", "")).startswith("ERROR"))
        successful_actions = total_actions - failed_actions
        tool_precision_rate = round((successful_actions / total_actions) * 100, 1) if total_actions > 0 else 0.0

        # Calculate Recovery Rate
        recovery_attempts = state.get("recovery_attempts", 0)
        if recovery_attempts > 0:
            # If the run eventually succeeded despite having failures, it recovered
            successful_recoveries = recovery_attempts - (0 if is_completed else recovery_attempts)
            recovery_rate = round((successful_recoveries / recovery_attempts) * 100, 1)
        else:
            recovery_rate = 100.0 if is_completed else 0.0

        metrics = {
            "tcs_id": state.get("tcs_id", "Unknown"),
            "mode": "autonomous" if state.get("task_goal") else "predefined",
            "status": status,
            "total_cycles": state.get("current_step", 0),
            "physical_actions": total_actions,
            "stagnation_count": stagnation,
            "total_tokens_estimate": total_tokens,
            "total_price_usd": round(total_cost_usd, 8),
            "total_duration_seconds": round(duration, 2),
            "tool_precision_rate": tool_precision_rate,
            "recovery_attempts": recovery_attempts,
            "recovery_rate": recovery_rate,
            "justification": {
                "orchestrator_reasoning": state.get("orchestrator_reasoning", ""),
                "reflector_final_judgment": state.get("reflector_reasoning", "No judgment"),
            },
            "figma_verified": state.get("figma_enabled", False),
            "last_reflector_passed": state.get("last_reflector_passed", False),
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        try:
            with open(metrics_path, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=4)
            print(f"[Recorder] Final metrics saved to {metrics_path}")
        except Exception as e:
            print(f"[Recorder Error] Failed to save final metrics: {e}")
