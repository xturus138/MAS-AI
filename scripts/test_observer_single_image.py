import os
import sys
import json
import cv2
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from shared import config
from agents.observer_agent import ObserverAgent
from tools.observer_tools import ObserverTools
from unittest.mock import MagicMock

# ── OUTPUT TEST FOLDER SETUP ──────────────────────────────────────────────────
TEST_OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "outputs",
    "test_observer_inspection",
)
os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)

# ── SAMPLE IMAGE ──────────────────────────────────────────────────────────────
sample_img = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "outputs",
    "runs",
    "predefined",
    "2026-08-21",
    "run_1",
    "scenario_01",
    "attempt_001",
    "steps",
    "001",
    "raw.png",
)

if not os.path.exists(sample_img):
    sample_img = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "outputs",
        "runs",
        "predefined",
        "2026-06-13",
        "run_7",
        "scenario_01",
        "steps",
        "001",
        "raw.png",
    )

print("=" * 65)
print("  OBSERVER INSPECTION TEST RUNNER")
print("=" * 65)
print(f"[*] Input Image : {sample_img}")
print(f"[*] Output Dir  : {TEST_OUTPUT_DIR}\n")

# Copy raw image to inspection folder
raw_save_path = os.path.join(TEST_OUTPUT_DIR, "raw_image.png")
annotated_save_path = os.path.join(TEST_OUTPUT_DIR, "annotated_bounding_boxes.png")
json_save_path = os.path.join(TEST_OUTPUT_DIR, "detected_widgets.json")
ocr_save_path = os.path.join(TEST_OUTPUT_DIR, "ocr_extracted.json")

# Initialize Observer
mock_device = MagicMock()
tools_inst = ObserverTools(mock_device)
tools = tools_inst.get_tools()
observer = ObserverAgent(llm=None, tools=tools)

img = Image.open(sample_img)
w, h = img.size
img.save(raw_save_path)
print(f"[*] Image Dimension: {w} x {h} px")

# 1. Run OmniParser Detection
print("[*] Running OmniParser detection (YOLOv8 + EasyOCR + Florence-2)...")
widgets = observer._detect_widgets_via_omniparser(
    sample_img, w, h, ocr_path=ocr_save_path
)
print(f"[+] Detected {len(widgets)} elements.\n")

# 2. Draw Visual Bounding Boxes with Labels & IDs
print("[*] Generating visual annotated screenshot with bounding boxes...")
annotate_fn = tools[3]
annotate_fn.invoke({
    "image_path": sample_img,
    "elements": widgets,
    "save_path": annotated_save_path,
})
print(f"[+] Saved visual annotated image to: {annotated_save_path}")

# 3. Save Detected Widgets JSON
with open(json_save_path, "w", encoding="utf-8") as f:
    json.dump(widgets, f, indent=2, ensure_ascii=False)
print(f"[+] Saved structured detection JSON to: {json_save_path}\n")

# 4. Print Summary Table
print("-" * 65)
print(f"{'ID':<4} | {'TYPE':<16} | {'BOUNDS [x1,y1,x2,y2]':<22} | {'LABEL / TEXT'}")
print("-" * 65)
for widget in widgets:
    wid = widget.get("id")
    wtype = widget.get("type", "")
    wtext = widget.get("text", "").replace("\n", " ")
    wbounds = str(widget.get("bounds", []))
    if len(wtext) > 30:
        wtext = wtext[:27] + "..."
    print(f"{wid:<4} | {wtype:<16} | {wbounds:<22} | {wtext}")
print("-" * 65)
print(f"\n[OK] Inspection complete! Check folder:\n  -> {TEST_OUTPUT_DIR}")
