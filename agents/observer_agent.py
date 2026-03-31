class ObserverAgent:
    def __init__(self, device_tools):
        # 1. INITIALIZE OBSERVER TOOLS
        self.tools = device_tools

    def observe(self):
        # 2. CAPTURE VISUAL STATE
        screenshot_path = self.tools.capture_screenshot()
        
        # 3. CAPTURE STRUCTURAL STATE (XML/OCR)
        ui_elements = self.tools.get_ui_elements()
        
        # 4. FILTER INTERACTIVE ELEMENTS
        interactive_elements = []
        for el in ui_elements:
            if el['clickable'] or 'EditText' in el['class'] or 'Button' in el['class']:
                interactive_elements.append({
                    "class": el['class'],
                    "label": el['text'] or el['description'] or "(no label)",
                    "bounds": el['bounds']
                })

        # 5. RETURN PERCEPTION STATE
        return {
            "screenshot_path": screenshot_path,
            "elements": interactive_elements
        }