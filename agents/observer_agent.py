import base64
import json
import re
import os
import cv2
from langchain_core.prompts import ChatPromptTemplate
from langgraph.types import Command
from core.models.state import AgentState
from core.ports.llm_port import ILLMClient
from core.utils.toons_helper import compress_and_report


class ObserverAgent:
    def __init__(self, llm: ILLMClient, tools: list):
        self.llm = llm
        self.take_screenshot = tools[0]
        self.ocr_extract_text = tools[1]
        self.detect_visual_elements = tools[2]
        self.annotate_screenshot = tools[3]
        self.check_keyboard_state = tools[4]
    
        self.base_output = "outputs"
        self.dirs = {
            "crops": os.path.join(self.base_output, "crops"),
            "analysis": os.path.join(self.base_output, "analysis"),
            "json": os.path.join(self.base_output, "json"),
            "merged": os.path.join(self.base_output, "merged")
        }
        for d in self.dirs.values():
            if not os.path.exists(d):
                os.makedirs(d)

    def _encode_image(self, image_path: str, max_height: int = 720) -> str:
        """
        Reads an image, resizes it to a maximum height (720px) and encodes it
        as WebP at 70% quality to minimize base64 token usage.
        """
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
        """
        Merges OCR text blocks that are on the same line and close to each other horizontally.
        This prevents splitting a single label into multiple widgets.
        """
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
        """Groups dense clusters of elements in the lower half of the screen into a single Keyboard element."""
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
            print(f"[Observer] ADB confirmed Keyboard is open. Grouped {len(kb_candidates)} bottom-half elements into a single body.")
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
                w, h = b[2]-b[0], b[3]-b[1]
                if h > 0 and w/h < 0.2:
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

    def analyze(self, state: AgentState) -> Command:
        print(f"\n--- CYCLE {state['current_step'] + 1} | [Observer] Starting Pure Vision Perception... ---")

        print("[Observer] Taking screenshot...")
        raw_image_path = self.take_screenshot.invoke({})
        basename = os.path.basename(raw_image_path).replace(".png", "")

        print("[Observer] Running Vision Pipeline (OCR + CV)...")
        ocr_raw = self.ocr_extract_text.invoke({"image_path": raw_image_path})
        cv_raw = self.detect_visual_elements.invoke({"image_path": raw_image_path})

        try:
            ocr_elements = json.loads(ocr_raw)
            cv_elements = json.loads(cv_raw)
        except (json.JSONDecodeError, TypeError):
            ocr_elements, cv_elements = [], []

        print("[Observer] Checking keyboard state via ADB...")
        kb_resp = self.check_keyboard_state.invoke({})
        try:
            is_kb_shown = json.loads(kb_resp).get("is_shown", False)
        except:
            is_kb_shown = False

        img = cv2.imread(raw_image_path)
        image_height = img.shape[0] if img is not None else 1920

        print("[Observer] Merging and filtering visual elements (ScenGen)...")
        final_widget_set = self._merge_and_filter(cv_elements, ocr_elements, image_height, is_kb_shown)
        print(f"[Observer] Final vision widget count: {len(final_widget_set)}")

        merged_json_path = os.path.join(self.dirs["merged"], f"merged_{basename}.json")
        with open(merged_json_path, "w", encoding="utf-8") as f:
            json.dump(final_widget_set, f, indent=4, ensure_ascii=False)
        print(f"[Observer] Merged results saved to: {merged_json_path}")

        print("[Observer] Annotating screenshot...")
        annotated_path = self.annotate_screenshot.invoke({
            "image_path": raw_image_path,
            "elements": final_widget_set
        })

        print("[Observer] Calling multimodal LLM for semantic interpretation...")
        img_b64 = self._encode_image(annotated_path)

        elements_data = [{"i": el["id"], "t": el.get("text") or ""} for el in final_widget_set]
        elements_json = compress_and_report(elements_data, "elements", "observer")

        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a Perception Agent. Analyze an annotated Android screenshot and map every visible ID to its UI function.\n"
                       "IMPORTANT: If you see an On-Screen Keyboard, treat it as a single block. Do not analyze individual keys (A, B, C, Enter, etc.).\n"
                       "OUTPUT FORMAT (strict):\n"
                       "SEMANTIC_MAP: [[ID]: Description, ...]\n"
                       "SUMMARY: One sentence describing the screen and key actions available."),
            ("human", [
                {"type": "text", "text": "Goal: {task_goal}\nSubgoal: {subgoal}\nElements: {elements_json}\n\nMap every ID in the screenshot to its function. Identify interactive elements (buttons, inputs, nav icons) precisely. Skip interpreting individual keyboard keys if they appear."},
                {"type": "image_url", "image_url": {"url": "data:image/webp;base64,{img_b64}"}}
            ])
        ])

        messages = prompt.format_messages(
            task_goal=state['task_goal'],
            subgoal=state.get('current_subgoal', ''),
            elements_json=elements_json,
            img_b64=img_b64
        )

        try:
            import sys
            print("[Observer] Translating vision to semantics ", end="", flush=True)
            chunks = []
            
            for chunk in self.llm.stream(
                messages,
                config={
                    "tags": ["observer", f"step_{state.get('current_step', 0)}"],
                    "timeout": 45.0
                }
            ):
                print(".", end="", flush=True)
                chunks.append(chunk.content)
                
            raw_res = "".join(chunks)
            print("\n[Observer] Full semantic interpretation received.")
        except Exception as e:
            print(f"\n[!] Observer Vision LLM Failed/Timed Out: {str(e)}")
            return Command(
                goto="__end__",
                update={
                    "execution_result": f"Fatal failure in Observer: {str(e)}. Exiting system.",
                    "sender": "observer",
                    "is_completed": False
                }
            )

        analysis_path = os.path.join(self.dirs["analysis"], f"analysis_{basename}.txt")
        with open(analysis_path, "w", encoding="utf-8") as f:
            f.write(raw_res)
        print(f"[Observer] Semantic analysis saved to: {analysis_path}")

        
        filtered_widgets = final_widget_set[:50]

        summary_data = [
            {"id": el.get("id", "?"), "cls": el.get("class", "Widget"), "text": el.get("text", "")}
            for el in filtered_widgets
        ]
        ui_summary_text = compress_and_report(summary_data, "ui_summary", "observer")

        previous_ui = state.get("previous_ui_summary", "")
        prev_count = state.get("stagnation_count", 0)
        if ui_summary_text and ui_summary_text == previous_ui:
            new_stagnation_count = prev_count + 1
        else:
            new_stagnation_count = 0

        return {
            "screenshot_path": raw_image_path,
            "annotated_screenshot_path": annotated_path,
            "ocr_result": ocr_raw,
            "detected_elements": cv_raw,
            "ui_elements_summary": ui_summary_text,
            "widgets": final_widget_set,
            "observer_analysis": raw_res,
            "current_step": state["current_step"] + 1,
            "sender": "observer",
            "previous_ui_summary": ui_summary_text,
            "stagnation_count": new_stagnation_count,
        }
