# tools/ui_tools.py
import os
import time
import xml.etree.ElementTree as ET
import re
from datetime import datetime

class UITools:
    def __init__(self, device_session, output_dir):
        """
        Menerima koneksi perangkat (device_session) yang sudah aktif,
        sehingga tidak perlu u2.connect() lagi di sini.
        """
        self.d = device_session 
        self.output_dir = output_dir
        
        # Buat folder output jika belum ada
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def capture_screenshot(self):
        """Mengambil screenshot menggunakan koneksi yang diberikan."""
        if not self.d:
            print("[!] Error: Tidak ada sesi perangkat aktif.")
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(self.output_dir, f"state_{timestamp}.png")
        
        try:
            self.d.screenshot(filepath)
            return filepath
        except Exception as e:
            print(f"[!] Gagal mengambil screenshot: {e}")
            return None

    def get_ui_elements(self):
        """Mengekstrak dan mem-parsing UI XML menjadi list dictionary."""
        if not self.d:
            return []

        # Pastikan layar menyala menggunakan sesi yang ada
        if not self.d.info.get('screenOn', True):
            print("[*] Layar mati. Menyalakan layar...")
            self.d.screen_on()
            time.sleep(2)

        try:
            xml_content = self.d.dump_hierarchy()
            return self._parse_xml(xml_content)
        except Exception as e:
            print(f"[!] Gagal mengekstrak UI: {e}")
            return []

    def _parse_xml(self, xml_string):
        """Logika internal untuk mem-parsing string XML."""
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
                
                element_data = {
                    "class": attribs.get('class', '').split('.')[-1],
                    "text": attribs.get('text', ''),
                    "description": attribs.get('content-desc', ''),
                    "clickable": is_clickable,
                    "bounds": bounds,
                    "resource_id": attribs.get('resource-id', '')
                }
                actionable_elements.append(element_data)
                
        return actionable_elements