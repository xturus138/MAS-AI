import os
import json
import cv2
import numpy as np
import easyocr
from langchain_core.tools import tool
from core.ports.device_port import IDeviceClient
from shared import config
from adapters.omniparser.omniparser_backend import OmniParserBackend


class ObserverTools:
    def __init__(self, device_session: IDeviceClient):
        self.d = device_session
        self.ocr_model = easyocr.Reader(['en'], gpu=True)

        self.omniparser = OmniParserBackend(
            weights_dir=config.OMNIPARSER_WEIGHTS_DIR,
            project_dir=config.OMNIPARSER_PROJECT_DIR,
            box_threshold=config.OMNIPARSER_BOX_THRESHOLD,
            enabled=config.OMNIPARSER_ENABLED,
        )

    def get_tools(self):
        d = self.d
        ocr_model = self.ocr_model
        omniparser = self.omniparser

        @tool
        def take_screenshot(target_path: str) -> str:
            """Takes a screenshot of the current device screen and saves it to target_path."""
            d.screenshot(target_path)
            return target_path

        @tool
        def ocr_extract_text(image_path: str, save_path: str = "") -> str:
            """Performs OCR on the image. If save_path is provided, result is saved as JSON."""
            if not os.path.exists(image_path):
                return json.dumps({"error": f"File not found: {image_path}"})

            img = cv2.imread(image_path)
            if img is None:
                return json.dumps({"error": f"Could not read image: {image_path}"})
            
            orig_h, orig_w = img.shape[:2]
            target_h = 1080
            scale = 1.0
            if orig_h > target_h:
                scale = target_h / orig_h
                new_w = int(orig_w * scale)
                img = cv2.resize(img, (new_w, target_h), interpolation=cv2.INTER_AREA)

            results = ocr_model.readtext(img)
            extracted = []

            for (box_points, text, confidence) in results:
                if confidence < 0.4:
                    continue
                
                xs = [pt[0] / scale for pt in box_points]
                ys = [pt[1] / scale for pt in box_points]
                x_min, y_min = int(min(xs)), int(min(ys))
                x_max, y_max = int(max(xs)), int(max(ys))

                extracted.append({
                    "text": str(text),
                    "bounds": [x_min, y_min, x_max, y_max],
                    "confidence": round(float(confidence), 4)
                })

            json_data = json.dumps(extracted)
            if save_path:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(json_data)
                
            return json_data

        @tool
        def detect_visual_elements(image_path: str, save_path: str = "") -> str:
            """Uses CV to detect UI elements. If save_path is provided, result is saved as JSON."""
            if not os.path.exists(image_path):
                return json.dumps({"error": f"File not found: {image_path}"})

            img = cv2.imread(image_path)
            img_h, img_w = img.shape[:2]
            total_area = img_h * img_w

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)

            kernel = np.ones((9, 9), np.uint8)
            dilated = cv2.dilate(edges, kernel, iterations=1)

            contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            detected = []
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h

                if area < 50:
                    continue
                if area > total_area * 0.80:
                    continue

                detected.append({"bounds": [x, y, x + w, y + h]})

            json_data = json.dumps(detected)
            if save_path:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(json_data)

            return json_data

        @tool
        def annotate_screenshot(image_path: str, elements: list, save_path: str) -> str:
            """Draws boxes onto a screenshot and saves result to save_path."""
            if not os.path.exists(image_path):
                return json.dumps({"error": f"File not found: {image_path}"})

            img = cv2.imread(image_path)

            for element in elements:
                el_id = element.get("id", "?")
                el_type = element.get("type", "container")
                ann_bounds = element.get("cv_bounds") or element.get("bounds", [])
                click_bounds = element.get("bounds", ann_bounds)
                if len(ann_bounds) != 4:
                    continue

                x1, y1, x2, y2 = int(ann_bounds[0]), int(ann_bounds[1]), int(ann_bounds[2]), int(ann_bounds[3])
                color = (0, 0, 255) if el_type == "container" else (255, 0, 0)
                thickness = 2 if el_type == "container" else 1
                cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)

                if len(click_bounds) == 4:
                    cx = int((click_bounds[0] + click_bounds[2]) / 2)
                    cy = int((click_bounds[1] + click_bounds[3]) / 2)
                    cv2.circle(img, (cx, cy), 4, (0, 220, 0), -1)

                label = str(el_id)
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.4
                font_thickness = 1
                (text_w, text_h), baseline = cv2.getTextSize(label, font, font_scale, font_thickness)
                bg_x1, bg_y1 = x1, y1 - text_h - baseline - 2
                bg_x2, bg_y2 = x1 + text_w + 4, y1
                cv2.rectangle(img, (bg_x1, bg_y1), (bg_x2, bg_y2), color, -1)
                cv2.putText(img, label, (x1 + 2, y1 - baseline - 1), font, font_scale, (255, 255, 255), font_thickness, cv2.LINE_AA)

            cv2.imwrite(save_path, img)
            return save_path

        @tool
        def check_keyboard_state() -> str:
            """Checks if keyboard is visible."""
            return json.dumps({"is_shown": d.check_keyboard_state()})

        base_tools = [take_screenshot, ocr_extract_text, detect_visual_elements, annotate_screenshot, check_keyboard_state]

        if omniparser.is_available:
            @tool
            def parse_screen_omniparser(image_path: str, save_path: str = "") -> str:
                """
                OmniParser unified vision pipeline: YOLO widget detection + Florence-2 icon
                captioning + EasyOCR, all fused into a single structured element list.
                Returns JSON list of widgets with bounds (pixels), text, and type.
                When save_path is given, result is also written to disk as JSON.
                """
                try:
                    widgets = omniparser.parse_screen(image_path)
                except Exception as exc:
                    return json.dumps({"error": str(exc)})

                json_data = json.dumps(widgets, ensure_ascii=False)
                if save_path:
                    with open(save_path, "w", encoding="utf-8") as fh:
                        fh.write(json_data)
                return json_data

            return base_tools + [parse_screen_omniparser]

        return base_tools
