import os
import xml.etree.ElementTree as ET
import re
from datetime import datetime

# STEP 1 ALAT PERSEPSI KHUSUS OBSERVER AGENT //
class ObserverTools:
    def __init__(self, device_session, output_dir):
        self.d = device_session
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def capture_state(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.output_dir, f"state_{timestamp}.png")
        self.d.screenshot(filepath)
        
        xml_content = self.d.dump_hierarchy()
        root = ET.fromstring(xml_content)
        elements = []
        for node in root.iter('node'):
            attribs = node.attrib
            if attribs.get('clickable') == 'true' or 'EditText' in attribs.get('class', ''):
                bounds = [int(x) for x in re.findall(r'\d+', attribs.get('bounds', ''))]
                label = attribs.get('text') or attribs.get('content-desc') or "unknown"
                elements.append(f"[{bounds[0]},{bounds[1]}] {attribs.get('class')}: '{label}'")
        
        return filepath, "\n".join(elements[:20])