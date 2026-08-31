import os
import sys
import json
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")

from shared import config
from agents.observer_agent import ObserverAgent
from tools.observer_tools import ObserverTools

sample_img = r"outputs\runs\predefined\2026-08-21\run_1\scenario_01\attempt_001\steps\001\raw.png"
if not os.path.exists(sample_img):
    sample_img = r"outputs\runs\predefined\2026-06-13\run_7\scenario_01\steps\001\raw.png"

print("Using sample image:", sample_img)

from unittest.mock import MagicMock

mock_device = MagicMock()
tools_inst = ObserverTools(mock_device)
tools = tools_inst.get_tools()
observer = ObserverAgent(llm=None, tools=tools)

img = Image.open(sample_img)
w, h = img.size
print(f"Image dimension: {w}x{h}")

print("\nExecuting _detect_widgets_via_omniparser...")
widgets = observer._detect_widgets_via_omniparser(sample_img, w, h)
print(f"OmniParser detected {len(widgets)} elements.\n")

print("\n--- Detected Elements with Text/Labels ---")
for widget in widgets:
    wid = widget.get("id")
    wtype = widget.get("type")
    wtext = widget.get("text", "")
    wbounds = widget.get("bounds")
    wsrc = widget.get("source")
    if wtext:
        print(f'ID {wid:2d}: [{wtype:15s}] (src: {wsrc:14s}) "{wtext}" @ bounds={wbounds}')
