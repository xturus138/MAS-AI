"""Output writer: human-readable summaries, archiving old runs."""

import os
import json
import re
import shutil
from typing import Any


def archive_old_runs(mode_root: str) -> None:
    """Move old run directories to `past/` so only the latest run stays in root.

    Supports two layouts:
    - New: ``outputs/runs/<mode>/<date>/run_N/`` — archives ``run_N`` dirs
      inside each date bucket.
    - Legacy: ``outputs/<mode>/<TCS_ID>_<YYYYMMDD_HHMMSS>/`` — archives
      flat scenario dirs.

    Skips: ``_memory/``, ``past/``, ``*.json``, ``*.xlsx``, ``*.md``.
    """
    if not os.path.isdir(mode_root):
        return

    past_dir = os.path.join(mode_root, "past")
    run_pattern = re.compile(r"^run_\d+$")
    legacy_pattern = re.compile(r"^[A-Z]+-\d{3}_\d{8}_\d{6}$")

    for entry in os.listdir(mode_root):
        src = os.path.join(mode_root, entry)
        if not os.path.isdir(src):
            continue
        if entry.startswith("_") or entry == "past":
            continue

        if run_pattern.match(entry):
            os.makedirs(past_dir, exist_ok=True)
            dest = os.path.join(past_dir, entry)
            if os.path.exists(dest):
                dest = os.path.join(past_dir, f"{entry}_archived")
            shutil.move(src, dest)
            print(f"[OutputWriter] Archived: {entry} -> past/")
            continue

        if legacy_pattern.match(entry):
            os.makedirs(past_dir, exist_ok=True)
            dest = os.path.join(past_dir, entry)
            if os.path.exists(dest):
                dest = os.path.join(past_dir, f"{entry}_archived")
            shutil.move(src, dest)
            print(f"[OutputWriter] Archived: {entry} -> past/")
            continue

        if re.match(r"^\d{4}-\d{2}-\d{2}$", entry):
            for sub_entry in os.listdir(src):
                sub_src = os.path.join(src, sub_entry)
                if not os.path.isdir(sub_src):
                    continue
                if run_pattern.match(sub_entry):
                    os.makedirs(past_dir, exist_ok=True)
                    dest = os.path.join(past_dir, f"{entry}__{sub_entry}")
                    if os.path.exists(dest):
                        dest = os.path.join(past_dir, f"{entry}__{sub_entry}_archived")
                    shutil.move(sub_src, dest)
                    print(f"[OutputWriter] Archived: {entry}/{sub_entry} -> past/")


def write_run_overview(
    output_dir: str,
    tcs_id: str,
    status: str,
    mode: str,
    steps_completed: int,
    total_steps: int,
    duration_seconds: float,
    physical_actions: int,
    figma_enabled: bool,
    tokens: int,
    cost_usd: float,
    reflector_judgment: str,
    steps_data: list[dict[str, Any]] | None = None,
) -> str:
    """Write a human-friendly markdown overview of a single scenario run.

    Returns the path to the written file.
    """
    status_icon = "✅" if status == "SUCCESS" else "❌" if status == "FAILED" else "⏸️"

    def _fmt_dur(s: float) -> str:
        m, sec = divmod(int(s), 60)
        return f"{m}m {sec}s" if m else f"{sec}s"

    lines = [
        f"# Test Run: {tcs_id}",
        "",
        f"**Generated:** {_now()}",
        "",
        "## Overview",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| **Status** | {status_icon} {status} |",
        f"| **Mode** | {mode} |",
        f"| **Steps** | {steps_completed}/{total_steps} completed |",
        f"| **Duration** | {_fmt_dur(duration_seconds)} |",
        f"| **Physical Actions** | {physical_actions} |",
        f"| **Figma** | {'Enabled' if figma_enabled else 'Disabled'} |",
        f"| **Tokens** | {tokens:,} |",
        f"| **Estimated Cost** | ~${cost_usd:.4f} |",
        "",
    ]

    if steps_data:
        lines.append("## Step Summary")
        lines.append("")
        lines.append("| Step | Instruction | Action | Verdict |")
        lines.append("|------|-------------|--------|---------|")
        for sd in steps_data:
            instr = sd.get("instruction", "")[:60]
            action = sd.get("action_type", "")
            verdict = sd.get("verdict", "")
            lines.append(f"| {sd.get('step_number', '?')} | {instr} | {action} | {verdict} |")
        lines.append("")

    lines.append("## Final Verdict")
    lines.append("")
    lines.append(reflector_judgment or "No judgment recorded.")
    lines.append("")

    content = "\n".join(lines)
    overview_path = os.path.join(output_dir, "run_overview.md")
    try:
        with open(overview_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OutputWriter] Overview written: {overview_path}")
    except Exception as e:
        print(f"[OutputWriter] Failed to write overview: {e}")

    return overview_path


def write_step_summary(
    step_dir: str,
    step_number: int,
    instruction: str,
    action_type: str,
    target_widget_id: int,
    verdict: str,
    has_screenshot: bool,
    duration_seconds: float | None = None,
) -> str:
    """Write a concise JSON step summary next to the existing reflector report.

    Returns the path to the written file.
    """
    summary = {
        "step_number": step_number,
        "step_instruction": instruction,
        "action_type": action_type,
        "target_widget_id": target_widget_id,
        "verdict": verdict,
        "has_screenshot": has_screenshot,
        "duration_seconds": duration_seconds,
    }

    path = os.path.join(step_dir, "step_summary.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[OutputWriter] Failed to write step_summary: {e}")
    return path


def write_run_summary(output_dir: str, tcs_id: str, status: str, steps_completed: int, duration_seconds: float) -> str:
    """Write a lightweight per-run summary JSON inside the run folder."""
    summary = {
        "tcs_id": tcs_id,
        "status": status,
        "steps_completed": steps_completed,
        "duration_seconds": round(duration_seconds, 2),
    }
    path = os.path.join(output_dir, "run_summary.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
    except Exception as e:
        print(f"[OutputWriter] Failed to write run_summary: {e}")
    return path


def write_run_index(mode_root: str, metrics_list: list[dict]) -> str:
    """Write a flat run index JSON at the mode root for quick scanning."""
    index = []
    for m in metrics_list:
        index.append({
            "session_id": m.get("session_id", ""),
            "tcs_id": m.get("tcs_id", ""),
            "status": m.get("status", ""),
            "steps_completed": m.get("steps_completed", 0),
            "duration_seconds": m.get("duration_seconds", 0),
            "timestamp": m.get("timestamp", ""),
        })
    path = os.path.join(mode_root, "run_index.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        print(f"[OutputWriter] Run index written: {path}")
    except Exception as e:
        print(f"[OutputWriter] Failed to write run index: {e}")
    return path


def _now() -> str:
    """Return current timestamp string."""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")