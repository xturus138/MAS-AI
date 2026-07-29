"""Static-image adapter for the Observer's widget-detection pipeline.

Lets the Observer's widget detector run against an arbitrary image file
(e.g. a Screen Annotation screenshot) with no live ADB device involved.
Built for the DSE calibration experiment (see `Dokumen Kepake/DSE
Calibration Experiment - Big Plan.md`, Phase 0) — NOT used by the live
predefined/autonomous test workflow, which still goes through the full
`ObserverAgent.analyze()` against a real device.

As of 2026-07-29 this defaults to the same zero-shot LLM widget-grounding
call the live pipeline uses (`ObserverAgent._detect_widgets_via_llm`),
replacing the earlier Canny+OCR-only path — see
`Dokumen Kepake/memory/thesis_vlm_grounding_alternative.md` for validation
numbers. The classical Canny+OCR path (`_run_canny_pipeline`) is kept and
still reachable via `method="cv_ocr"` for comparison/rollback.

Why this is safe: `ObserverTools.ocr_extract_text`, `.detect_visual_elements`,
and `.annotate_screenshot` (tools/observer_tools.py) only ever take an
`image_path` — they never touch the `IDeviceClient` session. Only
`take_screenshot`, `check_keyboard_state`, and `dump_hierarchy` are
device-bound, and this module never calls them: a static, externally-sourced
screenshot has no live keyboard state and no uiautomator XML hierarchy to
dump, so there is nothing for XML refinement to refine against. Widgets here
are vision-only, matching `ObserverAgent.analyze()`'s pre-XML-refinement
state.

Reuses `ObserverAgent._detect_widgets_via_llm` / `._run_canny_pipeline`
directly (rather than reimplementing detection logic) so this adapter can
never drift from the live pipeline's widget-detection behaviour.
"""
import os

import cv2

from agents.observer_agent import ObserverAgent
from tools.observer_tools import ObserverTools


def build_static_observer(llm=None) -> ObserverAgent:
    """An ObserverAgent instance usable for widget extraction only (no
    device, no memory/logger/monitor). Do not call `.analyze()` on it —
    that method assumes a live device end-to-end. Only the private
    `_detect_widgets_via_llm` / `_run_canny_pipeline` / `_merge_and_filter`
    helpers are safe to call.

    `llm` is required for `method="llm"` (the default in
    `extract_widgets_from_image`) since that path makes a real LLM call for
    detection itself, not just the downstream semantic-interpretation step.
    Pass `llm=None` only if you will exclusively use `method="cv_ocr"`.
    """
    tools = ObserverTools(device_session=None).get_tools()
    return ObserverAgent(llm=llm, tools=tools, memory=None, logger=None, monitor=None)


def extract_widgets_from_image(
    image_path: str, work_dir: str, llm=None, method: str = "llm"
) -> list:
    """Run the Observer's widget detector on a static image (vision-only, no
    XML refinement). Returns the same widget-dict schema as the live
    pipeline's `merged.json` (id, bounds, cv_bounds, text, type, class,
    resource_id), minus any XML-sourced fields (`source` here means the
    detector, not an XML match — `xml_label`/`xml_role`/`xml_actionable`
    never appear) since there is no device hierarchy dump for an
    externally-sourced screenshot.

    `method`: "llm" (default) — zero-shot VLM grounding, requires `llm`.
              "cv_ocr" — classical Canny+region+OCR pipeline, no LLM needed.

    Raises ValueError if the image can't be read. Raises whatever the LLM
    client raises if `method="llm"` and the call fails after retries — this
    function does NOT silently fall back to cv_ocr (unlike the live
    `ObserverAgent.analyze()`), because a calibration run should surface a
    real API failure rather than quietly mix detection methods within one
    experiment run.
    """
    os.makedirs(work_dir, exist_ok=True)

    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")
    image_height, image_width = img.shape[:2]

    observer = build_static_observer(llm=llm)

    if method == "llm":
        if llm is None:
            raise ValueError('extract_widgets_from_image(method="llm") requires an llm')
        return observer._detect_widgets_via_llm(image_path, image_width, image_height)

    if method == "cv_ocr":
        ocr_path = os.path.join(work_dir, "ocr.json")
        cv_path = os.path.join(work_dir, "cv.json")
        return observer._run_canny_pipeline(
            raw_path=image_path,
            ocr_path=ocr_path,
            cv_path=cv_path,
            image_height=image_height,
            is_kb_shown=False,
        )

    raise ValueError(f"Unknown method: {method!r} (expected 'llm' or 'cv_ocr')")
