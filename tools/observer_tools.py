import os
import json
import xml.etree.ElementTree as ET
import re
from datetime import datetime

import cv2
import numpy as np
from paddleocr import PaddleOCR
from langchain_core.tools import tool


class ObserverTools:
    def __init__(self, device_session, output_dir):
        self.d = device_session
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        self.ocr_model = PaddleOCR(lang='en', use_angle_cls=False, show_log=False)

    def get_tools(self):
        d = self.d
        output_dir = self.output_dir
        ocr_model = self.ocr_model

        @tool
        def take_screenshot() -> str:
            """Capture a screenshot of the current device screen and return the file path."""
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(output_dir, f"state_{timestamp}.png")
            d.screenshot(filepath)
            return filepath

        @tool
        def get_ui_hierarchy() -> str:
            """Dump the current UI hierarchy and return a summarized list of clickable elements."""
            xml_content = d.dump_hierarchy()
            root = ET.fromstring(xml_content)
            elements = []
            for node in root.iter('node'):
                attribs = node.attrib
                if attribs.get('clickable') == 'true' or 'EditText' in attribs.get('class', ''):
                    bounds = [int(x) for x in re.findall(r'\d+', attribs.get('bounds', ''))]
                    if len(bounds) == 4:
                        center_x = (bounds[0] + bounds[2]) // 2
                        center_y = (bounds[1] + bounds[3]) // 2

                        label = attribs.get('text') or attribs.get('content-desc') or ""
                        resource_id = attribs.get('resource-id', '').split('/')[-1]
                        class_name = attribs.get('class', '').split('.')[-1]

                        elements.append(f"@{center_x},{center_y} | {class_name} | ID:{resource_id} | '{label}'")

            return "\n".join(elements[:50])

        @tool
        def ocr_extract_text(image_path: str) -> str:
            """Extract text, bounding boxes, and confidence scores from an image using PaddleOCR.
            Returns a JSON string: [{"text": "...", "bounds": [x1, y1, x2, y2], "confidence": 0.95}]
            """
            if not os.path.exists(image_path):
                return json.dumps({"error": f"File not found: {image_path}"})

            results = ocr_model.ocr(image_path, cls=False)
            extracted = []

            if results and results[0]:
                for line in results[0]:
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
                        "text": text,
                        "bounds": [x_min, y_min, x_max, y_max],
                        "confidence": round(float(confidence), 4)
                    })

            return json.dumps(extracted)

        @tool
        def detect_visual_elements(image_path: str) -> str:
            """Detect UI elements (buttons, inputs, etc.) using OpenCV contour detection.
            Returns a JSON string: [{"bounds": [x, y, x+w, y+h]}]
            """
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

            return json.dumps(detected)

        @tool
        def annotate_screenshot(image_path: str, elements: list) -> str:
            """Draw bounding boxes and ID labels on a screenshot for agent visual reference.
            Expects elements as: [{"id": 1, "bounds": [x1, y1, x2, y2]}, ...]
            Returns the file path of the annotated image.
            """
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
            output_path = os.path.join(output_dir, f"annotated_{base_name}")
            cv2.imwrite(output_path, img)

            return output_path

        return [take_screenshot, get_ui_hierarchy, ocr_extract_text, detect_visual_elements, annotate_screenshot]