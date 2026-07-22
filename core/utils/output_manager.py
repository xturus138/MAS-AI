"""Centralized output path creation for MAS AI runs."""

from __future__ import annotations

import datetime
import json
import os
import re
from dataclasses import asdict, dataclass

from shared import config


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_part(value: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("-", str(value).strip()).strip("-_.")
    return cleaned or "unknown"


def compute_date_str() -> str:
    """Return today's date as YYYY-MM-DD string."""
    return datetime.datetime.now().strftime("%Y-%m-%d")


def compute_run_number(mode: str, date_str: str) -> int:
    """Scan outputs/runs/{mode}/{date_str}/ for existing run_N dirs.
    Return max N + 1, or 1 if none found."""
    run_root = os.path.join(config.OUTPUT_DIR, "runs", mode, date_str)
    if not os.path.isdir(run_root):
        return 1
    max_n = 0
    for entry in os.listdir(run_root):
        if entry.startswith("run_"):
            try:
                n = int(entry.split("_", 1)[1])
                if n > max_n:
                    max_n = n
            except (ValueError, IndexError):
                continue
    return max_n + 1


def compute_run_root(mode: str) -> tuple[str, str, int]:
    """Return (run_root_abs_path, date_str, run_number).
    run_root = outputs/runs/{mode}/{date}/run_{N}"""
    date_str = compute_date_str()
    run_number = compute_run_number(mode, date_str)
    run_root = os.path.join(config.OUTPUT_DIR, "runs", mode, date_str, f"run_{run_number}")
    return run_root, date_str, run_number


def scenario_dir_name(scenario_index: int) -> str:
    """Return e.g. 'scenario_01' for index 0."""
    return f"scenario_{int(scenario_index) + 1:02d}"


@dataclass(frozen=True)
class RunOutputPaths:
    root: str
    mode: str
    date: str
    session_id: str
    run_dir: str
    steps_dir: str
    logs_dir: str
    llm_logs_dir: str
    reports_dir: str
    figma_dir: str
    memory_dir: str
    shared_memory_dir: str

    def step_dir(self, step_number: int, retry_count: int = 0) -> str:
        base = f"{int(step_number):03d}"
        if retry_count > 0:
            base = f"{base}_retry_{int(retry_count):02d}"
        return os.path.join(self.steps_dir, base)

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def create_run_output(mode: str, tcs_id: str, timestamp: str | None = None,
                      run_root: str | None = None, scenario_index: int | None = None) -> RunOutputPaths:
    """Create standard output folders and return all paths for one scenario run.

    When *run_root* and *scenario_index* are provided, the scenario dir is
    placed under ``run_root/scenario_NN/``.  Otherwise the old flat layout
    ``runs/<mode>/<date>/<tcs_id>__<timestamp>/`` is used (backward compat).
    """
    mode = _safe_part(mode.lower())
    tcs_id = _safe_part(tcs_id)
    timestamp = timestamp or datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    date = _timestamp_to_date(timestamp)
    session_id = f"{tcs_id}_{timestamp}"

    root = config.OUTPUT_DIR

    if run_root and scenario_index is not None:
        run_dir = os.path.join(run_root, scenario_dir_name(scenario_index))
        shared_memory_dir = os.path.join(root, "runs", mode, "_memory")
    else:
        run_name = f"{tcs_id}__{timestamp}"
        run_dir = os.path.join(root, "runs", mode, date, run_name)
        shared_memory_dir = os.path.join(root, "shared", f"{mode}_memory")

    steps_dir = os.path.join(run_dir, "steps")
    logs_dir = os.path.join(run_dir, "logs")
    llm_logs_dir = os.path.join(logs_dir, "llm")
    reports_dir = os.path.join(run_dir, "reports")
    figma_dir = os.path.join(run_dir, "figma")
    memory_dir = os.path.join(run_dir, "memory")

    paths = RunOutputPaths(
        root=root,
        mode=mode,
        date=date,
        session_id=session_id,
        run_dir=run_dir,
        steps_dir=steps_dir,
        logs_dir=logs_dir,
        llm_logs_dir=llm_logs_dir,
        reports_dir=reports_dir,
        figma_dir=figma_dir,
        memory_dir=memory_dir,
        shared_memory_dir=shared_memory_dir,
    )

    for directory in (
        run_dir,
        steps_dir,
        logs_dir,
        llm_logs_dir,
        reports_dir,
        figma_dir,
        memory_dir,
        shared_memory_dir,
    ):
        os.makedirs(directory, exist_ok=True)

    return paths


def build_step_dir(output_dir: str, step_number: int, retry_count: int = 0) -> str:
    """Return canonical step directory under a run output dir and create it."""
    steps_dir = os.path.join(output_dir, "steps")
    base = f"{int(step_number):03d}"
    if retry_count > 0:
        base = f"{base}_retry_{int(retry_count):02d}"
    step_dir = os.path.join(steps_dir, base)
    os.makedirs(step_dir, exist_ok=True)
    return step_dir


def write_latest_index(paths: RunOutputPaths) -> str:
    """Update outputs/indexes/latest.json and per-mode run index."""
    indexes_dir = os.path.join(paths.root, "indexes")
    os.makedirs(indexes_dir, exist_ok=True)

    latest_path = os.path.join(indexes_dir, "latest.json")
    latest = {}
    if os.path.exists(latest_path):
        try:
            with open(latest_path, "r", encoding="utf-8") as f:
                latest = json.load(f)
        except Exception:
            latest = {}

    latest[paths.mode] = paths.run_dir
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(latest, f, indent=2, ensure_ascii=False)

    mode_index_path = os.path.join(indexes_dir, f"{paths.mode}_runs.json")
    mode_index = []
    if os.path.exists(mode_index_path):
        try:
            with open(mode_index_path, "r", encoding="utf-8") as f:
                mode_index = json.load(f)
        except Exception:
            mode_index = []

    entry = {
        "session_id": paths.session_id,
        "date": paths.date,
        "run_dir": paths.run_dir,
    }
    mode_index = [item for item in mode_index if item.get("session_id") != paths.session_id]
    mode_index.append(entry)
    with open(mode_index_path, "w", encoding="utf-8") as f:
        json.dump(mode_index, f, indent=2, ensure_ascii=False)

    return latest_path


def _timestamp_to_date(timestamp: str) -> str:
    try:
        return datetime.datetime.strptime(timestamp[:15], "%Y%m%d_%H%M%S").strftime("%Y-%m-%d")
    except ValueError:
        return datetime.datetime.now().strftime("%Y-%m-%d")
