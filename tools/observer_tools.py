import os
import json
import xml.etree.ElementTree as ET
import re
from datetime import datetime

# Disable Intel oneDNN (MKL-DNN) backend BEFORE importing PaddlePaddle.
# PaddleOCR v5 PIR-format models are incompatible with oneDNN on Windows,
# causing a NotImplementedError deep inside the inference engine.
os.environ['FLAGS_use_mkldnn'] = '0'

import cv2
import numpy as np
from paddleocr import PaddleOCR
from langchain_core.tools import tool


class ObserverTools:
    def __init__(self, device_session, output_dir):
        self.d = device_session
        self.output_dir = output_dir
        
        self.dirs = {
            "raw": os.path.join(output_dir, "raw"),
            "xml": os.path.join(output_dir, "xml"),
            "json": os.path.join(output_dir, "json"),
            "annotated": os.path.join(output_dir, "annotated")
        }
        
        for d in self.dirs.values():
            if not os.path.exists(d):
                os.makedirs(d)

        self.ocr_model = PaddleOCR(
            lang='en', 
            use_angle_cls=False,
            enable_mkldnn=False
        )

    def get_tools(self):
        d = self.d
        ocr_model = self.ocr_model
        dirs = self.dirs

        @tool
        def take_screenshot() -> str:
            """Takes a screenshot of the current device screen and returns the local file path."""
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(dirs["raw"], f"raw_{timestamp}.png")
            d.screenshot(filepath)
            return filepath

        @tool
        def get_ui_hierarchy() -> str:
            """Dumps the current UI hierarchy (XML) from the device and returns the raw XML string."""
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            xml_content = d.dump_hierarchy()
            filepath = os.path.join(dirs["xml"], f"hierarchy_{timestamp}.xml")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(xml_content)
            return xml_content

        @tool
        def ocr_extract_text(image_path: str) -> str:
            """Performs OCR on the given image path and returns a JSON string of detected text blocks and their bounds."""
            if not os.path.exists(image_path):
                return json.dumps({"error": f"File not found: {image_path}"})

            results = ocr_model.ocr(image_path)
            extracted = []

            if results and results[0]:
                res = results[0]
                if hasattr(res, 'keys') or isinstance(res, dict):
                    # PaddleX / PaddleOCR v3+ format
                    res_dict = res if isinstance(res, dict) else res.dict() if hasattr(res, 'dict') else dict(res)
                    texts = res_dict.get('rec_texts', [])
                    scores = res_dict.get('rec_scores', [])
                    polys = res_dict.get('dt_polys', []) or res_dict.get('rec_polys', [])
                    
                    for i in range(min(len(texts), len(scores), len(polys))):
                        text = texts[i]
                        confidence = scores[i]
                        box_points = polys[i]
                        
                        if confidence < 0.6:
                            continue
                            
                        xs = [pt[0] for pt in box_points]
                        ys = [pt[1] for pt in box_points]
                        x_min = int(min(xs))
                        y_min = int(min(ys))
                        x_max = int(max(xs))
                        y_max = int(max(ys))

                        extracted.append({
                            "text": str(text),
                            "bounds": [x_min, y_min, x_max, y_max],
                            "confidence": round(float(confidence), 4)
                        })
                else:
                    # Legacy PaddleOCR format
                    for line in res:
                        if not line or len(line) < 2: continue
                        box_points = line[0]
                        text = line[1][0]
                        confidence = line[1][1]

                        if confidence < 0.6:
                            continue

                        xs = [pt[0] for pt in box_points]
                        ys = [pt[1] for pt in box_points]
                        x_min = int(min(xs))
                        y_min = int(min(ys))
                        x_max = int(max(xs))
                        y_max = int(max(ys))

                        extracted.append({
                            "text": str(text),
                            "bounds": [x_min, y_min, x_max, y_max],
                            "confidence": round(float(confidence), 4)
                        })

            json_data = json.dumps(extracted)
            
            base = os.path.basename(image_path).replace(".png", "")
            json_path = os.path.join(dirs["json"], f"ocr_{base}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                f.write(json_data)
                
            return json_data

        @tool
        def detect_visual_elements(image_path: str) -> str:
            """Uses computer vision to detect UI elements like buttons/inputs from a screenshot and returns a JSON string of bounds."""
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
            
            base = os.path.basename(image_path).replace(".png", "")
            json_path = os.path.join(dirs["json"], f"cv_{base}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                f.write(json_data)

            return json_data

        @tool
        def annotate_screenshot(image_path: str, elements: list) -> str:
            """Draws bounding boxes and numeric IDs onto a screenshot for visual debugging and returns the path to the annotated image."""
            if not os.path.exists(image_path):
                return json.dumps({"error": f"File not found: {image_path}"})

            img = cv2.imread(image_path)

            for element in elements:
                el_id = element.get("id", "?")
                bounds = element.get("bounds", [])
                if len(bounds) != 4:
                    continue

                x1, y1, x2, y2 = int(bounds[0]), int(bounds[1]), int(bounds[2]), int(bounds[3])

                cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)

                label = str(el_id)
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.5
                thickness = 1
                (text_w, text_h), baseline = cv2.getTextSize(label, font, font_scale, thickness)

                bg_x1 = x1
                bg_y1 = y1 - text_h - baseline - 2
                bg_x2 = x1 + text_w + 4
                bg_y2 = y1

                cv2.rectangle(img, (bg_x1, bg_y1), (bg_x2, bg_y2), (0, 0, 255), -1)
                cv2.putText(img, label, (x1 + 2, y1 - baseline - 1), font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

            base_name = os.path.basename(image_path)
            output_path = os.path.join(dirs["annotated"], f"annotated_{base_name}")
            cv2.imwrite(output_path, img)

            return output_path

        return [take_screenshot, get_ui_hierarchy, ocr_extract_text, detect_visual_elements, annotate_screenshot]