import base64
import json
import os
import cv2
from langchain_core.prompts import ChatPromptTemplate
from langgraph.types import Command
from core.models.state import AgentState
from core.ports.llm_port import ILLMClient
from core.utils.toons_helper import compress_and_report, prune_history_by_tokens


class ObserverAgent:
    def __init__(self, llm: ILLMClient, tools: list, memory=None, logger=None):
        self.llm = llm
        self.take_screenshot = tools[0]
        self.ocr_extract_text = tools[1]
        self.detect_visual_elements = tools[2]
        self.annotate_screenshot = tools[3]
        self.check_keyboard_state = tools[4]
        # Optional: OmniParser unified vision backend (index 5)
        self.parse_screen_omniparser = tools[5] if len(tools) > 5 else None
        self.memory = memory
        self.logger = logger

    def _encode_image(self, image_path: str, max_height: int = 720) -> str:
        img = cv2.imread(image_path)
        if img is None:
            return ""

        h, w = img.shape[:2]
        if h > max_height:
            scale = max_height / h
            new_w = int(w * scale)
            img = cv2.resize(img, (new_w, max_height), interpolation=cv2.INTER_AREA)

        success, buffer = cv2.imencode(".webp", img, [int(cv2.IMWRITE_WEBP_QUALITY), 70])
        if not success:
            success, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        if not success:
            return ""

        return base64.b64encode(buffer).decode("utf-8")

    def _merge_ocr_blocks(self, ocr_elements: list) -> list:
        if not ocr_elements:
            return []

        sorted_ocr = sorted(ocr_elements, key=lambda x: (x["bounds"][1], x["bounds"][0]))

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
                    max(curr_b[3], next_b[3])
                ]
                current["text"] = current.get("text", "") + " " + next_el.get("text", "")
            else:
                merged.append(current)
                current = next_el

        merged.append(current)
        return merged

    def _group_keyboard_elements(self, elements: list, image_height: int, is_kb_shown: bool) -> list:
        if not is_kb_shown:
            return elements

        kb_threshold_y = image_height * 0.50

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
                "type": "container"
            }
            non_kb_elements.append(keyboard_el)
            return non_kb_elements

        return elements

    def _merge_and_filter(self, cv_elements: list, ocr_elements: list, image_height: int, is_kb_shown: bool = False) -> list:
        status_bar_threshold = image_height * 0.05

        ocr_elements = self._merge_ocr_blocks(ocr_elements)

        filtered_cv = [
            el for el in cv_elements
            if el.get("bounds", [0, 0])[1] >= status_bar_threshold
        ]
        filtered_ocr = [
            el for el in ocr_elements
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

        merged = []
        used_ocr = set()

        for cv_el in filtered_cv:
            cv_bounds = cv_el["bounds"]
            matched_text = []
            matched_ocr_bounds = []

            for ocr_idx, ocr_el in enumerate(filtered_ocr):
                if ocr_idx in used_ocr:
                    continue
                ocr_bounds = ocr_el["bounds"]

                is_inside = (ocr_bounds[0] >= cv_bounds[0] - 10 and
                             ocr_bounds[1] >= cv_bounds[1] - 10 and
                             ocr_bounds[2] <= cv_bounds[2] + 10 and
                             ocr_bounds[3] <= cv_bounds[3] + 10)

                if is_inside or compute_iou(cv_bounds, ocr_bounds) > 0.1 or boxes_nearby(cv_bounds, ocr_bounds):
                    matched_text.append(ocr_el.get("text", ""))
                    matched_ocr_bounds.append(ocr_bounds)
                    used_ocr.add(ocr_idx)

            if matched_ocr_bounds:
                all_x1 = min(b[0] for b in matched_ocr_bounds)
                all_y1 = min(b[1] for b in matched_ocr_bounds)
                all_x2 = max(b[2] for b in matched_ocr_bounds)
                all_y2 = max(b[3] for b in matched_ocr_bounds)
                click_bounds = [all_x1, all_y1, all_x2, all_y2]
            else:
                click_bounds = cv_bounds

            entry = {
                "bounds": click_bounds,
                "cv_bounds": cv_bounds,
                "text": " ".join(matched_text) if matched_text else "",
                "type": "container"
            }
            merged.append(entry)

        for ocr_idx, ocr_el in enumerate(filtered_ocr):
            if ocr_idx not in used_ocr:
                text = ocr_el.get("text", "").strip()
                if len(text) < 2 or len(text) > 100:
                    continue

                b = ocr_el["bounds"]
                w, h = b[2] - b[0], b[3] - b[1]
                if h > 0 and w / h < 0.2:
                    continue

                merged.append({
                    "bounds": ocr_el["bounds"],
                    "text": text,
                    "type": "text_stub"
                })

        merged = self._group_keyboard_elements(merged, image_height, is_kb_shown)

        final_widget_set = []
        for idx, el in enumerate(merged, start=1):
            el["id"] = idx
            el["class"] = "Interactive" if el["type"] == "container" else "StaticText"
            el["resource_id"] = "none"
            final_widget_set.append(el)

        return final_widget_set

    def _detect_stagnation(self, current_summary: str, current_step: int, prev_stagnation: int) -> int:
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

    def _log(self, msg: str, detail: str = ""):
        if self.logger is not None:
            self.logger.log("OBSERVER", msg, detail)

    def _run_canny_pipeline(
        self,
        raw_path: str,
        ocr_path: str,
        cv_path: str,
        image_height: int,
        is_kb_shown: bool,
    ) -> list:
        """Run the classic Canny edge detection + EasyOCR vision pipeline."""
        ocr_raw = self.ocr_extract_text.invoke({"image_path": raw_path, "save_path": ocr_path})
        cv_raw = self.detect_visual_elements.invoke({"image_path": raw_path, "save_path": cv_path})
        try:
            ocr_elements = json.loads(ocr_raw)
            cv_elements = json.loads(cv_raw)
        except (json.JSONDecodeError, TypeError):
            ocr_elements, cv_elements = [], []
        self._log(
            "Canny+OCR pipeline complete",
            f"ocr_elements={len(ocr_elements)}  cv_elements={len(cv_elements)}"
        )
        return self._merge_and_filter(cv_elements, ocr_elements, image_height, is_kb_shown)

    def analyze(self, state: AgentState) -> Command:
        current_step = state.get("current_step", 0)
        print(f"\n--- CYCLE {current_step} | [Observer] Starting Pure Vision Perception... ---")
        self._log(f"=== CYCLE {current_step} — Vision Perception started ===")

        step_dir = state.get("step_dir", "outputs")
        raw_path = os.path.join(step_dir, "raw.png")
        ocr_path = os.path.join(step_dir, "ocr.json")
        cv_path = os.path.join(step_dir, "cv.json")
        merged_path = os.path.join(step_dir, "merged.json")
        annotated_path = os.path.join(step_dir, "annotated.png")
        analysis_path = os.path.join(step_dir, "analysis.txt")

        # ── Active Retrieval ──────────────────────────────────────────────────
        memory_context = ""
        scenario_desc = "N/A"
        navigation_context = "N/A"
        if self.memory is not None:
            memory_context = self.memory.retrieve(f"navigation screen step={current_step}")
            scenario_desc = self.memory.core.get("scenario_desc") or "N/A"
            navigation_context = self.memory.core.get("navigation_context") or "N/A"
        self._log("Memory retrieval complete", f"scenario_desc={scenario_desc[:80]}")

        print("[Observer] Taking screenshot...")
        self.take_screenshot.invoke({"target_path": raw_path})
        self._log("Screenshot captured", raw_path)

        print("[Observer] Checking keyboard state via ADB...")
        kb_resp = self.check_keyboard_state.invoke({})
        try:
            is_kb_shown = json.loads(kb_resp).get("is_shown", False)
        except Exception:
            is_kb_shown = False

        img = cv2.imread(raw_path)
        image_height = img.shape[0] if img is not None else 1920

        if self.parse_screen_omniparser is not None:
            # ── OmniParser path: unified YOLO + Florence-2 + OCR pipeline ────
            print("[Observer] Running OmniParser unified vision pipeline (YOLO + Florence-2 + OCR)...")
            self._log("Vision pipeline: OmniParser")
            omni_raw = self.parse_screen_omniparser.invoke({
                "image_path": raw_path,
                "save_path": cv_path,
            })
            try:
                omni_elements = json.loads(omni_raw)
                if isinstance(omni_elements, dict) and "error" in omni_elements:
                    raise ValueError(omni_elements["error"])
            except Exception as exc:
                print(f"[Observer] OmniParser failed ({exc}), falling back to Canny pipeline.")
                self._log("OmniParser FAILED — falling back to Canny+OCR", str(exc))
                omni_elements = None

            if omni_elements is not None:
                # OmniParser already fuses OCR + CV + icon captions; skip merge step.
                grouped = self._group_keyboard_elements(omni_elements, image_height, is_kb_shown)
                final_widget_set = []
                for idx, el in enumerate(grouped, start=1):
                    el["id"] = idx
                    el["class"] = "Interactive" if el["type"] == "container" else "StaticText"
                    el["resource_id"] = "none"
                    final_widget_set.append(el)
                self._log(
                    "OmniParser pipeline complete",
                    f"widgets={len(final_widget_set)}  keyboard={'shown' if is_kb_shown else 'hidden'}"
                )
            else:
                # Fallback triggered inside the OmniParser branch
                final_widget_set = self._run_canny_pipeline(raw_path, ocr_path, cv_path, image_height, is_kb_shown)
        else:
            # ── Canny + EasyOCR fallback ──────────────────────────────────────
            print("[Observer] Running Canny+OCR vision pipeline...")
            final_widget_set = self._run_canny_pipeline(raw_path, ocr_path, cv_path, image_height, is_kb_shown)

        with open(merged_path, "w", encoding="utf-8") as f:
            json.dump(final_widget_set, f, indent=4, ensure_ascii=False)

        print("[Observer] Annotating screenshot...")
        self.annotate_screenshot.invoke({
            "image_path": raw_path,
            "elements": final_widget_set,
            "save_path": annotated_path
        })
        self._log("Annotated screenshot saved", annotated_path)

        print("[Observer] Calling multimodal LLM for semantic interpretation...")
        img_b64 = self._encode_image(annotated_path)

        elements_data = [{"i": el["id"], "t": el.get("text") or ""} for el in final_widget_set]
        elements_json = compress_and_report(elements_data, "elements", "observer")

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a Perception Agent. Your ONLY job is to describe what is visible on the screen. "
                       "Do NOT assume what the user wants to do. Do NOT bias your descriptions toward any goal.\n"
                       "IMPORTANT: If you see an On-Screen Keyboard, treat it as a single block. Do not analyze individual keys.\n"
                       "OUTPUT FORMAT (strict):\n"
                       "SEMANTIC_MAP: [[ID]: Description, ...]\n"
                       "SUMMARY: One sentence describing the screen and key actions available."),
            ("human", [
                {"type": "text", "text": "App Context: {scenario_desc}\nNavigation Path: {navigation_context}\nElements: {elements_json}\n\nMap every ID in the screenshot to its generic UI function. Be objective. Do not reference any task or goal."},
                {"type": "image_url", "image_url": {"url": "data:image/webp;base64,{img_b64}"}}
            ])
        ])

        messages = prompt.format_messages(
            scenario_desc=scenario_desc,
            navigation_context=navigation_context,
            elements_json=elements_json,
            img_b64=img_b64
        )

        self._log("LLM call started (multimodal screen interpretation)")
        try:
            chunks = []
            for chunk in self.llm.stream(
                messages,
                config={
                    "tags": ["observer", f"step_{current_step}"],
                    "timeout": 45.0
                }
            ):
                chunks.append(chunk.content)

            raw_res = "".join(chunks)
        except Exception as e:
            print(f"\n[!] Observer Vision LLM Failed/Timed Out: {str(e)}")
            self._log("LLM FATAL ERROR — aborting graph", str(e))
            return Command(
                goto="__end__",
                update={
                    "execution_result": f"Fatal failure in Observer: {str(e)}. Exiting system.",
                    "sender": "observer",
                    "is_completed": False
                }
            )

        with open(analysis_path, "w", encoding="utf-8") as f:
            f.write(raw_res)
        self._log("LLM analysis complete", raw_res[:500] + ("..." if len(raw_res) > 500 else ""))

        filtered_widgets = final_widget_set[:50]
        summary_data = [
            {"id": el.get("id", "?"), "cls": el.get("class", "Widget"), "text": el.get("text", "")}
            for el in filtered_widgets
        ]
        ui_summary_text = compress_and_report(summary_data, "ui_summary", "observer")

        # ── Stagnation Detection via Episodic Memory ──────────────────────────
        new_stagnation_count = self._detect_stagnation(
            ui_summary_text, current_step, state.get("stagnation_count", 0)
        )
        if new_stagnation_count > 0:
            self._log(f"STAGNATION detected — count={new_stagnation_count} (UI unchanged from previous step)")

        # ── Semantic Memory: persist detected UI elements ─────────────────────
        semantic_entries = []
        for el in final_widget_set:
            text = el.get("text", "").strip()
            if not text:
                continue
            semantic_entries.append({
                "name": f"widget_{el['id']}_{text[:30]}",
                "summary": f"[{el.get('class', 'Widget')}] {text}",
                "details": "",
                "source": "observer",
                "screen_context": scenario_desc,
                "bounds": str(el.get("bounds", [])),
            })

        # ── Memory Update ─────────────────────────────────────────────────────
        if self.memory is not None:
            update_packet = {
                "episodic": {
                    "event_type": "observer_analysis",
                    "summary": raw_res.split("\n")[0][:200] if raw_res else "Screen analyzed",
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

        return {
            "screenshot_path": raw_path,
            "widgets": final_widget_set,
            "observer_analysis": raw_res,
            "observer_analysis_step": current_step,
            "stagnation_count": new_stagnation_count,
            "memory_context": memory_context,
            "sender": "observer",
        }
