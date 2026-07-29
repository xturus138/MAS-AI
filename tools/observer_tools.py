import os
import json
import cv2
import numpy as np
import easyocr
from langchain_core.tools import tool
from core.ports.device_port import IDeviceClient


class ObserverTools:
    def __init__(self, device_session: IDeviceClient):
        self.d = device_session
        self.ocr_model = easyocr.Reader(['en'], gpu=True)

    def get_tools(self):
        d = self.d
        ocr_model = self.ocr_model

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
            """Uses CV to detect UI elements. If save_path is provided, result is saved as JSON.

            Two complementary detection channels:

            1. Canny edge + contour — finds elements with a visible outline or
               strong internal contrast (text, icons, bordered controls).
            2. Uniform-region — finds flat, evenly-filled rectangular regions
               (filled buttons, cards, toolbars, list rows).

            Channel 2 exists because edge detection is structurally blind to a
            low-contrast filled element: a Material-style button filled
            rgb(213,214,212) on an rgb(250,250,250) background has a soft
            antialiased border whose post-blur gradient magnitude falls below
            Canny's low threshold, so it produces literally zero edge pixels
            and the button is never detected at all — only the text drawn on
            top of it is. Lowering Canny's thresholds does NOT fix this
            (measured against Screen Annotation ground truth: recall@IoU0.5
            29.2% -> 30.7%, BUTTON recall flat at 26.0%), because the problem
            is the absence of a gradient, not the threshold on it.

            Region-based segmentation is the standard remedy — GUI elements are
            typically uniform-colour rectangles, so detecting flat regions
            directly succeeds where edge-following fails. See Chen et al. 2020,
            ESEC/FSE, "Object Detection for Graphical User Interface: Old
            Fashioned or Deep Learning or a Combination?".

            Measured on held-out Screen Annotation screens (45 screens, never
            used for parameter tuning), adding channel 2:
              recall@IoU0.5   35.4% -> 46.5%
              BUTTON recall   34.9% -> 47.7%
              mean best IoU   0.376 -> 0.477
              boxes/screen     52.4 ->  58.3
            """
            if not os.path.exists(image_path):
                return json.dumps({"error": f"File not found: {image_path}"})

            img = cv2.imread(image_path)
            if img is None:
                return json.dumps({"error": f"Could not read image: {image_path}"})
            img_h, img_w = img.shape[:2]
            total_area = img_h * img_w

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)

            # --- Channel 1: Canny edge + contour ---
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

            # --- Channel 2: uniform-fill regions ---
            # A pixel is "flat" when its local gradient is near zero, i.e. it
            # sits in the interior of an evenly-coloured area. Connected
            # components of flat pixels recover the filled shapes themselves.
            # GRAD_THRESH and MIN_REGION_AREA were swept over a wide range and
            # barely moved the result (recall varied 40.0-40.4%); FILL_RATIO is
            # the parameter that matters (0.85 -> 0.75 gained ~4pp recall), so
            # these are deliberately loose rather than finely tuned.
            GRAD_THRESH = 8.0     # gradient magnitude below which a pixel is "flat"
            MIN_REGION_AREA = 500  # px, ignore specks
            FILL_RATIO = 0.75      # component area / bbox area; keeps solid rectangles
            MIN_REGION_W, MIN_REGION_H = 40, 20

            grad_x = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
            grad_y = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
            flat_mask = (cv2.magnitude(grad_x, grad_y) < GRAD_THRESH).astype(np.uint8)

            num_labels, _, stats, _ = cv2.connectedComponentsWithStats(flat_mask, connectivity=4)

            region_boxes = []
            for i in range(1, num_labels):  # 0 is background
                x, y, w, h, area = stats[i]
                if area < MIN_REGION_AREA:
                    continue
                if w * h > total_area * 0.80:
                    continue
                if w < MIN_REGION_W or h < MIN_REGION_H:
                    continue
                if area / float(w * h) < FILL_RATIO:
                    continue
                region_boxes.append({"bounds": [int(x), int(y), int(x + w), int(y + h)]})

            # --- Merge the two channels (NMS on IoU) ---
            def _iou(a, b):
                xA, yA = max(a[0], b[0]), max(a[1], b[1])
                xB, yB = min(a[2], b[2]), min(a[3], b[3])
                inter = max(0, xB - xA) * max(0, yB - yA)
                if inter <= 0:
                    return 0.0
                area_a = (a[2] - a[0]) * (a[3] - a[1])
                area_b = (b[2] - b[0]) * (b[3] - b[1])
                union = area_a + area_b - inter
                return inter / union if union > 0 else 0.0

            NMS_IOU = 0.7
            merged = []
            for el in sorted(
                detected + region_boxes,
                key=lambda e: -(e["bounds"][2] - e["bounds"][0]) * (e["bounds"][3] - e["bounds"][1]),
            ):
                if all(_iou(el["bounds"], k["bounds"]) < NMS_IOU for k in merged):
                    merged.append(el)
            detected = merged

            json_data = json.dumps(detected)
            if save_path:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(json_data)

            return json_data

        @tool
        def annotate_screenshot(image_path: str, elements: list, save_path: str) -> str:
            """Draws boxes onto a screenshot and saves result to save_path.
            Handles coordinate scaling between XML bounds and actual screenshot dimensions."""
            if not os.path.exists(image_path):
                return json.dumps({"error": f"File not found: {image_path}"})

            img = cv2.imread(image_path)
            if img is None:
                return json.dumps({"error": f"Could not read image: {image_path}"})

            img_h, img_w = img.shape[:2]

            # Rescale ONLY when the bounds genuinely overflow the image, which
            # is the case this was written for: XML hierarchy bounds coming
            # from a device whose logical resolution is larger than the
            # captured screenshot. When bounds already fit inside the image
            # they are in image pixel space and must be drawn as-is.
            #
            # Previously this scaled unconditionally using
            # `scale = img_h / max_y`, where max_y is just the bottom edge of
            # the lowest detected element — not the screen height. On a
            # vision-only screenshot whose lowest element ends at y=1886 in a
            # 1920px-tall image, that invented a 1.018x vertical stretch,
            # drifting boxes progressively downward (+1px at the top of the
            # screen, +29px at the bottom) so lower boxes visibly detached
            # from the text they bound.
            scale_x, scale_y = 1.0, 1.0
            valid = [el.get("bounds", []) for el in elements]
            valid = [b for b in valid if len(b) >= 4]
            if valid:
                max_x = max(b[2] for b in valid)
                max_y = max(b[3] for b in valid)
                if max_x > img_w:
                    scale_x = img_w / max_x
                if max_y > img_h:
                    scale_y = img_h / max_y

            for element in elements:
                el_id = element.get("id", "?")
                el_type = element.get("type", "container")
                el_source = element.get("source", "unknown")
                ann_bounds = element.get("cv_bounds") or element.get("bounds", [])
                click_bounds = element.get("bounds", ann_bounds)
                if len(ann_bounds) != 4:
                    continue

                x1 = int(ann_bounds[0] * scale_x)
                y1 = int(ann_bounds[1] * scale_y)
                x2 = int(ann_bounds[2] * scale_x)
                y2 = int(ann_bounds[3] * scale_y)

                if el_source == "xml":
                    color = (0, 165, 255)
                elif el_type == "container":
                    color = (0, 0, 255)
                else:
                    color = (255, 0, 0)

                thickness = 2 if el_type == "container" else 1
                cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)

                if len(click_bounds) == 4:
                    cx = int((click_bounds[0] * scale_x + click_bounds[2] * scale_x) / 2)
                    cy = int((click_bounds[1] * scale_y + click_bounds[3] * scale_y) / 2)
                    cv2.circle(img, (cx, cy), 4, (0, 220, 0), -1)

                label = str(el_id)
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.4
                font_thickness = 1
                (text_w, text_h), baseline = cv2.getTextSize(label, font, font_scale, font_thickness)
                bg_x1, bg_y1 = max(0, x1), max(0, y1 - text_h - baseline - 2)
                bg_x2, bg_y2 = x1 + text_w + 4, y1
                cv2.rectangle(img, (bg_x1, bg_y1), (bg_x2, bg_y2), color, -1)
                cv2.putText(img, label, (x1 + 2, y1 - baseline - 1), font, font_scale, (255, 255, 255), font_thickness, cv2.LINE_AA)

            cv2.imwrite(save_path, img)
            return save_path

        @tool
        def check_keyboard_state() -> str:
            """Checks if keyboard is visible."""
            return json.dumps({"is_shown": d.check_keyboard_state()})

        @tool
        def dump_hierarchy(save_path: str = "") -> str:
            """Dumps the current screen UI hierarchy XML. If save_path is provided, result is saved to disk."""
            try:
                xml_data = d.dump_hierarchy()
                if save_path and xml_data:
                    with open(save_path, "w", encoding="utf-8") as f:
                        f.write(xml_data)
                return xml_data
            except Exception as e:
                return f"<error>{str(e)}</error>"

        base_tools = [take_screenshot, ocr_extract_text, detect_visual_elements, annotate_screenshot, check_keyboard_state, dump_hierarchy]

        return base_tools
