import base64
import json
import re
import os
import cv2
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import Command
from core.models.state import AgentState
from core.ports.llm_port import ILLMClient


class ObserverAgent:
    def __init__(self, llm: ILLMClient, tools: list):
        self.llm = llm
        self.take_screenshot = tools[0]
        self.ocr_extract_text = tools[1]
        self.detect_visual_elements = tools[2]
        self.annotate_screenshot = tools[3]
    
        self.base_output = "outputs"
        self.dirs = {
            "crops": os.path.join(self.base_output, "crops"),
            "analysis": os.path.join(self.base_output, "analysis"),
            "json": os.path.join(self.base_output, "json")
        }
        for d in self.dirs.values():
            if not os.path.exists(d):
                os.makedirs(d)

    def _encode_image(self, image_path: str, max_height: int = 720) -> str:
        """
        Reads an image, resizes it to a maximum height (720px) to optimize LLM visual tokens,
        and returns a base64 encoded string.
        """
        img = cv2.imread(image_path)
        if img is None:
            return ""

        # Resize to optimize for Vision-Language model tokens
        h, w = img.shape[:2]
        if h > max_height:
            scale = max_height / h
            new_w = int(w * scale)
            img = cv2.resize(img, (new_w, max_height), interpolation=cv2.INTER_AREA)

        # Encode as JPEG for efficient transmission
        success, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
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
        
        # Sort by Y top first, then X left
        sorted_ocr = sorted(ocr_elements, key=lambda x: (x["bounds"][1], x["bounds"][0]))
        
        merged = []
        if not sorted_ocr:
            return []
            
        current = sorted_ocr[0]
        
        for next_el in sorted_ocr[1:]:
            curr_b = current["bounds"]
            next_b = next_el["bounds"]
            
            # Check if on the same/close vertical line (Y overlap)
            # and close horizontally (X distance)
            y_overlap = min(curr_b[3], next_b[3]) - max(curr_b[1], next_b[1])
            h_dist = next_b[0] - curr_b[2]
            
            # Heuristic: overlap more than 50% of height and distance < 50px
            height = curr_b[3] - curr_b[1]
            if y_overlap > height * 0.5 and h_dist < 40:
                # Merge
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

    def _merge_and_filter(self, cv_elements: list, ocr_elements: list, image_height: int) -> list:
        # Filter out the top status bar only (clock, signal icons - not interactive)
        # We do NOT filter the bottom because the nav bar lives there.
        status_bar_threshold = image_height * 0.05

        # 1. Pre-merge OCR blocks horizontally
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

        # Step 1: Matching CV containers with OCR text
        for cv_el in filtered_cv:
            cv_bounds = cv_el["bounds"]
            matched_text = []
            matched_ocr_bounds = []  # Store individual OCR bounds for precision
            
            for ocr_idx, ocr_el in enumerate(filtered_ocr):
                if ocr_idx in used_ocr:
                    continue
                ocr_bounds = ocr_el["bounds"]
                
                # Check if text is INSIDE CV box or very nearby
                is_inside = (ocr_bounds[0] >= cv_bounds[0] - 10 and 
                             ocr_bounds[1] >= cv_bounds[1] - 10 and 
                             ocr_bounds[2] <= cv_bounds[2] + 10 and 
                             ocr_bounds[3] <= cv_bounds[3] + 10)

                if is_inside or compute_iou(cv_bounds, ocr_bounds) > 0.1 or boxes_nearby(cv_bounds, ocr_bounds):
                    matched_text.append(ocr_el.get("text", ""))
                    matched_ocr_bounds.append(ocr_bounds)
                    used_ocr.add(ocr_idx)

            # If OCR text was matched, use the UNION of OCR bounds as the click target
            # (more precise than the full CV contour center)
            if matched_ocr_bounds:
                all_x1 = min(b[0] for b in matched_ocr_bounds)
                all_y1 = min(b[1] for b in matched_ocr_bounds)
                all_x2 = max(b[2] for b in matched_ocr_bounds)
                all_y2 = max(b[3] for b in matched_ocr_bounds)
                click_bounds = [all_x1, all_y1, all_x2, all_y2]
            else:
                click_bounds = cv_bounds

            entry = {
                "bounds": click_bounds,   # Precise click target (OCR-driven if available)
                "cv_bounds": cv_bounds,   # Keep original CV bounds for annotation
                "text": " ".join(matched_text) if matched_text else "",
                "type": "container"
            }
            merged.append(entry)

        # Step 2: Fallback for orphaned OCR text (only if it looks meaningful)
        for ocr_idx, ocr_el in enumerate(filtered_ocr):
            if ocr_idx not in used_ocr:
                text = ocr_el.get("text", "").strip()
                # Heuristic: Skip very short text or very long paragraphs (pure content)
                if len(text) < 2 or len(text) > 100:
                    continue
                
                # Aspect ratio check: most buttons are wider than tall
                b = ocr_el["bounds"]
                w, h = b[2]-b[0], b[3]-b[1]
                if h > 0 and w/h < 0.2: # Very tall skinny text might be noise
                    continue

                merged.append({
                    "bounds": ocr_el["bounds"],
                    "text": text,
                    "type": "text_stub"
                })

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

        img = cv2.imread(raw_image_path)
        image_height = img.shape[0] if img is not None else 1920

        print("[Observer] Merging and filtering visual elements (ScenGen)...")
        final_widget_set = self._merge_and_filter(cv_elements, ocr_elements, image_height)
        print(f"[Observer] Final vision widget count: {len(final_widget_set)}")

        print("[Observer] Annotating screenshot...")
        annotated_path = self.annotate_screenshot.invoke({
            "image_path": raw_image_path,
            "elements": final_widget_set
        })

        print("[Observer] Calling multimodal LLM for semantic interpretation...")
        img_b64 = self._encode_image(annotated_path)

        list_of_texts_with_ids = [
            {"id": el["id"], "text": el.get("text", "(no text)")}
            for el in final_widget_set
        ]

        system_prompt = (
            "You are a Perception Agent. Your task is to look at an annotated Android screenshot and create a COMPLETE semantic map of the UI.\n\n"
            "INSTRUCTIONS:\n"
            "1. For EVERY ID visible on the screen, identify exactly what that element is (e.g., 'Floating Add Button', 'Menu Icon', 'Note Title').\n"
            "2. Note the approximate bounding box if requested, but primarily focus on the FUNCTION of each ID.\n\n"
            "OUTPUT FORMAT:\n"
            "SEMANTIC_MAP: [[ID]: [Description], ...]\n"
            "SUMMARY: [Brief overview of what page this is and what can be done here]"
        )

        user_prompt = (
            f"Annotated screenshot provided. Detected elements list: {json.dumps(list_of_texts_with_ids, ensure_ascii=False)}.\n\n"
            f"User Goal: {state['task_goal']}.\n"
            f"Current Subgoal: {state.get('current_subgoal', '')}.\n\n"
            f"TASK: Map every ID to its function. Be thorough. Ensure you identify any action buttons (like '+' or 'Create') correctly."
        )

        message = HumanMessage(content=[
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
        ])

        system_message = SystemMessage(content=system_prompt)
        llm_response = self.llm.invoke([system_message, message])
        raw_res = llm_response.content
        print("[Observer] Full semantic interpretation received.")

        # --- Enhanced Semantic State ---
        # We no longer filter out 'irrelevant' widgets here. 
        # We pass the ENTIRE set to the Orchestrator/Decider, sorted by VLM priority if possible.
        
        # Extract suggested IDs to put them at the top of the summary for the Decider
        relevant_ids_match = re.search(r"SEMANTIC_MAP:.*?\[(\d+)\].*?", raw_res, re.DOTALL)
        # (Simplified extraction for a full list - we just keep the VLM text as the analysis)
        
        # We limit to 50 widgets to stay safe with token limits, but 50 covers almost all screens.
        filtered_widgets = final_widget_set[:50]

        # Build a clean element summary for the Decider/Orchestrator
        formatted_ui_elements = []
        for el in filtered_widgets:
            cls_name = el.get("class", "Widget")
            text = el.get("text", "(no text)")
            el_id = el.get("id", "?")
            formatted_ui_elements.append(f"ID:{el_id} | {cls_name} | '{text}'")
            
        ui_summary_text = "\n".join(formatted_ui_elements)

        # --- Stagnation Detection ---
        previous_ui = state.get("previous_ui_summary", "")
        prev_count = state.get("stagnation_count", 0)
        if ui_summary_text and ui_summary_text == previous_ui:
            new_stagnation_count = prev_count + 1
        else:
            new_stagnation_count = 0

        # Hand control back to the Orchestrator
        return Command(
            goto="orchestrator_node",
            update={
                "screenshot_path": raw_image_path,
                "annotated_screenshot_path": annotated_path,
                "ocr_result": ocr_raw,
                "detected_elements": cv_raw,
                "ui_elements_summary": ui_summary_text,
                "widgets": final_widget_set, # Keep the FULL set in raw state
                "observer_analysis": raw_res, # The complete semantic map
                "current_step": state["current_step"] + 1,
                "sender": "observer",
                "previous_ui_summary": ui_summary_text,
                "stagnation_count": new_stagnation_count,
            },
        )