import os
import json
import datetime
from core.models.state import AgentState


class RecorderAgent:
    """
    Session finalizer — called ONCE at the end of a scenario run, not mid-cycle.

    With MIRIX, RecorderAgent is no longer a node in the LangGraph loop.
    It is called directly by the runner after the graph exits to persist final
    metrics and retrieve episodic chat history from memory.
    """

    def __init__(self, memory=None, logger=None):
        self.memory = memory
        self.logger = logger

    def _log(self, msg: str, detail: str = ""):
        if self.logger is not None:
            self.logger.log("RECORDER", msg, detail)

    def write_test_report(self, state: AgentState, metrics: dict):
        """Fill result columns in the original scenario.xlsx and copy it to output_dir.

        Columns filled (identified by header name in the TCS ID header row):
          Time Testing, Testing Status, Updated At, Testing By, OK Evid., Issue Status
        Additional columns appended if not already present:
          Actual Result, Steps Taken, Tokens Used, Stagnation Count

        Note: writes back to the original scenario.xlsx in-place (accumulates across runs).
        Not safe for concurrent execution of multiple scenarios.
        """
        import shutil
        import openpyxl

        xlsx_path  = os.path.join(os.getcwd(), "scenario.xlsx")
        tcs_id     = state.get("tcs_id", "")
        output_dir = state.get("output_dir", "")

        if not os.path.exists(xlsx_path) or not tcs_id:
            return

        try:
            wb = openpyxl.load_workbook(xlsx_path)
            ws = wb.active

            # ── Find header row and map column names → column indices ─────────
            header_row_idx = None
            col_map: dict = {}
            for row_idx, row in enumerate(ws.iter_rows(values_only=False), start=1):
                first = row[0].value
                if first and str(first).strip().upper() == "TCS ID":
                    header_row_idx = row_idx
                    for col_idx, cell in enumerate(row, start=1):
                        if cell.value:
                            name = str(cell.value).strip()
                            if name not in col_map:  # first occurrence wins — avoid duplicate header collision
                                col_map[name] = col_idx
                    break

            if header_row_idx is None:
                print("[Recorder] Warning: TCS ID header row not found in scenario.xlsx")
                return

            # ── Ensure all result column headers exist; create if missing ─────
            RESULT_COLS = [
                "Time Testing",
                "Testing Status",
                "Updated At",
                "Testing By",
                "OK Evid.",
                "Issue Status",
                "Actual Result",
                "Steps Taken",
                "Tokens Used",
                "Stagnation Count",
            ]
            next_col = ws.max_column + 1
            col_index: dict = {}
            for col_name in RESULT_COLS:
                if col_name in col_map:
                    col_index[col_name] = col_map[col_name]
                else:
                    ws.cell(header_row_idx, next_col).value = col_name
                    col_index[col_name] = next_col
                    next_col += 1

            # ── Find data row by TCS ID ───────────────────────────────────────
            data_row_idx = None
            for row_idx in range(header_row_idx + 1, ws.max_row + 2):
                cell_val = ws.cell(row_idx, 1).value
                if cell_val and str(cell_val).strip() == tcs_id:
                    data_row_idx = row_idx
                    break

            if data_row_idx is None:
                print(f"[Recorder] Warning: TCS ID '{tcs_id}' not found in scenario.xlsx")
                return

            # ── Build result values ───────────────────────────────────────────
            duration_s   = metrics.get("total_duration_seconds", 0)
            mins, secs   = divmod(int(duration_s), 60)
            duration_str = f"{mins}m {secs}s"

            status         = metrics.get("status", "FAILED")
            # status is "SUCCESS" / "STAGNATED" / "FAILED" as produced by finalize_run_metrics
            testing_status = "OK" if status == "SUCCESS" else "NG"

            judgment = (
                metrics.get("justification", {}).get("reflector_final_judgment", "") or ""
            )

            # "Time Testing" intentionally replaces any placeholder formula with the actual measured duration
            values = {
                "Time Testing":     duration_str,
                "Testing Status":   testing_status,
                "Updated At":       metrics.get("timestamp", ""),
                "Testing By":       f"MAS AI ({metrics.get('mode', 'predefined')})",
                "OK Evid.":         output_dir,
                "Issue Status":     "OK" if testing_status == "OK" else judgment[:200],
                "Actual Result":    judgment[:500],
                "Steps Taken":      metrics.get("total_cycles", 0),
                "Tokens Used":      metrics.get("total_tokens_estimate", 0),
                "Stagnation Count": metrics.get("stagnation_count", 0),
            }

            for col_name, value in values.items():
                idx = col_index.get(col_name)
                if idx:
                    ws.cell(data_row_idx, idx).value = value

            # ── Save back to original + copy to output_dir ───────────────────
            wb.save(xlsx_path)

            if output_dir:
                dest = os.path.join(output_dir, "test_report.xlsx")
                shutil.copy2(xlsx_path, dest)
                print(f"[Recorder] Test report saved to {dest}")

            self._log(
                "Test report written",
                f"tcs_id={tcs_id}  status={testing_status}  dest={output_dir}/test_report.xlsx"
            )

        except Exception as e:
            print(f"[Recorder] Warning: could not write test report: {e}")
            self._log("Test report FAILED", str(e))

    def finalize_run_metrics(self, state: AgentState):
        output_dir = state.get("output_dir", "outputs")
        metrics_path = os.path.join(output_dir, "final_metrics.json")
        session_id = state.get("session_id", "")
        tcs_id = state.get("tcs_id", "Unknown")

        is_completed = state.get("is_completed", False)
        stagnation = state.get("stagnation_count", 0)

        # ── Derive mode from Core Memory (or fall back to autonomous heuristic) ─
        mode = "predefined"
        if self.memory is not None:
            task_goal = self.memory.core.get("task_goal") or ""
            test_type = self.memory.core.get("test_type") or ""
            # Autonomous mode is identified by the presence of task_goal without sub_steps
            sub_steps = self.memory.procedural.get_steps(tcs_id, "workflow")
            mode = "autonomous" if (task_goal and not sub_steps) else "predefined"
        else:
            mode = "autonomous" if state.get("orchestrator_instruction") else "predefined"

        # ── Write episodic history to disk (replaces mid-loop recorder.record()) ─
        if self.memory is not None:
            episodes = self.memory.episodic.all_as_dicts()
            chat_file = os.path.join(output_dir, "chat_logs.txt")
            try:
                lines = []
                for ep in episodes:
                    actor = ep.get("actor", "?").upper()
                    step = ep.get("step", "?")
                    evt = ep.get("event_type", "")
                    summary = ep.get("summary", "")
                    details = ep.get("details", "")
                    lines.append(f"[{actor}] (Step {step}) [{evt}]\n{summary}\n{details}\n{'-'*40}")
                with open(chat_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
            except Exception as e:
                print(f"[Recorder] Warning: could not write chat_logs.txt: {e}")

            # Write interaction script from executor episodes
            exec_episodes = [ep for ep in episodes if ep.get("actor") == "executor"]
            script_content = {
                "tcs_id": tcs_id,
                "total_steps": len(exec_episodes),
                "recording_status": "Success" if is_completed else "In Progress/Failed",
                "actions": exec_episodes,
            }
            script_file = os.path.join(output_dir, "interaction_script.json")
            try:
                with open(script_file, "w", encoding="utf-8") as f:
                    json.dump(script_content, f, indent=2)
            except Exception:
                pass

        # ── Token and cost aggregation from LLM logs ──────────────────────────
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
                                total_tokens += (
                                    log_data.get("total_tokens")
                                    or log_data.get("token_count_estimate")
                                    or 0
                                )
                                total_cost_usd += log_data.get("cost_usd", 0.0)
                        except Exception:
                            continue

        # ── Duration ──────────────────────────────────────────────────────────
        start_time = state.get("start_time", 0)
        end_time = state.get("end_time", 0)
        duration = end_time - start_time if end_time > start_time else 0

        # ── Status ────────────────────────────────────────────────────────────
        status = "SUCCESS" if is_completed else "FAILED"
        if stagnation >= 3:
            status = "STAGNATED"

        # ── Action stats from episodic memory ─────────────────────────────────
        exec_count = 0
        failed_count = 0
        if self.memory is not None:
            exec_eps = [ep for ep in self.memory.episodic.all_as_dicts() if ep.get("actor") == "executor"]
            exec_count = len(exec_eps)
            failed_count = sum(1 for ep in exec_eps if str(ep.get("summary", "")).startswith("[FAIL]"))
        successful_actions = exec_count - failed_count
        tool_precision_rate = round((successful_actions / exec_count) * 100, 1) if exec_count > 0 else 0.0

        recovery_attempts = state.get("recovery_attempts", 0)
        if recovery_attempts > 0:
            successful_recoveries = recovery_attempts - (0 if is_completed else recovery_attempts)
            recovery_rate = round((successful_recoveries / recovery_attempts) * 100, 1)
        else:
            recovery_rate = 100.0 if is_completed else 0.0

        # ── Final reflector judgment from episodic memory ─────────────────────
        reflector_final_judgment = "No judgment"
        if self.memory is not None:
            last_ref = self.memory.episodic.last_by_actor("reflector")
            if last_ref:
                reflector_final_judgment = last_ref.details or last_ref.summary

        # ── Orchestrator reasoning from episodic memory ───────────────────────
        orchestrator_reasoning = ""
        if self.memory is not None:
            last_orch = self.memory.episodic.last_by_actor("orchestrator")
            if last_orch:
                orchestrator_reasoning = last_orch.summary

        figma_enabled = False
        if self.memory is not None:
            figma_enabled = (self.memory.core.get("figma_enabled") or "False") == "True"

        metrics = {
            "tcs_id": tcs_id,
            "mode": mode,
            "status": status,
            "total_cycles": state.get("current_step", 0),
            "physical_actions": exec_count,
            "stagnation_count": stagnation,
            "total_tokens_estimate": total_tokens,
            "total_price_usd": round(total_cost_usd, 8),
            "total_duration_seconds": round(duration, 2),
            "tool_precision_rate": tool_precision_rate,
            "recovery_attempts": recovery_attempts,
            "recovery_rate": recovery_rate,
            "justification": {
                "orchestrator_reasoning": orchestrator_reasoning,
                "reflector_final_judgment": reflector_final_judgment,
            },
            "figma_verified": figma_enabled,
            "last_reflector_passed": state.get("last_reflector_passed", False),
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        # ── Research metrics block ────────────────────────────────────────────
        sub_steps_total = len(
            self.memory.procedural.get_steps(tcs_id, "workflow")
        ) if self.memory is not None else 0
        steps_completed = state.get("steps_completed_count", 0)
        total_ref_calls = state.get("total_reflector_calls", 0)
        ref_passes = state.get("reflector_pass_count", 0)
        first_verify_total = state.get("total_first_verify_calls", 0)
        first_verify_passes = state.get("reflector_first_pass_count", 0)
        lookup_ok       = state.get("widget_lookup_success", 0)
        lookup_fail     = state.get("widget_lookup_fail", 0)
        lookup_fallback = state.get("widget_text_fallback_count", 0)

        def _pct(num, den):
            return round((num / den) * 100, 1) if den > 0 else None

        if mode == "autonomous":
            # Autonomous mode has no fixed step denominator — coverage_rate is not applicable.
            coverage_rate = None
        else:
            coverage_rate = _pct(steps_completed, sub_steps_total)

        metrics["research_metrics"] = {
            "coverage_rate":                     coverage_rate,
            "decision_accuracy_initial_acc1":    _pct(first_verify_passes, first_verify_total),
            "decision_accuracy_final_accf":      _pct(steps_completed, first_verify_total),
            "verification_pass_rate":            _pct(ref_passes, total_ref_calls),
            "widget_localization_effectiveness": _pct(lookup_ok, lookup_ok + lookup_fail),
            "widget_text_fallback_recoveries":   lookup_fallback,
            "time_overhead_seconds":             round(duration, 2),
            "token_consumption":                 total_tokens,
        }

        try:
            with open(metrics_path, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=4)
            print(f"[Recorder] Final metrics saved to {metrics_path}")
            self._log(
                "Final metrics saved",
                f"status={metrics['status']}  cycles={metrics['total_cycles']}\n"
                f"physical_actions={metrics['physical_actions']}\n"
                f"stagnation={metrics['stagnation_count']}\n"
                f"tokens={metrics['total_tokens_estimate']}\n"
                f"duration={metrics['total_duration_seconds']}s\n"
                f"tool_precision={metrics['tool_precision_rate']}%\n"
                f"path={metrics_path}"
            )
        except Exception as e:
            print(f"[Recorder Error] Failed to save final metrics: {e}")
            self._log("FAILED to save final metrics", str(e))

        # ── Test report: fill scenario.xlsx result columns ────────────────────
        self.write_test_report(state, metrics)

        if self.logger is not None:
            self.logger.close()
