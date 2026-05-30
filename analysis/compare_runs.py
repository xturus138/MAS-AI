"""
Aggregate and compare final_metrics.json files from predefined test runs.

Usage:
    python analysis/compare_runs.py
    python analysis/compare_runs.py --output_dir outputs/predefined
    python analysis/compare_runs.py --csv results.csv
"""

import argparse
import json
import math
import os
import sys
from pathlib import Path


RESEARCH_KEYS = [
    "coverage_rate",
    "decision_accuracy_initial_acc1",
    "decision_accuracy_final_accf",
    "verification_pass_rate",
    "widget_localization_effectiveness",
    "widget_text_fallback_recoveries",
    "time_overhead_seconds",
    "token_consumption",
]

TOP_LEVEL_KEYS = [
    "tool_precision_rate",
    "total_duration_seconds",
    "total_price_usd",
    "total_tokens_estimate",
    "recovery_attempts",
    "physical_actions",
    "stagnation_count",
]


def load_metrics(output_dir: str) -> list:
    """Walk output_dir and collect all predefined final_metrics.json files."""
    records = []
    base = Path(output_dir)
    for path in sorted(base.rglob("final_metrics.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("mode") != "predefined":
                continue
            flat = {
                "tcs_id":    data.get("tcs_id", "?"),
                "status":    data.get("status", "?"),
                "run_dir":   str(path.parent),
                "timestamp": data.get("timestamp", ""),
            }
            for k in TOP_LEVEL_KEYS:
                flat[k] = data.get(k)
            rm = data.get("research_metrics", {})
            for k in RESEARCH_KEYS:
                flat[k] = rm.get(k)
            records.append(flat)
        except Exception as e:
            print(f"[warn] Could not load {path}: {e}", file=sys.stderr)
    return records


def _mean(vals: list):
    clean = [v for v in vals if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def _std(vals: list):
    clean = [v for v in vals if v is not None]
    if len(clean) < 2:
        return None
    mu = sum(clean) / len(clean)
    variance = sum((x - mu) ** 2 for x in clean) / (len(clean) - 1)
    return round(math.sqrt(variance), 2)


def summarize(records: list) -> dict:
    all_keys = TOP_LEVEL_KEYS + RESEARCH_KEYS
    summary = {
        "n_runs":      len(records),
        "n_success":   sum(1 for r in records if r["status"] == "SUCCESS"),
        "n_failed":    sum(1 for r in records if r["status"] == "FAILED"),
        "n_stagnated": sum(1 for r in records if r["status"] == "STAGNATED"),
    }
    for k in all_keys:
        vals = [r.get(k) for r in records]
        summary[f"{k}_mean"] = _mean(vals)
        summary[f"{k}_std"]  = _std(vals)
    return summary


def print_table(records: list, summary: dict):
    print(f"\n{'='*60}")
    print(f"  MAS AI Predefined Run Analysis — {summary['n_runs']} runs")
    print(f"  SUCCESS: {summary['n_success']}  FAILED: {summary['n_failed']}  STAGNATED: {summary['n_stagnated']}")
    print(f"{'='*60}\n")

    print(f"{'TCS ID':<20} {'Status':<12} {'Coverage%':>10} {'Acc1%':>8} {'ToolPrec%':>10} {'Dur(s)':>8} {'Cost$':>8}")
    print("-" * 80)
    for r in records:
        print(
            f"{r['tcs_id']:<20} {r['status']:<12}"
            f" {str(r.get('coverage_rate') or '-'):>10}"
            f" {str(r.get('decision_accuracy_initial_acc1') or '-'):>8}"
            f" {str(r.get('tool_precision_rate') or '-'):>10}"
            f" {str(r.get('total_duration_seconds') or '-'):>8}"
            f" {str(r.get('total_price_usd') or '-'):>8}"
        )

    display_keys = [
        ("coverage_rate",                     "Coverage Rate (%)"),
        ("decision_accuracy_initial_acc1",    "Decision Accuracy Acc1 (%)"),
        ("decision_accuracy_final_accf",      "Decision Accuracy AccF (%)"),
        ("tool_precision_rate",               "Tool Precision Rate (%)"),
        ("widget_localization_effectiveness", "Widget Localization (%)"),
        ("total_duration_seconds",            "Duration (s)"),
        ("total_price_usd",                   "Cost (USD)"),
        ("total_tokens_estimate",             "Tokens"),
    ]
    print(f"\n{'Metric':<40} {'Mean':>10} {'Std Dev':>10}")
    print("-" * 62)
    for key, label in display_keys:
        mean_val = summary.get(f"{key}_mean", "-")
        std_val  = summary.get(f"{key}_std", "-")
        print(f"  {label:<38} {str(mean_val):>10} {str(std_val):>10}")


def write_csv(records: list, path: str):
    import csv
    if not records:
        return
    fieldnames = list(records[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"\n[+] CSV saved to: {path}")


def main():
    parser = argparse.ArgumentParser(description="Aggregate MAS AI predefined run metrics.")
    parser.add_argument(
        "--output_dir", default="outputs/predefined",
        help="Root directory to scan for final_metrics.json files (default: outputs/predefined)"
    )
    parser.add_argument(
        "--csv", default="",
        help="Optional path to export results as CSV (e.g. results.csv)"
    )
    args = parser.parse_args()

    records = load_metrics(args.output_dir)
    if not records:
        print(f"[!] No predefined final_metrics.json found under '{args.output_dir}'.")
        sys.exit(1)

    summary = summarize(records)
    print_table(records, summary)

    if args.csv:
        write_csv(records, args.csv)


if __name__ == "__main__":
    main()
