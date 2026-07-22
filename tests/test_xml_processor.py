import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.append(".")
from core.utils.xml_processor import XMLProcessor

class TestXMLProcessor(unittest.TestCase):
    def setUp(self):
        self.processor = XMLProcessor(screen_width=1080, screen_height=2400)
        self.sample_xml = """<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>
        <hierarchy rotation="0">
            <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" bounds="[0,0][1080,2400]" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false">
                <!-- System UI status bar -->
                <node index="0" text="" resource-id="com.android.systemui:id/status_bar" class="android.view.View" package="com.android.systemui" bounds="[0,0][1080,120]" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" />

                <!-- Screen content -->
                <node index="1" text="" resource-id="com.example.app:id/content" class="android.widget.RelativeLayout" package="com.example.app" bounds="[0,120][1080,2200]" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false">
                    <!-- Title Header -->
                    <node index="0" text="My Application" resource-id="com.example.app:id/title" class="android.widget.TextView" package="com.example.app" bounds="[40,160][400,240]" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" />

                    <!-- Form input -->
                    <node index="1" text="" resource-id="com.example.app:id/username_input" class="android.widget.EditText" package="com.example.app" bounds="[100,400][980,500]" clickable="true" enabled="true" focusable="true" focused="true" scrollable="false" />

                    <!-- Action Button -->
                    <node index="2" text="Submit Data" resource-id="com.example.app:id/submit_btn" class="android.widget.Button" package="com.example.app" bounds="[300,600][780,720]" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" />

                    <!-- Icon image button (clickable) -->
                    <node index="3" text="" content-desc="Settings Gear" resource-id="com.example.app:id/settings_icon" class="android.widget.ImageView" package="com.example.app" bounds="[950,150][1030,230]" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" />
                </node>

                <!-- Navigation Bar at bottom -->
                <node index="2" text="" resource-id="com.android.systemui:id/navigation_bar" class="android.view.View" package="com.android.systemui" bounds="[0,2200][1080,2400]" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" />
            </node>
        </hierarchy>
        """

    def test_bounds_parsing(self):
        bounds = self.processor.parse_bounds("[100,200][300,400]")
        self.assertEqual(bounds, (100, 200, 300, 400))

        invalid = self.processor.parse_bounds("")
        self.assertIsNone(invalid)

    def test_semantic_role(self):
        self.assertEqual(self.processor.get_role_from_class("android.widget.Button"), "button")
        self.assertEqual(self.processor.get_role_from_class("android.widget.EditText"), "input")
        self.assertEqual(self.processor.get_role_from_class("android.widget.ImageView", clickable=True), "icon_button")
        self.assertEqual(self.processor.get_role_from_class("android.view.View", clickable=True), "button")

    def test_label_priority(self):
        node = ET.Element("node", text="Hello", **{"content-desc": "Desc", "resource-id": "com.app:id/btn"})
        self.assertEqual(self.processor.get_element_label(node), "Hello")

        node2 = ET.Element("node", text="", **{"content-desc": "Desc", "resource-id": "com.app:id/btn"})
        self.assertEqual(self.processor.get_element_label(node2), "Desc")

        node3 = ET.Element("node", text="", **{"content-desc": "", "resource-id": "com.app:id/btn"})
        self.assertEqual(self.processor.get_element_label(node3), "btn")

    def test_hierarchy_parsing(self):
        elements = self.processor.parse_hierarchy(self.sample_xml)
        self.assertTrue(len(elements) > 0)

        for el in elements:
            self.assertNotEqual(el["resource_id"], "com.android.systemui:id/status_bar")
            self.assertNotEqual(el["resource_id"], "com.android.systemui:id/navigation_bar")

        input_el = next(el for el in elements if el["resource_id"] == "com.example.app:id/username_input")
        self.assertEqual(input_el["role"], "input")
        self.assertTrue(input_el["state"]["focused"])

        button_el = next(el for el in elements if el["resource_id"] == "com.example.app:id/submit_btn")
        self.assertEqual(button_el["role"], "button")
        self.assertEqual(button_el["label"], "Submit Data")

        icon_el = next(el for el in elements if el["resource_id"] == "com.example.app:id/settings_icon")
        self.assertEqual(icon_el["role"], "icon_button")
        self.assertEqual(icon_el["label"], "Settings Gear")

    def test_element_ranking(self):
        elements = self.processor.parse_hierarchy(self.sample_xml)
        first_el = elements[0]
        self.assertTrue(first_el["actionable"])
        self.assertEqual(first_el["role"], "input")

    def test_confidence_scoring(self):
        elements = self.processor.parse_hierarchy(self.sample_xml)
        score, reason = self.processor.evaluate_confidence(elements, self.sample_xml)
        self.assertEqual(score, 1.0)

        score_low, reason_low = self.processor.evaluate_confidence([], "")
        self.assertEqual(score_low, 0.0)

if __name__ == "__main__":
    unittest.main()
