"""Select and pre-parse an N=400 calibration sample from Screen Annotation.

N=400 matches Farquhar et al. 2024's own main QA evaluation scale ("we use
400 train examples and 400 test examples randomly sampled from the original
larger dataset") — see `Dokumen Kepake/DSE Calibration Experiment - Big
Plan.md`, decision log, 2026-07-24.

Usage:
    python core/calibration/sample_screen_annotation.py \\
        --csv path/to/screen_annotation_train.csv \\
        --n 400 --seed 20260724 \\
        --out experiment/calibration/screen_annotation_sample.json

Output is a JSON list of:
    {"screen_id": "...", "elements": [{"type", "text", "bbox"}, ...]}
where bbox is already converted to [x1, y1, x2, y2] order, still in the
dataset's native 0-999 normalized space (pixel-scale conversion happens
later, once each image's actual dimensions are known — see
`screen_annotation_parser.scale_bbox_to_pixels`).

The random seed is fixed and logged in the output file itself so the sample
is reproducible — an arbitrary re-sample every run would make the eventual
AUROC/AURAC numbers non-reproducible, which matters for a thesis result.
"""
import argparse
import csv
import json
import os
import random
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.calibration.screen_annotation_parser import parse_flat, to_xyxy_0_999

csv.field_size_limit(10_000_000)


def load_rows(csv_path: str) -> list:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def build_sample(csv_path: str, n: int, seed: int) -> dict:
    rows = load_rows(csv_path)
    if n > len(rows):
        raise ValueError(f"Requested n={n} exceeds dataset size {len(rows)}")

    rng = random.Random(seed)
    chosen = rng.sample(rows, n)

    samples = []
    skipped_no_elements = 0
    for row in chosen:
        flat = parse_flat(row["screen_annotation"])
        elements = [
            {"type": el["type"], "text": el["text"],
             "bbox": to_xyxy_0_999(el["bbox"]) if el["bbox"] else None}
            for el in flat
        ]
        if not elements:
            skipped_no_elements += 1
            continue
        samples.append({"screen_id": row["screen_id"], "elements": elements})

    return {
        "source": "google-research-datasets/screen_annotation (train split)",
        "seed": seed,
        "requested_n": n,
        "actual_n": len(samples),
        "skipped_no_elements": skipped_no_elements,
        "bbox_order": "x1_y1_x2_y2_normalized_0_999",
        "samples": samples,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", required=True, help="Path to Screen Annotation train.csv")
    p.add_argument("--n", type=int, default=400)
    p.add_argument("--seed", type=int, default=20260724)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    result = build_sample(args.csv, args.n, args.seed)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"[OK] wrote {result['actual_n']}/{result['requested_n']} samples to {args.out}")
    if result["skipped_no_elements"]:
        print(f"[WARN] {result['skipped_no_elements']} sampled screens had zero "
              f"parseable elements and were dropped — re-run with a larger "
              f"--n if you need exactly {args.n} usable screens.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
