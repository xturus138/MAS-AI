import base64
import json
import re
import os
import xml.etree.ElementTree as ET
import cv2
from langchain_core.messages import HumanMessage, SystemMessage
from core.models.state import AgentState
from core.ports.llm_port import ILLMClient


class ObserverAgent:
    def __init__(self, llm: ILLMClient, tools: list):
        self.llm = llm
        self.take_screenshot = tools[0]
        self.get_ui_hierarchy = tools[1]
        self.ocr_extract_text = tools[2]
        self.detect_visual_elements = tools[3]
        self.annotate_screenshot = tools[4]
    
        self.base_output = "outputs"
        self.dirs = {
            "crops": os.path.join(self.base_output, "crops"),
            "analysis": os.path.join(self.base_output, "analysis"),
            "json": os.path.join(self.base_output, "json")
        }
        for d in self.dirs.values():
            if not os.path.exists(d):
                os.makedirs(d)

    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as img:
            return base64.b64encode(img.read()).decode("utf-8")

    def _needs_visual_fallback(self, xml_content: str) -> bool:
        if not xml_content or xml_content.strip() == "":
            return True

        node_count = xml_content.count("<node")
        if node_count < 5:
            return True

        blind_classes = [
            "FlutterView",
            "SurfaceView",
            "WebView",
            "GLSurfaceView",
        ]

        for blind_class in blind_classes:
            if blind_class in xml_content:
                return True

        return False

    def _parse_xml_to_widgets(self, xml_content: str) -> list:
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError:
            return []

        elements = []
        for node in root.iter("node"):
            attribs = node.attrib
            is_editable = "EditText" in attribs.get("class", "")
            if attribs.get("clickable") == "true" or is_editable:
                bounds = [int(x) for x in re.findall(r"\d+", attribs.get("bounds", ""))]
                if len(bounds) == 4:
                    elements.append({
                        "bounds": bounds,
                        "text": attribs.get("text") or attribs.get("content-desc") or "",
                        "class": attribs.get("class", "").split(".")[-1],
                        "resource_id": attribs.get("resource-id", "").split("/")[-1],
                        "is_editable": is_editable,
                    })

        widget_set = []
        for idx, el in enumerate(elements[:50], start=1):
            el["id"] = idx
            widget_set.append(el)

        return widget_set

    def _run_ocr_on_bounds(self, image_path: str, widgets: list) -> list:
        img = cv2.imread(image_path)
        if img is None:
            return widgets

        for widget in widgets:
            if widget.get("text"):
                continue

            x1, y1, x2, y2 = widget["bounds"]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(img.shape[1], x2), min(img.shape[0], y2)
            if x2 <= x1 or y2 <= y1:
                continue

            base = os.path.basename(image_path).replace(".png", "")
            crop_filename = f"crop_{base}_{widget['id']}.png"
            cropped_path = os.path.join(self.dirs["crops"], crop_filename)
            
            cv2.imwrite(cropped_path, img[y1:y2, x1:x2])

            ocr_result_raw = self.ocr_extract_text.invoke({"image_path": cropped_path})
            try:
                ocr_items = json.loads(ocr_result_raw)
                if ocr_items and isinstance(ocr_items, list):
                    combined_text = " ".join(
                        item.get("text", "") for item in ocr_items if item.get("text")
                    ).strip()
                    if combined_text:
                        widget["text"] = combined_text
            except (json.JSONDecodeError, TypeError):
                pass

        return widgets

    def _merge_and_filter(self, cv_elements: list, ocr_elements: list, image_height: int) -> list:
        status_bar_threshold = image_height * 0.05

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

        def boxes_nearby(boxA, boxB, threshold=20):
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
            matched_text = None
            best_match_bounds = cv_bounds

            for ocr_idx, ocr_el in enumerate(filtered_ocr):
                if ocr_idx in used_ocr:
                    continue
                ocr_bounds = ocr_el["bounds"]
                iou = compute_iou(cv_bounds, ocr_bounds)

                if iou > 0.1 or boxes_nearby(cv_bounds, ocr_bounds):
                    matched_text = ocr_el.get("text", "")
                    merged_bounds = [
                        min(cv_bounds[0], ocr_bounds[0]),
                        min(cv_bounds[1], ocr_bounds[1]),
                        max(cv_bounds[2], ocr_bounds[2]),
                        max(cv_bounds[3], ocr_bounds[3]),
                    ]
                    best_match_bounds = merged_bounds
                    used_ocr.add(ocr_idx)
                    break

            entry = {"bounds": best_match_bounds}
            if matched_text:
                entry["text"] = matched_text
            merged.append(entry)

        for ocr_idx, ocr_el in enumerate(filtered_ocr):
            if ocr_idx not in used_ocr:
                merged.append({
                    "bounds": ocr_el["bounds"],
                    "text": ocr_el.get("text", ""),
                })

        final_widget_set = []
        for idx, el in enumerate(merged, start=1):
            el["id"] = idx
            final_widget_set.append(el)

        return final_widget_set

    def analyze(self, state: AgentState) -> dict:
        print(f"\n--- CYCLE {state['current_step'] + 1} | [Observer] Starting Screen Perception... ---")

        print("[Observer] Taking screenshot...")
        raw_image_path = self.take_screenshot.invoke({})
        basename = os.path.basename(raw_image_path).replace(".png", "")

        print("[Observer] Fetching UI hierarchy (raw XML)...")
        xml_content = self.get_ui_hierarchy.invoke({})
        ocr_raw = "[]"
        cv_raw = "[]"

        if not self._needs_visual_fallback(xml_content):
            print("[Observer] Rich XML detected. Using XML path (Native).")
            final_widget_set = self._parse_xml_to_widgets(xml_content)
            print(f"[Observer] {len(final_widget_set)} widgets found from XML.")

            unlabeled_count = sum(1 for w in final_widget_set if not w.get("text"))
            if unlabeled_count:
                print(f"[Observer] Running targeted OCR on {unlabeled_count} unlabeled widget(s)...")
                final_widget_set = self._run_ocr_on_bounds(raw_image_path, final_widget_set)

        else:
            print("[Observer] XML is not useful. Using ScenGen Pipeline (CV + OCR).")

            print("[Observer] Running OCR on screenshot...")
            ocr_raw = self.ocr_extract_text.invoke({"image_path": raw_image_path})
            try:
                ocr_elements = json.loads(ocr_raw)
                if isinstance(ocr_elements, dict) and "error" in ocr_elements:
                    ocr_elements = []
            except (json.JSONDecodeError, TypeError):
                ocr_elements = []

            print("[Observer] Detecting visual elements (CV)...")
            cv_raw = self.detect_visual_elements.invoke({"image_path": raw_image_path})
            try:
                cv_elements = json.loads(cv_raw)
                if isinstance(cv_elements, dict) and "error" in cv_elements:
                    cv_elements = []
            except (json.JSONDecodeError, TypeError):
                cv_elements = []

            print(f"[Observer] OCR: {len(ocr_elements)} items | CV: {len(cv_elements)} elements.")

            img = cv2.imread(raw_image_path)
            image_height = img.shape[0] if img is not None else 1920

            print("[Observer] Merging and filtering elements (ScenGen)...")
            final_widget_set = self._merge_and_filter(cv_elements, ocr_elements, image_height)
            print(f"[Observer] Final widget count after merge: {len(final_widget_set)}")

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
            "You are an Observer Agent in a Multi-Agent System responsible for automating Android UI interaction. "
            "Your task is to analyze the UI screenshot which has been annotated with numeric IDs for each element."
        )

        user_prompt = (
            f"Here is the UI screenshot with numeric IDs (Annotated Image), "
            f"along with the list of found elements: {json.dumps(list_of_texts_with_ids, ensure_ascii=False)}.\n\n"
            f"User Goal: {state['task_goal']}.\n\n"
            f"Task: Provide a brief semantic interpretation of this page (e.g., this is a login page, or home screen), "
            f"and mention which widget IDs seem most relevant to interact with to achieve the target goal. "
            f"Output must be a short narrative description."
        )

        message = HumanMessage(content=[
            {"type": "text", "text": user_prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
        ])

        system_message = SystemMessage(content=system_prompt)
        llm_response = self.llm.invoke([system_message, message])
        print("[Observer] Semantic interpretation received.")

        # Persist final analysis and results to folders
        final_widgets_path = os.path.join(self.dirs["json"], f"final_widgets_{basename}.json")
        with open(final_widgets_path, "w", encoding="utf-8") as f:
            json.dump(final_widget_set, f, indent=2, ensure_ascii=False)
            
        analysis_path = os.path.join(self.dirs["analysis"], f"analysis_{basename}.txt")
        with open(analysis_path, "w", encoding="utf-8") as f:
            f.write(llm_response.content)

        return {
            "screenshot_path": raw_image_path,
            "annotated_screenshot_path": annotated_path,
            "ocr_result": ocr_raw,
            "detected_elements": cv_raw,
            "ui_elements_summary": json.dumps(final_widget_set, ensure_ascii=False),
            "observer_analysis": llm_response.content,
            "current_step": state["current_step"] + 1,
        }