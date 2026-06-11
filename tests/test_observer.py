import os
import sys
import glob
import json
import cv2

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from tools.observer_tools import ObserverTools


class MockDeviceClient:
    def screenshot(self, target_path):
        pass

    def check_keyboard_state(self):
        return False


def main():
    print("Testing Observer Vision Pipeline on local image files...")

    # Extensions to look for
    extensions = ("*.png", "*.jpg", "*.jpeg", "*.webp")
    image_files = []

    # Change CWD to the script's directory to find local files
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    for ext in extensions:
        image_files.extend([f for f in glob.glob(ext) if not f.startswith("test_out_")])

    if not image_files:
        print("No source image files found in the test directory.")
        print("Please copy a screenshot (e.g., 'screenshot.jpeg') to the 'test' folder and run this script again.")
        return

    # Build tools from observer_tools.py only — no agent dependency
    device        = MockDeviceClient()
    tools_wrapper = ObserverTools(device)
    tools         = tools_wrapper.get_tools()

    # Resolve tools by name so renaming/adding tools in observer_tools.py is reflected automatically
    ocr_tool      = next(t for t in tools if t.name == "ocr_extract_text")
    cv_tool       = next(t for t in tools if t.name == "detect_visual_elements")
    annotate_tool = next(t for t in tools if t.name == "annotate_screenshot")

    # Ensure output directory exists
    output_test_dir = "output_test"
    os.makedirs(output_test_dir, exist_ok=True)

    for img_path in image_files:
        print(f"\n[{img_path}] Processing...")

        base_name, ext = os.path.splitext(img_path)
        ocr_out = os.path.join(output_test_dir, f"test_out_ocr_{base_name}.json")
        cv_out  = os.path.join(output_test_dir, f"test_out_cv_{base_name}.json")
        ann_out = os.path.join(output_test_dir, f"test_out_annotated_{base_name}{ext}")

        # ── OCR ───────────────────────────────────────────────────────────────
        print(f"[{img_path}] Running OCR...")
        ocr_raw = ocr_tool.invoke({"image_path": img_path, "save_path": ocr_out})

        # ── CV detection ──────────────────────────────────────────────────────
        print(f"[{img_path}] Running CV detection...")
        cv_raw = cv_tool.invoke({"image_path": img_path, "save_path": cv_out})

        try:
            ocr_elements = json.loads(ocr_raw)
            cv_elements  = json.loads(cv_raw)
        except Exception as e:
            print(f"[{img_path}] Failed to parse JSON: {e}")
            continue

        # ── Element count summary ─────────────────────────────────────────────
        print(f"[{img_path}] OCR elements: {len(ocr_elements)}  |  CV elements: {len(cv_elements)}")

        # ── Annotate using raw CV elements (no merge step) ───────────────────
        # Assign temporary IDs so the annotator can label each box
        for idx, el in enumerate(cv_elements, start=1):
            el.setdefault("id", idx)
            el.setdefault("type", "container")

        img_cv       = cv2.imread(img_path)
        image_height = img_cv.shape[0] if img_cv is not None else 1920
        print(f"[{img_path}] Image height: {image_height}px")

        print(f"[{img_path}] Annotating screenshot...")
        annotate_tool.invoke({
            "image_path": img_path,
            "elements":   cv_elements,
            "save_path":  ann_out
        })

        print(f"[{img_path}] Done! Annotated image saved to: {ann_out}")

if __name__ == '__main__':
    main()
