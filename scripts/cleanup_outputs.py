"""Migrate old messy output folders into the new output layout.

Dry-run by default. Use --apply to move files. Never deletes data.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import shutil
from pathlib import Path

RUN_RE = re.compile(r"^(?P<tcs>[A-Za-z]+-\d{3})_(?P<ts>\d{8}_\d{6})(?:_archived)?$")
STEP_RE = re.compile(r"^step_\d+(?:_retry_\d+)?$")
SCENARIO_RE = re.compile(r"^scenario_\d+$")
RUN_DIR_RE = re.compile(r"^run_\d+$")
DATE_BUCKET_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean MAS AI outputs into outputs/runs layout.")
    parser.add_argument("--root", default="outputs", help="Output root to clean (default: outputs)")
    parser.add_argument("--apply", action="store_true", help="Move files. Without this, dry-run only.")
    parser.add_argument("--dry-run", action="store_true", help="Preview moves without changing files (default).")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"No output root: {root}")
        return 0

    actions: list[tuple[Path, Path]] = []
    quarantine = root / "quarantine" / f"cleanup_{_dt.datetime.now().strftime('%Y%m%d_%H%M%S')}"

    for mode in ("predefined", "autonomous"):
        mode_root = root / mode
        if not mode_root.exists():
            continue

        for entry in mode_root.iterdir():
            if not entry.is_dir():
                continue
            if entry.name in {"past", "_memory"}:
                continue

            match = RUN_RE.match(entry.name)
            if match:
                date_bucket = _date_from_timestamp(match.group("ts"))
                dest = root / "runs" / mode / date_bucket / f"{match.group('tcs')}__{match.group('ts')}"
                actions.append((entry, _unique_dest(dest)))
            elif STEP_RE.match(entry.name) or entry.name == "memory":
                actions.append((entry, _unique_dest(quarantine / mode / entry.name)))

        past_root = mode_root / "past"
        if past_root.exists():
            for entry in past_root.iterdir():
                if not entry.is_dir():
                    continue
                match = RUN_RE.match(entry.name)
                if match:
                    date_bucket = _date_from_timestamp(match.group("ts"))
                    dest = root / "runs" / mode / date_bucket / f"{match.group('tcs')}__{match.group('ts')}"
                    actions.append((entry, _unique_dest(dest)))
                elif STEP_RE.match(entry.name) or entry.name == "memory":
                    actions.append((entry, _unique_dest(quarantine / mode / "past" / entry.name)))

        shared_memory = mode_root / "_memory"
        if shared_memory.exists():
            actions.append((shared_memory, _unique_dest(root / "shared" / f"{mode}_memory")))

    # Attach legacy LLM logs to matching migrated run when possible.
    legacy_llm_root = root / "llm_logs"
    if legacy_llm_root.exists():
        for log_dir in legacy_llm_root.iterdir():
            if not log_dir.is_dir():
                continue
            match = RUN_RE.match(log_dir.name)
            if not match:
                actions.append((log_dir, _unique_dest(quarantine / "llm_logs" / log_dir.name)))
                continue
            dest = _find_matching_run(root, match.group("tcs"), match.group("ts"))
            if dest:
                actions.append((log_dir, _unique_dest(dest / "logs" / "llm")))
            else:
                actions.append((log_dir, _unique_dest(quarantine / "llm_logs" / log_dir.name)))

    # ── Phase 2: Wrap era-1 flat runs under run_N/scenario_NN ──────────────
    runs_root = root / "runs"
    if runs_root.exists():
        for mode in ("predefined", "autonomous"):
            mode_root = runs_root / mode
            if not mode_root.exists():
                continue

            for date_entry in sorted(mode_root.iterdir()):
                if not date_entry.is_dir() or not DATE_BUCKET_RE.match(date_entry.name):
                    continue
                if date_entry.name == "_memory":
                    continue

                # Collect era-1 scenario dirs (not already under run_N)
                flat_dirs = []
                has_run_dirs = False
                for entry in sorted(date_entry.iterdir()):
                    if not entry.is_dir():
                        continue
                    if RUN_DIR_RE.match(entry.name):
                        has_run_dirs = True
                    elif entry.name != "_memory":
                        flat_dirs.append(entry)

                if not flat_dirs:
                    continue

                # If run_N dirs already exist, skip (user may have custom layout)
                if has_run_dirs:
                    print(f"[Skip] {date_entry} already has run_N dirs — {len(flat_dirs)} flat dirs remain")
                    continue

                # Create run_1 and move flat dirs into scenario_NN subdirs
                run_dir = date_entry / "run_1"

                for idx, flat_dir in enumerate(flat_dirs):
                    scenario_name = f"scenario_{idx + 1:02d}"
                    dest = run_dir / scenario_name
                    actions.append((flat_dir, dest))

                # Move any run-level files (test_report.xlsx, run_summary.json)
                for fname in ("test_report.xlsx", "run_summary.json"):
                    src = date_entry / fname
                    if src.exists():
                        actions.append((src, run_dir / fname))

    if not actions:
        print("No cleanup actions needed.")
        return 0

    for src, dest in actions:
        print(f"{'MOVE' if args.apply else 'DRY '} {src} -> {dest}")
        if args.apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))

    print(f"Actions: {len(actions)}")
    print("Applied." if args.apply else "Dry-run only. Re-run with --apply to move files.")
    return 0


def _date_from_timestamp(timestamp: str) -> str:
    try:
        return _dt.datetime.strptime(timestamp, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d")
    except ValueError:
        return "unknown-date"


def _unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    i = 1
    while True:
        candidate = dest.with_name(f"{dest.name}_migrated_{i}")
        if not candidate.exists():
            return candidate
        i += 1


def _find_matching_run(root: Path, tcs_id: str, timestamp: str) -> Path | None:
    run_name = f"{tcs_id}__{timestamp}"
    runs_root = root / "runs"
    if not runs_root.exists():
        return None
    for mode_root in runs_root.iterdir():
        if not mode_root.is_dir():
            continue
        date_bucket = _date_from_timestamp(timestamp)
        candidate = mode_root / date_bucket / run_name
        if candidate.exists():
            return candidate
    return None


if __name__ == "__main__":
    raise SystemExit(main())
