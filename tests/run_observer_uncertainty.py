"""Standalone Observer DSE uncertainty runner.

Modes:
  --self-test                          offline; injected samples + MockClusterer
  --step-dir DIR                       real sampling from an existing step's artifacts
  --image IMG --elements JSON [--output-dir OUT]   real sampling from explicit inputs

Uses the SAME production ObserverUncertaintyService and ObserverSemanticRequestBuilder
as agents/observer_agent.py — one source of truth. Never prints secrets. Always shows
that prompt/temperature/sample-count/threshold are NOT validated.
"""
import argparse
import json
import os
import sys
import tempfile

# Repo root must precede site-packages so `import tests.*` (e.g. mock_clusterer)
# resolves to this project's tests package rather than any installed package
# that also exposes a top-level `tests` package.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
sys.path.append(".")
from core.uncertainty.config import UncertaintyConfig
from core.uncertainty.request_builder import (
    HUMAN_TEMPLATE,
    OUTPUT_CONTRACT,
    ObserverSemanticRequestBuilder,
)
from core.uncertainty.service import ObserverUncertaintyService
from shared.prompts.observer_prompts import FEW_SHOT_EXAMPLES, SYSTEM_PROMPT

_DISCLAIMER = (
    "[NOTE] Phase-1 measurement only. Prompt, temperature, sample count, and "
    "threshold are NOT validated. threshold=null, calibration_status=not_calibrated."
)


def _make_builder():
    return ObserverSemanticRequestBuilder(
        system_prompt=SYSTEM_PROMPT, few_shot=FEW_SHOT_EXAMPLES,
        human_template=HUMAN_TEMPLATE, output_contract=OUTPUT_CONTRACT,
    )


def run_self_test() -> int:
    from tests.mock_clusterer import MockClusterer

    print(_DISCLAIMER)
    widgets = [{"id": 1, "text": "Login", "xml_role": "button"}]
    cfg = UncertaintyConfig(enabled=True, samples=5, temperature=1.0,
                            provider="selftest", model="mock", judge_model="mock")
    svc = ObserverUncertaintyService(llm=None, clusterer=MockClusterer(),
                                     cfg=cfg, prompt_hash="selftest")

    cases = [
        (["[1]: Button - Login"] * 5, 0.0, 0.0, "ok"),
        ((["[1]: A - x"] * 3) + (["[1]: B - y"] * 2), 0.6730116670, 0.4181656601, "ok"),
        ([f"[1]: C{i} - z{i}" for i in range(5)], None, 1.0, "ok"),
    ]
    ok = True
    case_labels = [
        "all 5 samples identical (expect zero entropy)",
        "3-vs-2 split across two clusters (expect partial entropy)",
        "5 samples, all distinct (expect max normalized entropy)",
    ]
    with tempfile.TemporaryDirectory() as d:
        for i, (samples, exp_raw, exp_norm, exp_status) in enumerate(cases):
            m = svc.measure_from_samples(samples, widgets, "Login screen",
                                         os.path.join(d, str(i)))
            w = m["widgets"][0]
            case_ok = True
            if exp_raw is not None and abs(w["raw_dse"] - exp_raw) > 1e-6:
                print(f"[FAIL] case {i}: raw_dse={w['raw_dse']} exp={exp_raw}"); ok = False; case_ok = False
            if abs(w["normalized_dse"] - exp_norm) > 1e-6:
                print(f"[FAIL] case {i}: norm={w['normalized_dse']} exp={exp_norm}"); ok = False; case_ok = False
            if w["measurement_status"] != exp_status:
                print(f"[FAIL] case {i}: status={w['measurement_status']}"); ok = False; case_ok = False
            if w["threshold"] is not None or m["threshold"] is not None:
                print(f"[FAIL] case {i}: threshold not null"); ok = False; case_ok = False
            blob = json.dumps(m).lower()
            if any(b in blob for b in ("accepted", "rejected", '"pass"', '"fail"')):
                print(f"[FAIL] case {i}: decision word present"); ok = False; case_ok = False
            status_tag = "OK" if case_ok else "FAIL"
            print(f"[{status_tag}] case {i} ({case_labels[i]}): "
                  f"raw_dse={w['raw_dse']:.6f} normalized_dse={w['normalized_dse']:.6f} "
                  f"clusters={len(w['clusters'])} status={w['measurement_status']}")

    print("[OK] self-test passed" if ok else "[FAIL] self-test failed")
    return 0 if ok else 1


def _load_context(step_dir):
    ctx = {"scenario_desc": "N/A", "navigation_context": "N/A"}
    for name in ("core.json",):
        p = os.path.join(step_dir, "..", "..", "memory", name)
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                ctx["scenario_desc"] = data.get("scenario_desc", "N/A")
                ctx["navigation_context"] = data.get("navigation_context", "N/A")
            except Exception:
                pass
    return ctx


def run_real(args) -> int:
    print(_DISCLAIMER)
    from core.utils.llm_factory import LLMFactory
    from core.uncertainty.clusterer import EntailmentClusterer
    from shared.utils.llm_utils import encode_image
    from shared import config

    if args.step_dir:
        image = os.path.join(args.step_dir, "annotated.png")
        elements = os.path.join(args.step_dir, "merged.json")
        out_dir = args.output_dir or args.step_dir
        ctx = _load_context(args.step_dir)
    else:
        image, elements = args.image, args.elements
        out_dir = args.output_dir or tempfile.mkdtemp(prefix="uncertainty_")
        ctx = {"scenario_desc": "N/A", "navigation_context": "N/A"}

    for path, label in ((image, "image"), (elements, "elements")):
        if not path or not os.path.exists(path):
            print(f"[ERROR] missing {label}: {path}")
            return 2

    with open(elements, encoding="utf-8") as f:
        widgets = json.load(f)
    img_b64 = encode_image(image, 480)
    elements_json = json.dumps(
        [{"i": w["id"], "t": w.get("text") or "", "r": w.get("xml_role") or ""}
         for w in widgets], ensure_ascii=False,
    )

    llm = LLMFactory.create("observer")
    builder = _make_builder()
    from langchain_core.messages import convert_to_messages
    # convert_to_messages does not re-template already-resolved content (unlike
    # ChatPromptTemplate.from_messages().format_messages(), which chokes on the
    # literal braces in JSON elements_json/general_knowledge text).
    messages = convert_to_messages(
        builder.build(ctx["scenario_desc"], ctx["navigation_context"],
                      elements_json, img_b64)
    )

    cfg = UncertaintyConfig(
        enabled=True, samples=config.OBSERVER_UNCERTAINTY_SAMPLES,
        temperature=config.OBSERVER_UNCERTAINTY_TEMPERATURE,
        provider=getattr(llm, "provider", "unknown"),
        model=getattr(llm, "model_name", "unknown"),
        judge_model=getattr(llm, "model_name", "unknown"),
    )
    svc = ObserverUncertaintyService(llm, EntailmentClusterer(llm), cfg, builder.prompt_hash)
    manifest = svc.measure(messages, widgets, ctx["scenario_desc"], out_dir)
    print(f"[OK] artifacts written to {manifest.get('uncertainty_dir')}")
    for w in manifest["widgets"]:
        print(f"  id={w['element_id']} norm_dse={w['normalized_dse']:.4f} "
              f"status={w['measurement_status']} eff_M={w['effective_sample_count']}")
    return 0


def main():
    p = argparse.ArgumentParser(description="Observer DSE uncertainty runner (Phase 1)")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--step-dir")
    p.add_argument("--image")
    p.add_argument("--elements")
    p.add_argument("--output-dir")
    args = p.parse_args()

    if args.self_test:
        return run_self_test()
    if args.step_dir or (args.image and args.elements):
        return run_real(args)
    p.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
