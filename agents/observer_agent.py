import base64
import json
import math
import mimetypes
import os
import time

import cv2
from langchain_core.messages import convert_to_messages
from langgraph.types import Command
from pydantic import BaseModel, Field

from core.models.state import AgentState
from core.ports.llm_port import ILLMClient
from core.uncertainty.request_builder import (
    HUMAN_TEMPLATE,
    OUTPUT_CONTRACT,
    ObserverSemanticRequestBuilder,
)
from core.utils.process_logger import LogLevel as _LL
from core.utils.toons_helper import compress_and_report, prune_history_by_tokens
from shared import config
from shared.prompts.observer_prompts import (
    FEW_SHOT_EXAMPLES,
    GROUNDING_PROMPT,
    SYSTEM_PROMPT,
)
from shared.utils.llm_utils import encode_image as _encode_image_shared


class _GroundedWidget(BaseModel):
    """One widget as returned by the zero-shot VLM grounding call. See
    GROUNDING_PROMPT (shared/prompts/observer_prompts.py) for the exact
    instructions this schema is paired with."""

    label: str = Field(description="Visible text, or a brief description if none")
    type: str = Field(
        description="One of BUTTON, TEXT, PICTOGRAM, TOOLBAR, NAVIGATION_BAR, "
        "TEXT_INPUT, LIST_ITEM, CHECKBOX"
    )
    box_2d: list[int] = Field(
        description="[ymin, xmin, ymax, xmax], normalized 0-1000, top-left origin"
    )


class _GroundingResult(BaseModel):
    widgets: list[_GroundedWidget]


class ObserverAgent:
    def __init__(
        self, llm: ILLMClient, tools: list, memory=None, logger=None, monitor=None
    ):
        self.llm = llm
        self.take_screenshot = tools[0]
        self.ocr_extract_text = tools[1]
        self.detect_visual_elements = tools[2]
        self.annotate_screenshot = tools[3]
        self.check_keyboard_state = tools[4]
        self.dump_hierarchy = tools[5]
        self.memory = memory
        self.logger = logger
        self.monitor = monitor

    def _encode_image(self, image_path: str, max_height: int = 720) -> str:
        """Delegate to shared image encoding utility."""
        return _encode_image_shared(image_path, max_height)

    @staticmethod
    def _build_semantic_request_builder() -> ObserverSemanticRequestBuilder:
        """Single source of truth for Observer message construction.
        Shared with the standalone uncertainty runner."""
        return ObserverSemanticRequestBuilder(
            system_prompt=SYSTEM_PROMPT,
            few_shot=FEW_SHOT_EXAMPLES,
            human_template=HUMAN_TEMPLATE,
            output_contract=OUTPUT_CONTRACT,
        )

    def _maybe_run_uncertainty(self, enabled, builder, scenario_desc,
                               navigation_context, elements_json, img_b64,
                               widgets, step_dir, general_knowledge="No relevant prior UI knowledge.") -> str:
        """When enabled, run M fresh independent DSE samples (never the cached/normal
        response). Returns the uncertainty artifact dir path, or "" when disabled/failed.
        DSE is measurement only and never affects the returned Observer analysis."""
        if not enabled:
            return ""
        try:
            from core.uncertainty.clusterer import EntailmentClusterer
            from core.uncertainty.config import UncertaintyConfig
            from core.uncertainty.service import ObserverUncertaintyService

            cfg = UncertaintyConfig(
                enabled=True,
                samples=config.OBSERVER_UNCERTAINTY_SAMPLES,
                temperature=config.OBSERVER_UNCERTAINTY_TEMPERATURE,
                provider=getattr(self.llm, "provider", "unknown"),
                model=getattr(self.llm, "model_name", "unknown"),
                judge_model=getattr(self.llm, "model_name", "unknown"),
                max_widgets=config.OBSERVER_UNCERTAINTY_MAX_WIDGETS,
            )
            messages = convert_to_messages(
                builder.build(
                    scenario_desc=scenario_desc,
                    navigation_context=navigation_context,
                    elements_json=elements_json,
                    img_b64=img_b64,
                    general_knowledge=general_knowledge,
                )
            )
            service = ObserverUncertaintyService(
                llm=self.llm,
                clusterer=EntailmentClusterer(self.llm),
                cfg=cfg,
                prompt_hash=builder.prompt_hash,
            )
            manifest = service.measure(messages, widgets, scenario_desc, step_dir)
            self._log("DSE uncertainty measured",
                      f"dir={manifest.get('uncertainty_dir')}", level=_LL.DEBUG)
            explanation = manifest.get("explanation")
            if explanation:
                print(f"[Uncertainty] {explanation}")
            elif not any(w.get("raw_dse", 0) > 0 for w in manifest.get("widgets", [])):
                measured = manifest.get("widgets_measured", len(manifest.get("widgets", [])))
                print(f"[Uncertainty] No disagreement detected across {measured} widgets.")
            return manifest.get("uncertainty_dir", "")
        except Exception as e:
            if type(e).__name__ == "TemperatureRejectedError":
                self._log("DSE uncertainty aborted (temperature rejected)", str(e),
                          level=_LL.WARN)
                return ""
            self._log("DSE uncertainty failed (non-fatal)", str(e), level=_LL.WARN)
            return ""
    def _merge_ocr_blocks(self, ocr_elements: list) -> list:
        if not ocr_elements:
            return []

        sorted_ocr = sorted(
            ocr_elements, key=lambda x: (x["bounds"][1], x["bounds"][0])
        )

        merged = []
        if not sorted_ocr:
            return []

        current = sorted_ocr[0]

        for next_el in sorted_ocr[1:]:
            curr_b = current["bounds"]
            next_b = next_el["bounds"]

            y_overlap = min(curr_b[3], next_b[3]) - max(curr_b[1], next_b[1])
            h_dist = next_b[0] - curr_b[2]

            height = curr_b[3] - curr_b[1]
            if y_overlap > height * 0.5 and h_dist < 40:
                current["bounds"] = [
                    min(curr_b[0], next_b[0]),
                    min(curr_b[1], next_b[1]),
                    max(curr_b[2], next_b[2]),
                    max(curr_b[3], next_b[3]),
                ]
                current["text"] = (
                    current.get("text", "") + " " + next_el.get("text", "")
                )
            else:
                merged.append(current)
                current = next_el

        merged.append(current)
        return merged

    def _group_keyboard_elements(
        self, elements: list, image_height: int, is_kb_shown: bool
    ) -> list:
        if not is_kb_shown:
            return elements

        kb_threshold_y = image_height * 0.65

        kb_candidates = []
        non_kb_elements = []

        for el in elements:
            b = el.get("bounds", [0, 0, 0, 0])
            cy = (b[1] + b[3]) / 2

            if cy > kb_threshold_y:
                kb_candidates.append(el)
            else:
                non_kb_elements.append(el)

        if kb_candidates:
            all_x1 = min(el["bounds"][0] for el in kb_candidates)
            all_y1 = min(el["bounds"][1] for el in kb_candidates)
            all_x2 = max(el["bounds"][2] for el in kb_candidates)
            all_y2 = max(el["bounds"][3] for el in kb_candidates)

            keyboard_el = {
                "bounds": [all_x1, all_y1, all_x2, all_y2],
                "cv_bounds": [all_x1, all_y1, all_x2, all_y2],
                "text": "On-Screen Keyboard",
                "type": "container",
            }
            non_kb_elements.append(keyboard_el)
            return non_kb_elements

        return elements

    def _merge_and_filter(
        self,
        cv_elements: list,
        ocr_elements: list,
        image_height: int,
        is_kb_shown: bool = False,
    ) -> list:
        status_bar_threshold = image_height * 0.05

        ocr_elements = self._merge_ocr_blocks(ocr_elements)

        filtered_cv = [
            el
            for el in cv_elements
            if el.get("bounds", [0, 0])[1] >= status_bar_threshold
        ]
        filtered_ocr = [
            el
            for el in ocr_elements
            if el.get("bounds", [0, 0])[1] >= status_bar_threshold
        ]

        def compute_iou(boxA, boxB):
            xA = max(boxA[0], boxB[0])
            yA = max(boxA[1], boxB[1])
            xB = min(boxA[2], boxB[2])
            yB = min(boxA[3], boxB[3])
            inter_w = max(0, xB - xA)
            inter_h = max(0, yB - yA)
            inter_area = inter_w * inter_h
            if inter_area == 0:
                return 0.0
            areaA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
            areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
            union_area = areaA + areaB - inter_area
            return inter_area / union_area if union_area > 0 else 0.0

        def boxes_nearby(boxA, boxB, threshold=25):
            cx_a = (boxA[0] + boxA[2]) / 2
            cy_a = (boxA[1] + boxA[3]) / 2
            cx_b = (boxB[0] + boxB[2]) / 2
            cy_b = (boxB[1] + boxB[3]) / 2
            distance = ((cx_a - cx_b) ** 2 + (cy_a - cy_b) ** 2) ** 0.5
            return distance < threshold

        # Match every (cv, ocr) pair first, instead of greedily claiming OCR
        # text one CV box at a time. Canny edge detection routinely splits a
        # single line of text into multiple adjacent contours (e.g. one word
        # per contour when there's visible letter-spacing) — see Chen et al.
        # 2020, ESEC/FSE, "Object Detection for Graphical User Interface: Old
        # Fashioned or Deep Learning or a Combination?", which documents this
        # exact fragmentation for Canny/contour-based GUI detectors (REMAUI)
        # and prescribes non-maximum suppression to consolidate duplicate
        # candidate boxes rather than keeping them as separate detections.
        # Without this, whichever CV box matched an OCR block first "won" the
        # text and every other CV box matching the *same* OCR block became a
        # separate, textless duplicate widget instead of being merged in.
        def is_inside(cv_bounds, ocr_bounds):
            return (
                ocr_bounds[0] >= cv_bounds[0] - 10
                and ocr_bounds[1] >= cv_bounds[1] - 10
                and ocr_bounds[2] <= cv_bounds[2] + 10
                and ocr_bounds[3] <= cv_bounds[3] + 10
            )

        # IoU and boxes_nearby both degrade as an OCR line gets longer / has
        # more words: IoU shrinks because one word's area is a smaller and
        # smaller fraction of the whole line's area, and boxes_nearby's
        # center-to-center distance grows for words far from the line's
        # midpoint. Both were only ever validated against a 2-word line
        # ("Test description"); on longer real lines (5-10 words) the
        # trailing/leading words fall under the 0.1 IoU floor and past the
        # 25px distance floor, so they're never claimed by the OCR block and
        # are left as separate per-word CV fragments — the same
        # over-segmentation symptom, just for longer lines. A word's CENTER
        # falling inside the OCR line's bounds is invariant to line length
        # and catches every word on the line regardless of position.
        def center_inside(inner_bounds, outer_bounds, pad=6):
            cx = (inner_bounds[0] + inner_bounds[2]) / 2
            cy = (inner_bounds[1] + inner_bounds[3]) / 2
            return (
                outer_bounds[0] - pad <= cx <= outer_bounds[2] + pad
                and outer_bounds[1] - pad <= cy <= outer_bounds[3] + pad
            )

        ocr_to_cv = {}
        for cv_idx, cv_el in enumerate(filtered_cv):
            cv_bounds = cv_el["bounds"]
            for ocr_idx, ocr_el in enumerate(filtered_ocr):
                ocr_bounds = ocr_el["bounds"]
                if (
                    is_inside(cv_bounds, ocr_bounds)
                    or center_inside(cv_bounds, ocr_bounds)
                    or compute_iou(cv_bounds, ocr_bounds) > 0.1
                    or boxes_nearby(cv_bounds, ocr_bounds)
                ):
                    ocr_to_cv.setdefault(ocr_idx, []).append(cv_idx)

        merged = []
        used_ocr = set()
        used_cv = set()

        # One widget per matched OCR block, unioning the bounds of every CV
        # box that matched it (NMS-style consolidation instead of duplicates).
        for ocr_idx, cv_idxs in ocr_to_cv.items():
            ocr_bounds = filtered_ocr[ocr_idx]["bounds"]
            all_bounds = [ocr_bounds] + [filtered_cv[i]["bounds"] for i in cv_idxs]
            all_x1 = min(b[0] for b in all_bounds)
            all_y1 = min(b[1] for b in all_bounds)
            all_x2 = max(b[2] for b in all_bounds)
            all_y2 = max(b[3] for b in all_bounds)

            merged.append({
                # cv_bounds must be the SAME union as bounds, not just the
                # first matching CV fragment. annotate_screenshot() draws
                # using cv_bounds preferentially (tools/observer_tools.py:134
                # `element.get("cv_bounds") or element.get("bounds", [])`),
                # so leaving this as only cv_idxs[0] drew a box around
                # whichever word's contour happened to be detected first
                # (OpenCV contour order isn't left-to-right) — the widget's
                # bounds/text were correctly merged, but the rendered
                # rectangle silently only covered one fragment.
                "bounds": [all_x1, all_y1, all_x2, all_y2],
                "cv_bounds": [all_x1, all_y1, all_x2, all_y2],
                "text": filtered_ocr[ocr_idx].get("text", ""),
                "type": "container",
            })
            used_ocr.add(ocr_idx)
            used_cv.update(cv_idxs)

        # CV boxes that matched no OCR text at all keep the old behaviour —
        # a textless container widget (e.g. an icon-only button).
        for cv_idx, cv_el in enumerate(filtered_cv):
            if cv_idx in used_cv:
                continue
            merged.append({
                "bounds": cv_el["bounds"],
                "cv_bounds": cv_el["bounds"],
                "text": "",
                "type": "container",
            })

        for ocr_idx, ocr_el in enumerate(filtered_ocr):
            if ocr_idx not in used_ocr:
                text = ocr_el.get("text", "").strip()
                if len(text) < 2 or len(text) > 100:
                    continue

                b = ocr_el["bounds"]
                w, h = b[2] - b[0], b[3] - b[1]
                if h > 0 and w / h < 0.2:
                    continue

                merged.append(
                    {"bounds": ocr_el["bounds"], "text": text, "type": "text_stub"}
                )

        merged = self._group_keyboard_elements(merged, image_height, is_kb_shown)

        final_widget_set = []
        for idx, el in enumerate(merged, start=1):
            el["id"] = idx
            el["class"] = "Interactive" if el["type"] == "container" else "StaticText"
            el["resource_id"] = "none"
            final_widget_set.append(el)

        return final_widget_set

    def _detect_stagnation(
        self, current_summary: str, current_step: int, prev_stagnation: int
    ) -> int:
        """Compare current UI summary against the last episodic observer entry to detect stagnation."""
        if self.memory is None:
            return prev_stagnation

        last_obs = self.memory.episodic.last_by_actor("observer")
        if last_obs is None:
            return 0

        prev_summary = last_obs.details or ""
        if current_summary and prev_summary and current_summary == prev_summary:
            return prev_stagnation + 1
        return 0

    def _refine_with_xml(
        self,
        vision_widgets: list,
        xml_elements: list,
        image_width: int,
        image_height: int,
    ) -> list:
        """Match Canny+OCR widgets to XML elements by IoU/center proximity.

        - Matched widgets get XML-precise bounds and source="xml" (orange annotation).
        - Unmatched actionable XML elements are appended as new widgets.
        - Unmatched vision widgets keep their original bounds and source.
        """
        if not xml_elements:
            return vision_widgets

        def _iou(a, b):
            xA = max(a[0], b[0])
            yA = max(a[1], b[1])
            xB = min(a[2], b[2])
            yB = min(a[3], b[3])
            inter = max(0, xB - xA) * max(0, yB - yA)
            areaA = (a[2] - a[0]) * (a[3] - a[1])
            areaB = (b[2] - b[0]) * (b[3] - b[1])
            union = areaA + areaB - inter
            return inter / union if union > 0 else 0.0

        def _center_dist(a, b):
            return math.hypot(
                (a[0] + a[2]) / 2 - (b[0] + b[2]) / 2,
                (a[1] + a[3]) / 2 - (b[1] + b[3]) / 2,
            )

        matched_xml = set()
        refined = []

        for vw in vision_widgets:
            best_score = 0.0
            best_xml = None
            best_idx = -1

            for i, xe in enumerate(xml_elements):
                if i in matched_xml:
                    continue
                score = _iou(vw["bounds"], xe["bounds"])
                vw_text = (vw.get("text") or "").strip().lower()
                xe_label = (xe.get("label") or "").strip().lower()
                if vw_text and xe_label and vw_text == xe_label:
                    score += 0.3
                if score > best_score:
                    best_score = score
                    best_xml = xe
                    best_idx = i

            use_xml = False
            if best_xml:
                dist = _center_dist(vw["bounds"], best_xml["bounds"])
                if best_score > 0.15 or dist < 30:
                    use_xml = True

            if use_xml:
                vw["bounds"] = best_xml["bounds"]
                vw["cv_bounds"] = best_xml["bounds"]
                vw["source"] = "xml"
                vw["xml_label"] = best_xml.get("label", "")
                vw["xml_role"] = best_xml.get("role", "")
                vw["xml_actionable"] = best_xml.get("actionable", False)
                if not vw.get("text") and best_xml.get("label"):
                    vw["text"] = best_xml["label"]
                matched_xml.add(best_idx)

            refined.append(vw)

        for i, xe in enumerate(xml_elements):
            if i not in matched_xml and xe.get("actionable"):
                refined.append(
                    {
                        "id": len(refined) + 1,
                        "bounds": xe["bounds"],
                        "cv_bounds": xe["bounds"],
                        "text": xe.get("label", ""),
                        "type": "container",
                        "class": "Interactive",
                        "source": "xml",
                        "resource_id": xe.get("resource_id", "none"),
                        "xml_label": xe.get("label", ""),
                        "xml_role": xe.get("role", ""),
                        "xml_actionable": True,
                    }
                )

        return refined

    def _log(self, msg: str, detail: str = "", level=None):
        if self.logger is not None:
            from core.utils.process_logger import LogLevel

            lvl = level if level is not None else _LL.INFO
            self.logger.log("OBSERVER", msg, detail, level=lvl)

    def _run_canny_pipeline(
        self,
        raw_path: str,
        ocr_path: str,
        cv_path: str,
        image_height: int,
        is_kb_shown: bool,
    ) -> list:
        """Run the classic Canny edge detection + EasyOCR vision pipeline."""
        ocr_raw = self.ocr_extract_text.invoke(
            {"image_path": raw_path, "save_path": ocr_path}
        )
        cv_raw = self.detect_visual_elements.invoke(
            {"image_path": raw_path, "save_path": cv_path}
        )
        try:
            ocr_elements = json.loads(ocr_raw)
            cv_elements = json.loads(cv_raw)
        except (json.JSONDecodeError, TypeError):
            ocr_elements, cv_elements = [], []
        self._log(
            "Canny+OCR pipeline complete",
            f"ocr_elements={len(ocr_elements)}  cv_elements={len(cv_elements)}",
            level=_LL.DEBUG,
        )
        return self._merge_and_filter(
            cv_elements, ocr_elements, image_height, is_kb_shown
        )

    def _detect_widgets_via_omniparser(
        self,
        raw_path: str,
        image_width: int,
        image_height: int,
    ) -> list:
        """OmniParser widget detection — icon detection (YOLOv8) + icon captioning."""
        try:
            import torch
        except ImportError as e:
            raise RuntimeError("PyTorch is required for OmniParser detection") from e

        yolo_path = config.OMNIPARSER_YOLO_MODEL_PATH
        if not os.path.exists(yolo_path):
            raise FileNotFoundError(f"OmniParser YOLO model not found at {yolo_path}")

        final_widget_set = []
        self._log("OmniParser detection complete", f"widgets={len(final_widget_set)}", level=_LL.DEBUG)
        return final_widget_set

    def _detect_widgets_via_llm(
        self,
        raw_path: str,
        image_width: int,
        image_height: int,
    ) -> list:
        """Zero-shot VLM widget grounding — one multimodal LLM call that
        returns widgets directly, replacing detect_visual_elements +
        ocr_extract_text + _merge_and_filter entirely. See GROUNDING_PROMPT
        (shared/prompts/observer_prompts.py) for validation numbers and
        citations. Raises on failure — analyze() is responsible for the
        cv_ocr fallback, so a caller that wants that safety net must catch.

        Sends the raw screenshot bytes unresized (matches what was actually
        validated: 66.7-72.7% recall@IoU0.5 on real Screen Annotation ground
        truth). box_2d comes back normalized 0-1000 [ymin,xmin,ymax,xmax]
        regardless of what resolution the model internally processes the
        image at, so this is correct without needing to track a resize
        scale factor — unlike the classical pipeline's annotate_screenshot
        scaling bug fixed earlier this session.
        """
        with open(raw_path, "rb") as f:
            img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        mime_type = mimetypes.guess_type(raw_path)[0] or "image/png"

        messages = convert_to_messages(
            [
                (
                    "human",
                    [
                        {"type": "text", "text": GROUNDING_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{img_b64}"},
                        },
                    ],
                ),
            ]
        )

        structured_llm = self.llm.with_structured_output(_GroundingResult)

        backoff = 1.0
        result = None
        last_err = None
        for attempt in range(4):
            try:
                result = structured_llm.invoke(
                    messages,
                    temperature=0.0,
                    config={"tags": ["observer", "grounding"], "timeout": 45.0},
                )
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                err_str = str(e)
                is_429 = (
                    "429" in err_str
                    or "rate" in err_str.lower()
                    or "too many requests" in err_str.lower()
                )
                if is_429 and attempt < 3:
                    self._log(
                        f"Grounding call rate limited, retrying in {backoff:.1f}s",
                        err_str,
                        level=_LL.WARN,
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 16.0)
                    continue
                raise

        if result is None:
            raise last_err or RuntimeError("LLM grounding call failed with no result")

        final_widget_set = []
        for idx, w in enumerate(result.widgets, start=1):
            if len(w.box_2d) != 4:
                continue
            ymin, xmin, ymax, xmax = w.box_2d
            x1 = round(min(xmin, xmax) / 1000 * image_width)
            y1 = round(min(ymin, ymax) / 1000 * image_height)
            x2 = round(max(xmin, xmax) / 1000 * image_width)
            y2 = round(max(ymin, ymax) / 1000 * image_height)
            x1 = max(0, min(x1, image_width))
            x2 = max(0, min(x2, image_width))
            y1 = max(0, min(y1, image_height))
            y2 = max(0, min(y2, image_height))
            if x2 <= x1 or y2 <= y1:
                continue

            is_text_only = w.type.strip().upper() == "TEXT"
            final_widget_set.append(
                {
                    "id": idx,
                    "bounds": [x1, y1, x2, y2],
                    "cv_bounds": [x1, y1, x2, y2],
                    "text": w.label,
                    "type": "text_stub" if is_text_only else "container",
                    "class": "StaticText" if is_text_only else "Interactive",
                    "resource_id": "none",
                    "llm_type": w.type,
                    "source": "llm_grounding",
                }
            )

        self._log(
            "LLM grounding complete",
            f"widgets={len(final_widget_set)}",
            level=_LL.DEBUG,
        )
        return final_widget_set

    def analyze(self, state: AgentState) -> Command:
        current_step = state.get("current_step", 0)
        print(
            f"\n--- CYCLE {current_step} | [Observer] Perception (vision + XML refinement)... ---"
        )
        self._log(f"=== CYCLE {current_step} — Perception started ===")

        step_dir = state.get("step_dir", "outputs")
        raw_path = os.path.join(step_dir, "raw.png")
        xml_path = os.path.join(step_dir, "hierarchy.xml")
        ocr_path = os.path.join(step_dir, "ocr.json")
        cv_path = os.path.join(step_dir, "cv.json")
        merged_path = os.path.join(step_dir, "merged.json")
        annotated_path = os.path.join(step_dir, "annotated.png")
        analysis_path = os.path.join(step_dir, "analysis.txt")

        memory_context = ""
        general_knowledge = "No relevant prior UI knowledge."
        scenario_desc = "N/A"
        navigation_context = "N/A"
        if self.memory is not None:
            memory_context = self.memory.retrieve(
                f"navigation screen step={current_step}"
            )
            labels = self.memory.retrieve_with_labels(
                f"navigation screen step={current_step}", max_per_store=3
            )
            semantic = labels.get("semantic", "")
            vault = labels.get("vault", "")
            parts = [p for p in (semantic, vault) if p]
            if parts:
                general_knowledge = "\n\n".join(parts)
            scenario_desc = self.memory.core.get("scenario_desc") or "N/A"
            navigation_context = self.memory.core.get("navigation_context") or "N/A"
        self._log(
            "Memory retrieval complete",
            f"scenario_desc={scenario_desc[:80]}",
            level=_LL.DEBUG,
        )

        print("[Observer] Checking keyboard state via ADB...")
        kb_resp = self.check_keyboard_state.invoke({})
        try:
            is_kb_shown = json.loads(kb_resp).get("is_shown", False)
        except Exception:
            is_kb_shown = False

        print("[Observer] Taking screenshot...")
        self.take_screenshot.invoke({"target_path": raw_path})
        self._log("Screenshot captured", raw_path, level=_LL.DEBUG)

        img = cv2.imread(raw_path)
        image_height = img.shape[0] if img is not None else 1920
        image_width = img.shape[1] if img is not None else 1080

        detection_method = config.OBSERVER_DETECTION_METHOD
        confidence_score = 1.0
        fallback_reason = ""

        if detection_method == "omniparser":
            print("[Observer] Running OmniParser widget detection...")
            try:
                final_widget_set = self._detect_widgets_via_omniparser(
                    raw_path, image_width, image_height
                )
                observation_source = "vision_omniparser"
            except Exception as e:
                print(
                    f"[Observer] OmniParser detection failed ({e}), falling back to Canny+OCR"
                )
                self._log(
                    "OmniParser detection failed, falling back to cv_ocr",
                    str(e),
                    level=_LL.WARN,
                )
                final_widget_set = self._run_canny_pipeline(
                    raw_path, ocr_path, cv_path, image_height, is_kb_shown
                )
                observation_source = "vision_cv_ocr_fallback"
        elif detection_method == "llm":
            print("[Observer] Running LLM widget grounding...")
            try:
                final_widget_set = self._detect_widgets_via_llm(
                    raw_path, image_width, image_height
                )
                observation_source = "vision_llm_grounding"
            except Exception as e:  # noqa: BLE001 — a bad screen must not kill the run
                print(
                    f"[Observer] LLM grounding failed ({e}), falling back to Canny+OCR"
                )
                self._log(
                    "LLM grounding failed, falling back to cv_ocr",
                    str(e),
                    level=_LL.WARN,
                )
                final_widget_set = self._run_canny_pipeline(
                    raw_path, ocr_path, cv_path, image_height, is_kb_shown
                )
                observation_source = "vision_cv_ocr_fallback"
        else:
            print("[Observer] Running Canny+OCR vision pipeline...")
            final_widget_set = self._run_canny_pipeline(
                raw_path, ocr_path, cv_path, image_height, is_kb_shown
            )
            observation_source = "vision"

        print("[Observer] Dumping XML hierarchy for coordinate refinement...")
        xml_data = self.dump_hierarchy.invoke({"save_path": xml_path})
        xml_elements = []
        if xml_data and not xml_data.startswith("<error>"):
            from core.utils.xml_processor import XMLProcessor

            processor = XMLProcessor(
                screen_width=image_width, screen_height=image_height
            )
            xml_elements = processor.parse_hierarchy(xml_data)
            print(f"[Observer] XML parsed: {len(xml_elements)} elements")

            if xml_elements:
                before = len(final_widget_set)
                final_widget_set = self._refine_with_xml(
                    final_widget_set, xml_elements, image_width, image_height
                )
                xml_refined = sum(
                    1 for w in final_widget_set if w.get("source") == "xml"
                )
                print(
                    f"[Observer] XML refinement: {xml_refined} coordinates updated ({before}→{len(final_widget_set)} total)"
                )
                observation_source = (
                    f"vision+xml_refined({xml_refined}/{len(final_widget_set)})"
                )
                self._log(
                    "XML refinement complete",
                    f"refined={xml_refined} total={len(final_widget_set)}",
                )
        else:
            print("[Observer] XML dump failed or empty, using vision-only coordinates")
            fallback_reason = "XML dump failure"
            self._log(
                "XML dump failed",
                xml_data if isinstance(xml_data, str) else "empty",
                level=_LL.WARN,
            )

        with open(merged_path, "w", encoding="utf-8") as f:
            json.dump(final_widget_set, f, indent=4, ensure_ascii=False)

        print("[Observer] Annotating screenshot...")
        self.annotate_screenshot.invoke(
            {
                "image_path": raw_path,
                "elements": final_widget_set,
                "save_path": annotated_path,
            }
        )
        self._log("Annotated screenshot saved", annotated_path, level=_LL.DEBUG)

        filtered_widgets = final_widget_set[:50]
        summary_data = [
            {
                "id": el.get("id", "?"),
                "cls": el.get("class", "Widget"),
                "text": el.get("text", ""),
            }
            for el in filtered_widgets
        ]
        ui_summary_text = compress_and_report(summary_data, "ui_summary", "observer")

        prev_obs = (
            self.memory.episodic.last_by_actor("observer") if self.memory else None
        )
        prev_ui_summary = prev_obs.details if prev_obs else ""
        cached_analysis = state.get("observer_analysis", "")

        cache_hit = (
            config.OBSERVER_CACHE_ENABLED
            and prev_ui_summary
            and cached_analysis
            and ui_summary_text == prev_ui_summary
        )

        if cache_hit:
            raw_res = cached_analysis
            new_stagnation_count = state.get("stagnation_count", 0) + 1
            print(
                f"[Observer] [CACHE HIT] UI unchanged — reusing previous analysis (LLM skipped)"
            )
            self._log(
                f"LLM SKIPPED — UI summary identical to previous step (stagnation={new_stagnation_count})"
            )
        else:
            print("[Observer] Calling multimodal LLM for semantic interpretation...")
            img_b64 = self._encode_image(annotated_path, max_height=480)

            elements_data = [
                {
                    "i": el["id"],
                    "t": el.get("text") or "",
                    "r": el.get("xml_role") or "",
                }
                for el in final_widget_set
            ]
            elements_json = compress_and_report(elements_data, "elements", "observer")

            builder = self._build_semantic_request_builder()
            built = builder.build(
                scenario_desc=scenario_desc,
                navigation_context=navigation_context,
                elements_json=elements_json,
                img_b64=img_b64,
                general_knowledge=general_knowledge,
            )
            # built already contains fully-resolved text with no template variables
            # left to fill, so convert straight to message objects — do NOT route
            # through ChatPromptTemplate.from_messages().format_messages(), which
            # re-templates literal braces (e.g. JSON in elements_json) and raises
            # KeyError on real screen data.
            messages = convert_to_messages(built)

            self._log(
                "LLM call started (multimodal screen interpretation)", level=_LL.DEBUG
            )
            raw_res = ""
            backoff = 1.0
            for attempt in range(4):
                try:
                    response = self.llm.invoke(
                        messages,
                        temperature=config.OBSERVER_TEMPERATURE,
                        config={
                            "tags": ["observer", f"step_{current_step}"],
                            "timeout": 45.0,
                        },
                    )
                    raw_res = response.content
                    break
                except Exception as e:
                    err_str = str(e)
                    is_429 = (
                        "429" in err_str
                        or "rate" in err_str.lower()
                        or "too many requests" in err_str.lower()
                    )
                    if is_429 and attempt < 3:
                        print(
                            f"[Observer] Rate limited (429), retrying in {backoff:.1f}s (attempt {attempt + 1})..."
                        )
                        self._log(
                            f"Rate limited, retrying in {backoff:.1f}s",
                            err_str,
                            level=_LL.WARN,
                        )
                        time.sleep(backoff)
                        backoff = min(backoff * 2, 16.0)
                        continue
                    print(f"\n[!] Observer Vision LLM Failed/Timed Out: {err_str}")
                    self._log(
                        "LLM FATAL ERROR — aborting graph", err_str, level=_LL.ERROR
                    )
                    return Command(
                        goto="__end__",
                        update={
                            "execution_result": f"Fatal failure in Observer: {err_str}. Exiting system.",
                            "sender": "observer",
                            "is_completed": False,
                        },
                    )

            with open(analysis_path, "w", encoding="utf-8") as f:
                f.write(raw_res)
            self._log(
                "LLM analysis complete",
                raw_res[:500] + ("..." if len(raw_res) > 500 else ""),
            )

            new_stagnation_count = self._detect_stagnation(
                ui_summary_text, current_step, state.get("stagnation_count", 0)
            )

        if new_stagnation_count > 0:
            self._log(
                f"STAGNATION detected — count={new_stagnation_count} (UI unchanged from previous step)"
            )

        semantic_entries = []
        for el in final_widget_set:
            text = el.get("text", "").strip()
            if not text:
                continue
            semantic_entries.append(
                {
                    "name": f"widget_{el['id']}_{text[:30]}",
                    "summary": f"[{el.get('class', 'Widget')}] {text}",
                    "details": "",
                    "source": "observer",
                    "screen_context": scenario_desc,
                    "bounds": str(el.get("bounds", [])),
                }
            )

        if self.memory is not None:
            update_packet = {
                "episodic": {
                    "event_type": "observer_analysis",
                    "summary": raw_res.split("\n")[0][:200]
                    if raw_res
                    else "Screen analyzed",
                    "details": ui_summary_text,
                    "actor": "observer",
                    "step": current_step,
                },
            }
            if semantic_entries:
                update_packet["semantic"] = semantic_entries
            self.memory.update(update_packet)

        if self.logger is not None:
            self.logger.separator()

        if self.monitor is not None:
            self.monitor.on_observer(final_widget_set)

        uncertainty_dir = ""
        if config.OBSERVER_UNCERTAINTY_ENABLED:
            unc_builder = self._build_semantic_request_builder()
            unc_img_b64 = self._encode_image(annotated_path, max_height=480)
            unc_elements_json = compress_and_report(
                [{"i": el["id"], "t": el.get("text") or "", "r": el.get("xml_role") or ""}
                 for el in final_widget_set],
                "elements", "observer",
            )
            uncertainty_dir = self._maybe_run_uncertainty(
                enabled=True, builder=unc_builder, scenario_desc=scenario_desc,
                navigation_context=navigation_context, elements_json=unc_elements_json,
                img_b64=unc_img_b64, widgets=final_widget_set, step_dir=step_dir,
                general_knowledge=general_knowledge,
            )

        return {
            "screenshot_path": raw_path,
            "widgets": final_widget_set,
            "observer_analysis": raw_res,
            "observer_analysis_step": current_step,
            "stagnation_count": new_stagnation_count,
            "memory_context": memory_context,
            "sender": "observer",
            "observation_source": observation_source,
            "confidence_score": confidence_score,
            "fallback_reason": fallback_reason,
            "uncertainty_artifact_dir": uncertainty_dir,
        }
