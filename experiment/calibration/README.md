# DSE Calibration Experiment — Data & Run Instructions

Supports `Dokumen Kepake/DSE Calibration Experiment - Big Plan.md`. See that
file for the full phase-by-phase plan and citations; this README is just
the "how to actually run it" pointer.

## What's already here

- `screen_annotation_train.csv` — full Screen Annotation train split (15,548
  rows), downloaded from
  `github.com/google-research-datasets/screen_annotation`.
- `screen_annotation_sample_400.json` — the deterministic N=400 calibration
  sample (seed `20260724`, matching Farquhar et al. 2024's own evaluation
  scale), already parsed into per-element `{type, text, bbox}` records via
  `core/calibration/screen_annotation_parser.py`. Reproducible: re-running
  `sample_screen_annotation.py` with the same seed gives the same 400 IDs.
- `rico_images/` — 5 of the 400 needed screenshots (proof the download
  pipeline works end-to-end against the real archive). **395 remain.**

**Decision (2026-07-27): running Phase 3 now with whatever images are already downloaded**
(272/400 as of this note), rather than waiting for the full 400. `run_calibration.py` already
skips any screen whose image isn't present (prints `[SKIP]`), so this needs no code change — it's
just a smaller-than-planned sample. State this explicitly in the eventual write-up (actual N used,
not the originally planned N=400) rather than presenting it as the full sample. You can still run
`fetch_rico_images.py` again later to top up the remaining images and re-run
`run_calibration.py` (skips screens already processed) + `compute_calibration_report.py` to fold
in the rest.

## What's NOT done and needs to run in your own environment

The remaining work needs real bandwidth and real LLM API access — neither
was available in the sandbox this was built in (observed ~1.1 MB/s against
the 6.0 GB image archive, and no `.env` API keys configured there). Nothing
about the code is blocked; it's an environment/resource gap, not an
unfinished design.

### 1. Finish downloading the images (~5-15 min on normal broadband)

```
python core/calibration/fetch_rico_images.py ^
  --sample experiment/calibration/screen_annotation_sample_400.json ^
  --out-dir experiment/calibration/rico_images
```

Resumable — it skips the 5 images already present and only writes what's
missing. Streams the whole 6.0 GB archive once (no random access is
possible on a gzip-compressed tar), keeping only the ~395 matching files.

### 2. Run the calibration measurement pipeline (needs real API keys)

Uses your existing `.env` (`OBSERVER_UNCERTAINTY_SAMPLES=10`,
`OBSERVER_UNCERTAINTY_TEMPERATURE=1.0`, `OBSERVER_TEMPERATURE=0.1` — same
config the live workflow uses). Cost note: ~400 widgets-worth of screens x
(1 production call + 10 DSE samples + several entailment-judge calls +
1 correctness-judge call) — budget accordingly before running the full 400.

**Widget detection (2026-07-29):** `run_calibration.py` calls
`extract_widgets_from_image(..., method="llm")` by default, matching the live
Observer's `OBSERVER_DETECTION_METHOD=llm` default — zero-shot VLM grounding
via `ObserverAgent._detect_widgets_via_llm`, one structured-output call per
screen, now included in the per-screen cost tracked by `_MeteredLLM`. Unlike
the live workflow, this does **not** silently fall back to the classical
`cv_ocr` pipeline on API failure — a calibration run should surface a real
API failure rather than quietly mixing detection methods within one
experiment. Pass `method="cv_ocr"` explicitly to benchmark the classical
Canny+region+OCR pipeline instead.

```
python core/calibration/run_calibration.py ^
  --sample experiment/calibration/screen_annotation_sample_400.json ^
  --images experiment/calibration/rico_images ^
  --out-dir experiment/calibration/results
```

Resumable — skips screens that already have a `{screen_id}.json` in
`--out-dir`. Prints per-screen progress (labeled / unmatched / parse
failures) as it goes.

### 3. Compute the AUROC / rejection-accuracy / AURAC report

```
python core/calibration/compute_calibration_report.py ^
  --results-dir experiment/calibration/results ^
  --out experiment/calibration/calibration_report.json
```

Prints AUROC and AURAC to the console and writes the full report
(including the rejection-accuracy curve) to `calibration_report.json`.
Interpretation guidance (AUROC near 0.5 vs. meaningfully above) is included
in the report itself — see Big Plan Phase 5.

## Everything above this line has been code-reviewed and unit-tested

Every module in `core/calibration/` has a matching test in `tests/`
(`test_static_observer_adapter.py`, `test_screen_annotation_parser.py`,
`test_correctness_judge.py`, `test_threshold_metrics.py`,
`test_ground_truth_alignment.py`, `test_run_calibration.py`,
`test_compute_calibration_report.py`) — all passing as of 2026-07-24, using
mocked LLM/image inputs where real API keys or the full image set weren't
available. The orchestration logic (`run_calibration.py`) has NOT been
exercised against real LLM calls end-to-end; run steps 1-3 above for real
before trusting the eventual `calibration_report.json` numbers.
