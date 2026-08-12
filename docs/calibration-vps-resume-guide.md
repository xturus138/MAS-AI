# DSE Calibration — VPS Resume Guide

Reference for continuing the calibration run in future sessions: how to resume from wherever it left off, generate the report, and sync results to GitHub.

**Current status (as of 2026-07-30):** N=19 screens completed, AUROC=0.760, AURAC=0.830, committed to `main` (commit `d34599f`). Target sample is N=400; run stopped early because the Gemini API key ran out of free-tier credit.

## Access

```
ssh raditya@103.93.129.70
cd ~/MAS-AI
```

Key: your local `id_ed25519` (comment `raditya-vast`), already authorized on the VPS.

## 1. Check current progress

```bash
ls experiment/calibration/results/*.json | wc -l
```

Compares against the 400-screen target. Anything already there is safe — `run_calibration.py` skips completed screens automatically.

## 2. Before resuming: make sure there's API budget

The run previously stopped because the Gemini key exhausted its free-tier quota. Check before starting a new batch:

- https://aistudio.google.com/apikey — confirm the key has billing enabled or fresh free-tier quota.
- If it's still free-tier only, either enable billing (Google Cloud Console → link a billing account) or wait for quota to reset.
- Rough cost: ~$0.10–0.25 per screen at the current config (`OBSERVER_UNCERTAINTY_SAMPLES=10`, `OBSERVER_UNCERTAINTY_MAX_WIDGETS=20`).

## 3. Start (or reattach to) a tmux session

New session:
```bash
tmux new -s calibration
```

Reattach to an existing one:
```bash
tmux attach -t calibration
```

Detach without killing it: `Ctrl+b` then `d`. Don't close the terminal window directly or press `Ctrl+c` unless you actually want to stop the run — closing the SSH window alone won't kill tmux, but killing the tmux session (or the VPS) does kill whatever's running inside it.

## 4. Resume the run

Inside tmux:

```bash
cd ~/MAS-AI
python3 core/calibration/run_calibration.py \
  --sample experiment/calibration/screen_annotation_sample_400.json \
  --images experiment/calibration/rico_images \
  --out-dir experiment/calibration/results
```

This picks up automatically — it skips every screen that already has a `.json` in `experiment/calibration/results/`. No flags needed to control "how many" to do; it just keeps going until it's done all 400 or you stop it. Live output shows per-screen progress, cost, and a running ETA.

**To stop after a while (e.g. once you're happy with the budget spent):** `Ctrl+c` inside the tmux pane. It's safe — the screen currently mid-flight may be lost, but every screen already written to a `.json` file is kept.

Then detach (`Ctrl+b`, `d`) and disconnect if you're not stopping it, or just exit if you did stop it.

## 5. Clean up scratch folders

After a run (whether it finished or you stopped it), each screen leaves a `_work_{screen_id}/` scratch folder next to its `.json` result. Safe to delete once you don't need to debug that screen:

```bash
rm -rf experiment/calibration/results/_work_*
```

Only delete these — never delete the `.json` result files themselves.

## 6. Compute the calibration report

```bash
python3 core/calibration/compute_calibration_report.py \
  --results-dir experiment/calibration/results \
  --out experiment/calibration/calibration_report.json
```

Prints `N labeled widgets from N screens`, `AUROC=... AURAC=...`, and an auto-interpretation. Safe to re-run any time — it just recomputes from whatever `.json` files currently exist in `results/`.

## 7. Push results to GitHub

Credentials are already cached on the VPS (`git config --global credential.helper store`), so no token prompt needed after the first time.

```bash
git add -f experiment/calibration/calibration_report.json
git add -f experiment/calibration/results/*.json
git commit -m "calibration: N=<screen count>, AUROC=<value>"
git push origin main
```

(`outputs/` is gitignored repo-wide, so `-f` is required to force-add these specific files. `origin` is the VPS's remote name — your local clone calls the same remote `MAS-AI`.)

## 8. Pull results down locally

On your Windows machine (PowerShell):

```powershell
cd "C:\Users\radit\Project\VisualStudioProject\Skripsi\MAS AI"
git pull MAS-AI main
```

`experiment/calibration/calibration_report.json` and the per-screen result files will now be up to date locally.

## Repeat

Steps 1–8 form one cycle. Repeat as budget/time allows: check progress → confirm API quota → resume the tmux run → stop when ready → clean up → recompute report → push → pull. Each cycle's report overwrites the previous one with the latest cumulative numbers (N grows each time, never shrinks, since nothing already-completed is redone).

Stop when N=400 is reached, or whenever you decide the current N is sufficient for the thesis — there's no hard requirement to reach 400.
