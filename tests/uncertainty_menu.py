"""

MAS AI — Observer DSE Uncertainty Test Menu

An interactive console launcher for tests/run_observer_uncertainty.py.
Wraps all three test modes (self-test / existing step / custom image+elements)
so you don't have to hand-type paths.

"""

import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from shared.config import OBSERVER_UNCERTAINTY_MAX_WIDGETS as _MAX_WIDGETS
except Exception:
    _MAX_WIDGETS = 20

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
RUNNER = os.path.join(SCRIPT_DIR, "run_observer_uncertainty.py")
OUTPUTS_DIR = os.path.join(REPO_ROOT, "outputs", "runs")

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BLUE = "\033[36m"
GRAY = "\033[90m"

try:
    "✔ ✘ ━".encode(sys.stdout.encoding or 'utf-8')
    SUCCESS_ICON = f"{GREEN}✔{RESET}"
    FAILURE_ICON = f"{RED}✘{RESET}"
    LINE_CHAR = "━"
except Exception:
    SUCCESS_ICON = f"{GREEN}[OK]{RESET}"
    FAILURE_ICON = f"{RED}[FAIL]{RESET}"
    LINE_CHAR = "="


def print_banner():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"{BOLD}{BLUE}===================================================================={RESET}")
    print(f"{BOLD}{BLUE}         MAS AI — OBSERVER DSE UNCERTAINTY TEST MENU                {RESET}")
    print(f"{BOLD}{BLUE}===================================================================={RESET}")


def classify_step_dir(step_dir):
    """Classify one steps/NNN dir for DSE-testability.

    Returns a dict: {dir, status, reason, widget_count}
      status "good"   - annotated.png + merged.json both present and valid, widget
                         count within OBSERVER_UNCERTAINTY_MAX_WIDGETS -> runs as-is.
      status "capped" - valid, but widget count exceeds the cap -> still runnable,
                         extra widgets will be skipped and marked skipped_widget_cap.
      status "broken" - missing/unreadable/empty required files -> cannot run.
    """
    img = os.path.join(step_dir, "annotated.png")
    els = os.path.join(step_dir, "merged.json")

    if not os.path.exists(img):
        return {"dir": step_dir, "status": "broken", "reason": "missing annotated.png", "widget_count": None}
    if os.path.getsize(img) == 0:
        return {"dir": step_dir, "status": "broken", "reason": "annotated.png is empty (0 bytes)", "widget_count": None}
    if not os.path.exists(els):
        return {"dir": step_dir, "status": "broken", "reason": "missing merged.json", "widget_count": None}

    try:
        with open(els, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"dir": step_dir, "status": "broken", "reason": f"merged.json unreadable ({e})", "widget_count": None}

    if not isinstance(data, list):
        return {"dir": step_dir, "status": "broken", "reason": "merged.json is not a list", "widget_count": None}
    if len(data) == 0:
        return {"dir": step_dir, "status": "broken", "reason": "merged.json has zero widgets", "widget_count": 0}
    if not all(isinstance(w, dict) and "id" in w for w in data):
        return {"dir": step_dir, "status": "broken", "reason": "some widgets missing an 'id' field", "widget_count": len(data)}

    n = len(data)
    if n > _MAX_WIDGETS:
        return {
            "dir": step_dir, "status": "capped", "widget_count": n,
            "reason": f"{n} widgets > cap of {_MAX_WIDGETS} — {n - _MAX_WIDGETS} will be skipped (measurement_status=skipped_widget_cap)",
        }
    return {"dir": step_dir, "status": "good", "reason": f"{n} widgets, all within cap", "widget_count": n}


def find_step_dirs():
    """Find every steps/NNN dir under outputs/runs, newest first, classified as
    good/capped/broken for DSE testability. Works for both old (scenario_01) and
    new ({tcs_id}__{ts}) layouts."""
    pattern = os.path.join(OUTPUTS_DIR, "**", "steps", "*")
    candidates = [d for d in glob.glob(pattern, recursive=True) if os.path.isdir(d)]
    candidates.sort(key=lambda d: os.path.getmtime(d), reverse=True)
    return [classify_step_dir(d) for d in candidates]


def display_step_label(step_dir):
    rel = os.path.relpath(step_dir, OUTPUTS_DIR)
    return rel.replace("\\", " / ")


def run_command(cmd):
    print(f"\n{GRAY}$ {' '.join(cmd)}{RESET}\n")
    sys.stdout.flush()
    sys.stderr.flush()
    result = subprocess.run(cmd, cwd=REPO_ROOT, stdout=sys.stdout, stderr=sys.stderr)
    sys.stdout.flush()
    sys.stderr.flush()
    if result.returncode == 0:
        print(f"\n{SUCCESS_ICON} {GREEN}Command finished successfully.{RESET}")
    else:
        print(f"\n{FAILURE_ICON} {RED}Command exited with code {result.returncode}.{RESET}")
    return result.returncode


def menu_self_test():
    border = LINE_CHAR * 68
    print(f"\n{BOLD}{BLUE}{border}{RESET}")
    print(f"{BOLD}{BLUE} Offline Self-Test (no API calls, injected samples){RESET}")
    print(f"{BOLD}{BLUE}{border}{RESET}")
    run_command([sys.executable, "-u", RUNNER, "--self-test"])


def menu_existing_step():
    border = LINE_CHAR * 68
    print(f"\n{BOLD}{BLUE}{border}{RESET}")
    print(f"{BOLD}{BLUE} Test Against an Existing Run's Step (real LLM calls){RESET}")
    print(f"{BOLD}{BLUE}{border}{RESET}")

    all_steps = find_step_dirs()
    if not all_steps:
        print(f"\n {RED}No step folders found under outputs/runs/ at all.{RESET}")
        print(f" Run the framework once first (python main.py).")
        return

    runnable = [s for s in all_steps if s["status"] in ("good", "capped")]
    broken = [s for s in all_steps if s["status"] == "broken"]

    print(f"\n {BOLD}{len(runnable)} runnable{RESET}, {GRAY}{len(broken)} excluded (broken){RESET} "
          f"out of {len(all_steps)} step folder(s) scanned.")

    if not runnable:
        print(f"\n {RED}None of the found steps are runnable.{RESET}")
        _show_broken_steps(broken)
        return

    page_size = 10
    page = 0
    while True:
        start = page * page_size
        page_items = runnable[start:start + page_size]
        print(f"\n {BOLD}Select a step, newest first:{RESET}")
        for i, s in enumerate(page_items, start=1):
            if s["status"] == "capped":
                tag = f"{YELLOW}[capped]{RESET}"
            else:
                tag = f"{GREEN}[ok]{RESET}"
            print(f"  [{GREEN}{i}{RESET}] {tag} {display_step_label(s['dir'])}")
            if s["status"] == "capped":
                print(f"       {GRAY}{s['reason']}{RESET}")
        nav_hint = []
        if start + page_size < len(runnable):
            nav_hint.append("[n] next page")
        if page > 0:
            nav_hint.append("[p] previous page")
        if broken:
            nav_hint.append(f"[x] show {len(broken)} excluded/broken")
        nav_hint.append("[0] back")
        print(f" {GRAY}{'  '.join(nav_hint)}{RESET}")

        choice = input(f"\n {BOLD}Select a step (1-{len(page_items)}): {RESET}").strip().lower()
        if choice == "0":
            return
        if choice == "n" and start + page_size < len(runnable):
            page += 1
            continue
        if choice == "p" and page > 0:
            page -= 1
            continue
        if choice == "x" and broken:
            _show_broken_steps(broken)
            input(f"\n{GRAY}Press Enter to continue...{RESET}")
            continue
        if choice.isdigit() and 1 <= int(choice) <= len(page_items):
            step = page_items[int(choice) - 1]
            if step["status"] == "capped":
                print(f"\n {YELLOW}Note: {step['reason']}{RESET}")
            run_command([sys.executable, "-u", RUNNER, "--step-dir", step["dir"]])
            return
        print(f" {RED}Invalid choice.{RESET}")


def _show_broken_steps(broken):
    if not broken:
        print(f"\n {GRAY}No excluded steps.{RESET}")
        return
    print(f"\n {BOLD}Excluded (cannot run) — {len(broken)} step(s):{RESET}")
    for s in broken:
        print(f"  {RED}✘{RESET} {display_step_label(s['dir'])}")
        print(f"     {GRAY}reason: {s['reason']}{RESET}")


def menu_custom_image():
    border = LINE_CHAR * 68
    print(f"\n{BOLD}{BLUE}{border}{RESET}")
    print(f"{BOLD}{BLUE} Test Against a Custom Image + Elements File (real LLM calls){RESET}")
    print(f"{BOLD}{BLUE}{border}{RESET}")

    image = input(f"\n {BOLD}Path to screenshot image: {RESET}").strip().strip('"')
    if not image or not os.path.exists(image):
        print(f" {RED}Image not found: {image}{RESET}")
        return

    elements = input(f" {BOLD}Path to elements JSON (merged.json-shaped): {RESET}").strip().strip('"')
    if not elements or not os.path.exists(elements):
        print(f" {RED}Elements file not found: {elements}{RESET}")
        return

    output_dir = input(f" {BOLD}Output dir (Enter for a temp dir): {RESET}").strip().strip('"')

    cmd = [sys.executable, "-u", RUNNER, "--image", image, "--elements", elements]
    if output_dir:
        cmd += ["--output-dir", output_dir]
    run_command(cmd)


def menu_env_status():
    border = LINE_CHAR * 68
    print(f"\n{BOLD}{BLUE}{border}{RESET}")
    print(f"{BOLD}{BLUE} Current Uncertainty Config (.env){RESET}")
    print(f"{BOLD}{BLUE}{border}{RESET}\n")
    sys.path.insert(0, REPO_ROOT)
    from shared import config
    print(f"  OBSERVER_UNCERTAINTY_ENABLED     = {config.OBSERVER_UNCERTAINTY_ENABLED}")
    print(f"  OBSERVER_UNCERTAINTY_SAMPLES     = {config.OBSERVER_UNCERTAINTY_SAMPLES}")
    print(f"  OBSERVER_UNCERTAINTY_TEMPERATURE = {config.OBSERVER_UNCERTAINTY_TEMPERATURE}")
    print(f"  OBSERVER_UNCERTAINTY_MAX_WIDGETS = {config.OBSERVER_UNCERTAINTY_MAX_WIDGETS}")
    print(f"  OBSERVER_PROVIDER                = {config.OBSERVER_PROVIDER}")
    print(f"  OBSERVER_MODEL                   = {config.OBSERVER_MODEL}")
    print(f"\n {GRAY}Note: options 2 and 3 below always run DSE regardless of{RESET}")
    print(f" {GRAY}OBSERVER_UNCERTAINTY_ENABLED — that flag only gates the hook inside{RESET}")
    print(f" {GRAY}the production Observer agent, not this standalone runner.{RESET}")


def main():
    while True:
        print_banner()
        all_steps = find_step_dirs()
        runnable_count = sum(1 for s in all_steps if s["status"] in ("good", "capped"))
        broken_count = sum(1 for s in all_steps if s["status"] == "broken")
        steps_label = f"{runnable_count} runnable"
        if broken_count:
            steps_label += f", {broken_count} excluded"
        print(f"\n{BOLD}{BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
        print(f"{BOLD}{BLUE}  SELECT TEST MODE:{RESET}")
        print(f"{BOLD}{BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
        print(f"  [{GREEN}1{RESET}] Offline self-test              {GRAY}(no API calls, instant){RESET}")
        print(f"  [{GREEN}2{RESET}] Test an existing run's step    {GRAY}({steps_label}){RESET}")
        print(f"  [{GREEN}3{RESET}] Test a custom image + elements {GRAY}(type your own paths){RESET}")
        print(f"  [{GREEN}4{RESET}] Show current uncertainty config (.env)")
        print(f"  [{GREEN}5{RESET}] {BOLD}{RED}Exit{RESET}")
        print(f"{BOLD}{BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")

        try:
            choice = input(f" {BOLD}Enter your choice (1-5): {RESET}").strip()
        except KeyboardInterrupt:
            print(f"\n\n {FAILURE_ICON} Exited.")
            break

        if choice == "1":
            menu_self_test()
        elif choice == "2":
            menu_existing_step()
        elif choice == "3":
            menu_custom_image()
        elif choice == "4":
            menu_env_status()
        elif choice == "5":
            print(f"\n{BOLD}{GREEN} Exiting. Goodbye!{RESET}\n")
            break
        else:
            print(f"\n {FAILURE_ICON} {RED}Invalid choice! Please select 1-5.{RESET}")

        input(f"\n{GRAY}Press Enter to return to main menu...{RESET}")


if __name__ == "__main__":
    main()
