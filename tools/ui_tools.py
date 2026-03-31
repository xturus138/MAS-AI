import os
import time
import xml.etree.ElementTree as ET
import re
from datetime import datetime

class UITools:
    def __init__(self, device_session, output_dir):
        # 1. INITIALIZE SESSION AND DIRECTORY
        self.d = device_session 
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def capture_screenshot(self):
        # 2. CAPTURE AND SAVE SCREENSHOT
        if not self.d:
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.output_dir, f"state_{timestamp}.png")
        try:
            self.d.screenshot(filepath)
            return filepath
        except:
            return None

    def get_ui_elements(self):
        # 3. WAKE SCREEN
        if not self.d.info.get('screenOn', True):
            self.d.screen_on()
            time.sleep(2)

        # 4. EXTRACT XML
        try:
            xml_content = self.d.dump_hierarchy()
            return self._parse_xml(xml_content)
        except:
            return []

    def _parse_xml(self, xml_string):
        # 5. PARSE XML NODES
        root = ET.fromstring(xml_string)
        actionable_elements = []
        for node in root.iter('node'):
            attribs = node.attrib
            has_text = attribs.get('text') != ''
            has_desc = attribs.get('content-desc') != ''
            is_clickable = attribs.get('clickable') == 'true'
            
            if has_text or has_desc or is_clickable:
                bounds_str = attribs.get('bounds', '')
                bounds = [int(coord) for coord in re.findall(r'\d+', bounds_str)]
                actionable_elements.append({
                    "class": attribs.get('class', '').split('.')[-1],
                    "text": attribs.get('text', ''),
                    "description": attribs.get('content-desc', ''),
                    "clickable": is_clickable,
                    "bounds": bounds
                })
        return actionable_elements