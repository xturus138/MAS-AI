"""Aggregate per-screen calibration results into the final AUROC/AURAC
report — the last leg of Phase 4/5 in the Big Plan.

Reads every `{screen_id}.json` written by `run_calibration.py`, pools all
labeled widgets across all 400 screens into one (raw_dse, is_correct)
dataset, and computes AUROC / the rejection-accuracy curve / AURAC per
Farquhar et al. 2024's definitions (`threshold_metrics.py`).

Usage:
    python core/calibration/compute_calibration_report.py \\
        --results-dir outputs/calibration/results \\
        --out outputs/calibration/calibration_report.json
"""
import argparse
import glob
import json
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.calibration.threshold_metrics import auroc, aurac, rejection_accuracy_curve


def load_pairs(results_dir: str) -> tuple:
    """Returns (uncertainty_scores, is_correct, n_screens, n_widgets_skipped)."""
    scores, labels = [], []
    n_screens = 0
    n_skipped = 0
    for path in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        n_screens += 1
        n_skipped += data.get("skipped_no_ground_truth_match", 0)
        n_skipped += data.get("skipped_parse_failure", 0)
        for w in data.get("widgets", []):
            scores.append(w["raw_dse"])
            labels.append(w["is_correct"])
    return scores, labels, n_screens, n_skipped


def build_report(results_dir: str) -> dict:
    scores, labels, n_screens, n_skipped = load_pairs(results_dir)
    n = len(scores)
    n_correct = sum(1 for c in labels if c)

    report = {
        "n_screens": n_screens,
        "n_labeled_widgets": n,
        "n_skipped_widgets": n_skipped,
        "n_correct": n_correct,
        "n_incorrect": n - n_correct,
        "baseline_accuracy": (n_correct / n) if n else None,
    }

    if n == 0:
        report["interpretation"] = (
            "No labeled widgets — nothing to compute. Check that "
            "run_calibration.py actually produced results in this directory."
        )
        return report

    report["auroc"] = auroc(scores, labels)
    curve = rejection_accuracy_curve(scores, labels, steps=100)
    report["rejection_accuracy_curve"] = curve
    report["aurac"] = aurac(curve)

    if report["auroc"] <= 0.55:
        report["interpretation"] = (
            f"AUROC={report['auroc']:.3f} is close to 0.5 (uninformative). "
            "DSE does not appear to discriminate correct from incorrect "
            "widget descriptions on this sample — a threshold would not "
            "help. This is a reportable negative finding (see Big Plan, "
            "Phase 5), not a pipeline failure."
        )
    else:
        report["interpretation"] = (
            f"AUROC={report['auroc']:.3f} is meaningfully above 0.5. DSE "
            "discriminates correct from incorrect widget descriptions on "
            "this sample. Inspect rejection_accuracy_curve to pick an "
            "operating threshold (Big Plan, Phase 5)."
        )
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results-dir", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    report = build_report(args.results_dir)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"[OK] {report['n_labeled_widgets']} labeled widgets from "
          f"{report['n_screens']} screens.")
    if "auroc" in report:
        print(f"[RESULT] AUROC={report['auroc']:.4f}  AURAC={report['aurac']:.4f}")
    print(report["interpretation"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
