import sys
import os
import argparse

# ── stdout/stderr UTF-8 ──────────────────────────────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from shared import config


# ── helpers ──────────────────────────────────────────────────────────────────

SCENARIOS_ROOT = os.path.join(os.path.dirname(__file__), "scenarios")


def _list_scenario_folders() -> list[str]:
    """Return subfolder names inside scenarios/ that contain a scenario.xlsx."""
    if not os.path.isdir(SCENARIOS_ROOT):
        return []
    folders = []
    for name in sorted(os.listdir(SCENARIOS_ROOT)):
        folder_path = os.path.join(SCENARIOS_ROOT, name)
        if os.path.isdir(folder_path) and os.path.isfile(
            os.path.join(folder_path, "scenario.xlsx")
        ):
            folders.append(name)
    return folders


def _resolve_xlsx_path(scenario_arg: str) -> str:
    """
    Accept either:
    - a subfolder name  →  scenarios/<name>/scenario.xlsx
    - a relative/absolute path to a .xlsx file
    """
    if scenario_arg.endswith(".xlsx") and os.path.isfile(scenario_arg):
        return os.path.abspath(scenario_arg)

    # treat as subfolder name or path
    candidate = os.path.join(SCENARIOS_ROOT, scenario_arg, "scenario.xlsx")
    if os.path.isfile(candidate):
        return os.path.abspath(candidate)

    # maybe the user passed a full path without .xlsx
    candidate2 = os.path.join(scenario_arg, "scenario.xlsx")
    if os.path.isfile(candidate2):
        return os.path.abspath(candidate2)

    return ""


def _interactive_pick_scenario() -> str:
    """Show available scenario folders and let the user choose one."""
    folders = _list_scenario_folders()
    if not folders:
        print(
            f"[-] No scenario folders found in '{SCENARIOS_ROOT}'.\n"
            "    Create a subfolder with a scenario.xlsx inside it first."
        )
        sys.exit(1)

    print("\n[*] Available scenarios:")
    for i, name in enumerate(folders, 1):
        print(f"    [{i}] {name}")
    print()

    while True:
        try:
            raw = input("    Select scenario (number or name): ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(folders):
                return folders[idx]
        elif raw in folders:
            return raw
        print(f"    Invalid choice '{raw}', try again.")


def _interactive_pick_figma() -> str:
    """Prompt for a Figma URL (may be empty)."""
    print()
    print("    Enter Figma file URL (or press Enter to skip): ", end="", flush=True)
    try:
        return input().strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="MAS AI — Multi-Agent Android GUI Testing Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --scenario firebase_chat --mode predefined
  python main.py --scenario firebase_chat --mode predefined --preflight-only
  python main.py --scenario firebase_chat --mode predefined --resume RUN_ROOT
  python main.py --scenario notes --figma "https://figma.com/design/..."
  python main.py -s notes -m autonomous
  python main.py --list
  python main.py                        # interactive picker
""",
    )

    parser.add_argument(
        "-s", "--scenario",
        metavar="FOLDER_OR_PATH",
        help=(
            "Scenario subfolder name inside scenarios/ "
            "(e.g. 'notes') or a direct path to a scenario.xlsx file. "
            "If omitted, an interactive menu is shown."
        ),
    )
    parser.add_argument(
        "-f", "--figma",
        metavar="FIGMA_URL",
        default=None,
        help=(
            "Figma file URL to use for visual validation. "
            "Overrides FIGMA_URL_QA from .env."
        ),
    )
    parser.add_argument(
        "-m", "--mode",
        choices=["predefined", "autonomous"],
        default=None,
        help="Workflow mode. Overrides WORKFLOW_STRATEGY from .env.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available scenario folders and exit.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run read-only predefined baseline preflight and exit.",
    )
    parser.add_argument(
        "--resume",
        metavar="RUN_ROOT",
        default=None,
        help="Resume an existing predefined batch run root.",
    )

    return parser


def validate_cli_options(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    *,
    effective_mode: str,
) -> None:
    if args.resume and effective_mode == "autonomous":
        parser.error("--resume is available only with predefined mode")
    if args.preflight_only and effective_mode == "autonomous":
        parser.error("--preflight-only is available only with predefined mode")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    # --list
    if args.list:
        folders = _list_scenario_folders()
        if folders:
            print("[*] Available scenario folders:")
            for name in folders:
                print(f"    • scenarios/{name}/scenario.xlsx")
        else:
            print(f"[-] No scenario folders found in '{SCENARIOS_ROOT}'.")
        sys.exit(0)

    # ── resolve scenario path ─────────────────────────────────────────────────
    if args.scenario:
        xlsx_path = _resolve_xlsx_path(args.scenario)
        if not xlsx_path:
            print(
                f"[-] Could not find scenario.xlsx for '{args.scenario}'.\n"
                f"    Expected location: scenarios/{args.scenario}/scenario.xlsx"
            )
            sys.exit(1)
    else:
        scenario_folder = _interactive_pick_scenario()
        xlsx_path = _resolve_xlsx_path(scenario_folder)

    print(f"[*] Scenario file : {xlsx_path}")

    mode = args.mode or config.WORKFLOW_STRATEGY
    validate_cli_options(parser, args, effective_mode=mode)
    print(f"[*] Mode          : {mode}")

    # ── resolve figma URL ─────────────────────────────────────────────────────
    figma_url = args.figma  # None means "fall back to env / interactive prompt"
    if figma_url:
        print(f"[*] Figma URL     : {figma_url}")
    elif (
        mode == "autonomous"
        and not args.preflight_only
        and not config.FIGMA_FILE_URL
    ):
        # No env var set and no CLI flag → offer interactive prompt
        figma_url = _interactive_pick_figma()

    # ── resolve mode ──────────────────────────────────────────────────────────
    # ── dispatch ──────────────────────────────────────────────────────────────
    if mode == "autonomous":
        from core.workflow.autonomous.runner import run_autonomous
        run_autonomous(xlsx_path=xlsx_path, figma_url=figma_url)
    else:
        from core.workflow.predefined.runner import run_predefined
        run_predefined(
            xlsx_path=xlsx_path,
            figma_url=figma_url,
            preflight_only=args.preflight_only,
            resume=args.resume,
        )
