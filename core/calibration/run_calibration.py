"""End-to-end DSE calibration run — Phase 3 of the Big Plan.

For each sampled Screen Annotation screenshot:
  1. Extract widgets via the static-image Observer adapter (Phase 0,
     `core/calibration/static_observer.py`) — vision-only zero-shot LLM
     widget grounding (as of 2026-07-29; classical Canny+OCR still
     available via method="cv_ocr", see static_observer.py), no device, no
     XML refinement.
  2. Run ONE production call (T=0.1, same config the live Observer uses)
     to get the "best generation" per-widget description — Farquhar et al.
     2024's accuracy-assessment answer, NOT one of the M uncertainty
     samples.
  3. Run the EXISTING, unmodified M=10 DSE uncertainty sampling
     (`core/uncertainty/service.py` — same code path the live Observer
     uses) to get `raw_dse` per widget.
  4. Align each widget to its nearest Screen Annotation ground-truth
     element by IoU/center-distance (Phase 1's `ground_truth_alignment.py`).
     Widgets with no confident match are skipped, not guessed at.
  5. Run the correctness judge (Phase 2, `correctness_judge.py`) comparing
     the production description to the aligned ground truth.
  6. Persist one JSON per screen: `{screen_id, widgets: [{element_id,
     raw_dse, is_correct, ...}]}`.

Requires: real LLM API keys (via `shared/config.py` / `.env`, same as the
live workflow) and the Screen Annotation images already downloaded (see
`fetch_rico_images.py`). NOT runnable in the authoring sandbox — no API
keys, no full image set available there. This module is unit-tested with
mocked LLM/image inputs (`tests/test_run_calibration.py`) to verify wiring,
but has not been executed against real data end-to-end; that must happen in
the user's own environment. See
`Dokumen Kepake/DSE Calibration Experiment - Big Plan.md`.

Usage:
    python core/calibration/run_calibration.py \\
        --sample outputs/calibration/screen_annotation_sample_400.json \\
        --images outputs/calibration/rico_images \\
        --out-dir outputs/calibration/results
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from langchain_core.messages import convert_to_messages

from core.calibration.correctness_judge import CorrectnessJudge
from core.calibration.ground_truth_alignment import align_widget_to_ground_truth
from core.calibration.screen_annotation_parser import scale_bbox_to_pixels
from core.calibration.static_observer import build_static_observer, extract_widgets_from_image
from core.uncertainty.clusterer import EntailmentClusterer
from core.uncertainty.config import UncertaintyConfig
from core.uncertainty.request_builder import (
    HUMAN_TEMPLATE,
    OUTPUT_CONTRACT,
    ObserverSemanticRequestBuilder,
)
from core.uncertainty.semantic_parser import parse_semantic_map
from core.uncertainty.service import ObserverUncertaintyService
from core.utils.toons_helper import compress_and_report
from shared import config
from shared.prompts.observer_prompts import FEW_SHOT_EXAMPLES, SYSTEM_PROMPT
from shared.utils.llm_utils import encode_image

_SCREEN_DESC = "N/A (calibration: Screen Annotation sample, out-of-domain screen)"

# Real published rate for gemini-3.5-flash, checked 2026-07-27 against
# ai.google.dev/gemini-api/docs/pricing. Only accurate while OBSERVER_MODEL
# stays on this model — not looked up dynamically from the provider.
_PRICE_PER_M_INPUT = 1.50
_PRICE_PER_M_OUTPUT = 9.00


def _estimate_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (input_tokens / 1_000_000 * _PRICE_PER_M_INPUT
            + output_tokens / 1_000_000 * _PRICE_PER_M_OUTPUT)


class _MeteredLLM:
    """Transparent instrumentation wrapper around a real LLM client.

    Forwards every call unchanged (via __getattr__ passthrough for
    attributes, invoke() for calls) — does NOT alter any paper-exact
    algorithm behavior in core/uncertainty/. Just counts calls and, when the
    provider reports it on the response (`usage_metadata`), sums real
    input/output token counts so the CLI can print actual — not
    reconstructed-after-the-fact — per-screen cost.
    """

    def __init__(self, llm):
        self._llm = llm
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.tokens_unavailable = False

    def __getattr__(self, name):
        return getattr(self._llm, name)

    def invoke(self, *args, **kwargs):
        resp = self._llm.invoke(*args, **kwargs)
        self.calls += 1
        usage = getattr(resp, "usage_metadata", None)
        if isinstance(usage, dict):
            self.input_tokens += usage.get("input_tokens", 0) or 0
            self.output_tokens += usage.get("output_tokens", 0) or 0
        else:
            self.tokens_unavailable = True
        return resp


def _make_builder() -> ObserverSemanticRequestBuilder:
    return ObserverSemanticRequestBuilder(
        system_prompt=SYSTEM_PROMPT, few_shot=FEW_SHOT_EXAMPLES,
        human_template=HUMAN_TEMPLATE, output_contract=OUTPUT_CONTRACT,
    )


def _widgets_to_elements_json(widgets: list) -> str:
    return compress_and_report(
        [{"i": w["id"], "t": w.get("text") or "", "r": w.get("xml_role") or ""}
         for w in widgets],
        "elements", "observer",
    )


def process_screen(screen_id: str, image_path: str, ground_truth_elements: list,
                   llm, judge_llm, work_dir: str) -> dict:
    """Run steps 1-6 for one screenshot. `ground_truth_elements` is the
    sample's already-parsed `elements` list (bbox in dataset's native
    0-999 normalized [x1,y1,x2,y2] order — see `sample_screen_annotation.py`).

    Returns {"screen_id", "widgets": [...], "skipped_no_ground_truth_match",
    "skipped_parse_failure", "elapsed_seconds", "llm_calls", "input_tokens",
    "output_tokens", "cost_usd", "tokens_unavailable", "widgets_detected",
    "widgets_measured", "dse_min", "dse_max", "dse_avg"} — never raises for
    per-widget issues; only raises if the image itself can't be read or the
    LLM calls fail outright (those are real run-time errors the caller
    should surface, not swallow).
    """
    t_start = time.time()
    os.makedirs(work_dir, exist_ok=True)

    metered = _MeteredLLM(llm)
    judge_metered = metered if judge_llm is llm else _MeteredLLM(judge_llm)
    llm, judge_llm = metered, judge_metered

    # Detection now goes through the same metered LLM client as the DSE
    # sampling calls, so widgets_detected/cost_usd below reflect the real
    # total cost per screen INCLUDING the grounding call itself, not just
    # the M-sample uncertainty measurement.
    widgets = extract_widgets_from_image(image_path, work_dir, llm=llm, method="llm")

    observer = build_static_observer(llm=llm)
    annotated_path = os.path.join(work_dir, "annotated.png")
    observer.annotate_screenshot.invoke(
        {"image_path": image_path, "elements": widgets, "save_path": annotated_path}
    )

    import cv2
    img = cv2.imread(image_path)
    img_h, img_w = img.shape[:2]
    gt_px = [
        {"type": el["type"], "text": el["text"],
         "bbox": scale_bbox_to_pixels(el["bbox"], img_w, img_h) if el["bbox"] else None}
        for el in ground_truth_elements
    ]

    img_b64 = encode_image(annotated_path, max_height=480)
    elements_json = _widgets_to_elements_json(widgets)
    builder = _make_builder()
    built = builder.build(
        scenario_desc=_SCREEN_DESC, navigation_context="N/A",
        elements_json=elements_json, img_b64=img_b64,
    )
    messages = convert_to_messages(built)

    # Step 2: production "best generation" (T=0.1) — accuracy-assessment answer.
    prod_response = llm.invoke(messages, temperature=config.OBSERVER_TEMPERATURE)
    prod_content = getattr(prod_response, "content", prod_response)
    predicted_map = parse_semantic_map(prod_content)

    # Step 3: existing, unmodified M=10 DSE sampling.
    cfg = UncertaintyConfig(
        enabled=True, samples=config.OBSERVER_UNCERTAINTY_SAMPLES,
        temperature=config.OBSERVER_UNCERTAINTY_TEMPERATURE,
        provider=getattr(llm, "provider", "unknown"),
        model=getattr(llm, "model_name", "unknown"),
        judge_model=getattr(llm, "model_name", "unknown"),
        max_widgets=config.OBSERVER_UNCERTAINTY_MAX_WIDGETS,
    )
    svc = ObserverUncertaintyService(llm, EntailmentClusterer(llm), cfg, builder.prompt_hash)
    manifest = svc.measure(messages, widgets, _SCREEN_DESC, work_dir)
    dse_by_widget = {w["element_id"]: w["raw_dse"] for w in manifest["widgets"]
                     if "raw_dse" in w}

    judge = CorrectnessJudge(judge_llm)

    results = []
    skipped_no_match = 0
    skipped_parse_failure = 0
    for w in widgets:
        wid = w["id"]
        predicted = predicted_map.get(wid)
        raw_dse = dse_by_widget.get(wid)
        if predicted is None or raw_dse is None:
            skipped_parse_failure += 1
            continue
        match = align_widget_to_ground_truth(w["bounds"], gt_px)
        if match is None:
            skipped_no_match += 1
            continue
        cr = judge.judge(predicted, match["text"] or match["type"], _SCREEN_DESC)
        if cr.label == "unparseable":
            skipped_parse_failure += 1
            continue
        results.append({
            "element_id": wid,
            "raw_dse": raw_dse,
            "predicted_description": predicted,
            "ground_truth_type": match["type"],
            "ground_truth_text": match["text"],
            "correctness_label": cr.label,
            "is_correct": cr.is_correct,
            # Saved so a match can be re-verified later without re-running the
            # pipeline (both in the same pixel-space [x1,y1,x2,y2] convention).
            "widget_bounds_px": w["bounds"],
            "ground_truth_bounds_px": match["bbox"],
        })

    dse_values = list(dse_by_widget.values())
    input_tokens = metered.input_tokens + (judge_metered.input_tokens if judge_metered is not metered else 0)
    output_tokens = metered.output_tokens + (judge_metered.output_tokens if judge_metered is not metered else 0)
    llm_calls = metered.calls + (judge_metered.calls if judge_metered is not metered else 0)

    return {
        "screen_id": screen_id,
        "widgets": results,
        "skipped_no_ground_truth_match": skipped_no_match,
        "skipped_parse_failure": skipped_parse_failure,
        "elapsed_seconds": round(time.time() - t_start, 1),
        "llm_calls": llm_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(_estimate_cost_usd(input_tokens, output_tokens), 4),
        "tokens_unavailable": metered.tokens_unavailable,
        "widgets_detected": len(widgets),
        "widgets_measured": manifest.get("widgets_measured"),
        "dse_min": round(min(dse_values), 3) if dse_values else None,
        "dse_max": round(max(dse_values), 3) if dse_values else None,
        "dse_avg": round(sum(dse_values) / len(dse_values), 3) if dse_values else None,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sample", required=True)
    p.add_argument("--images", required=True, help="Dir of {screen_id}.jpg files")
    p.add_argument("--out-dir", required=True)
    args = p.parse_args()

    from core.utils.llm_factory import LLMFactory

    with open(args.sample, encoding="utf-8") as f:
        sample = json.load(f)

    os.makedirs(args.out_dir, exist_ok=True)
    llm = LLMFactory.create("observer")

    done = {fn[:-5] for fn in os.listdir(args.out_dir) if fn.endswith(".json")}
    todo = [s for s in sample["samples"] if s["screen_id"] not in done]
    todo_has_image = [os.path.exists(os.path.join(args.images, f"{s['screen_id']}.jpg")) for s in todo]
    available_count = sum(todo_has_image)
    print(f"[INFO] {len(sample['samples'])} total, {len(done)} already done, "
          f"{len(todo)} remaining ({available_count} have images downloaded, "
          f"{len(todo) - available_count} will be skipped for now).")
    print(f"[INFO] OBSERVER_UNCERTAINTY_SAMPLES={config.OBSERVER_UNCERTAINTY_SAMPLES}  "
          f"OBSERVER_UNCERTAINTY_MAX_WIDGETS={config.OBSERVER_UNCERTAINTY_MAX_WIDGETS}  "
          f"model={config.OBSERVER_MODEL}")

    run_start = time.time()
    processed = 0          # screens actually processed this invocation (not [SKIP]/[ERROR])
    total_cost = 0.0
    total_input_tokens = 0
    total_output_tokens = 0
    any_tokens_unavailable = False
    remaining_with_images = available_count

    for i, s in enumerate(todo):
        screen_id = s["screen_id"]
        image_path = os.path.join(args.images, f"{screen_id}.jpg")
        if not os.path.exists(image_path):
            print(f"[SKIP] {screen_id}: image not found at {image_path}")
            continue
        work_dir = os.path.join(args.out_dir, f"_work_{screen_id}")
        try:
            result = process_screen(screen_id, image_path, s["elements"], llm, llm, work_dir)
        except Exception as e:  # noqa: BLE001 — one bad screen must not kill a 400-item run
            print(f"[ERROR] {screen_id}: {e}")
            continue
        out_path = os.path.join(args.out_dir, f"{screen_id}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        processed += 1
        remaining_with_images -= 1
        total_cost += result["cost_usd"]
        total_input_tokens += result["input_tokens"]
        total_output_tokens += result["output_tokens"]
        any_tokens_unavailable = any_tokens_unavailable or result["tokens_unavailable"]

        correct = sum(1 for w in result["widgets"] if w["is_correct"])
        incorrect = len(result["widgets"]) - correct
        dse_range = (f"{result['dse_min']:.2f}-{result['dse_max']:.2f} "
                     f"(avg {result['dse_avg']:.2f})" if result["dse_min"] is not None else "n/a")

        # ETA is based only on screens that actually have an image downloaded —
        # todo may still contain entries with no image on disk yet, and those
        # get skipped near-instantly, so counting them here would inflate the
        # estimate (this is what happened before this fix).
        elapsed_run = time.time() - run_start
        avg_per_screen = elapsed_run / processed
        eta_seconds = avg_per_screen * remaining_with_images
        eta_finish = datetime.now() + timedelta(seconds=eta_seconds)
        proj_total_cost = total_cost / processed * available_count

        print(f"[{i + 1}/{len(todo)}] screen {screen_id} — done in {result['elapsed_seconds']}s")
        print(f"    widgets: {result['widgets_detected']} detected, "
              f"{result['widgets_measured']} measured, "
              f"{len(result['widgets'])} judged, "
              f"{result['skipped_no_ground_truth_match']} unmatched, "
              f"{result['skipped_parse_failure']} parse-fail")
        print(f"    correctness: {correct} correct / {incorrect} incorrect   "
              f"raw_dse range: {dse_range}")
        cost_note = " (token usage not reported by provider — cost is $0.0000)" \
            if result["tokens_unavailable"] and result["input_tokens"] == 0 else ""
        print(f"    tokens: {result['input_tokens']:,} in / {result['output_tokens']:,} out "
              f"({result['llm_calls']} calls) -> ${result['cost_usd']:.4f}{cost_note}  "
              f"running total: ${total_cost:.2f} over {processed} screens")
        print(f"    pace: avg {avg_per_screen:.1f}s/screen  ->  ETA for remaining "
              f"{remaining_with_images} (with images available): {eta_seconds / 3600:.1f}h "
              f"(finish ~{eta_finish.strftime('%Y-%m-%d %H:%M')})  "
              f"projected total cost for this run: ${proj_total_cost:.2f}")

    if any_tokens_unavailable and total_input_tokens == 0:
        print("[NOTE] This provider never reported token usage on any response, so all "
              "cost figures above are $0.00 — not evidence of free usage, just missing "
              "usage_metadata. Check your Google AI Studio / Cloud billing console for the "
              "real number.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
