import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Tuple, Optional

class XMLProcessor:
    """Parses, filters, normalizes, and ranks elements from Android XML UI hierarchy dumps."""

    CLASS_ROLE_MAP = {
        "android.widget.Button": "button",
        "android.widget.ImageButton": "icon_button",
        "android.widget.ImageView": "image",
        "android.widget.EditText": "input",
        "android.widget.TextView": "text",
        "android.widget.CheckBox": "checkbox",
        "android.widget.Switch": "switch",
        "android.widget.ToggleButton": "switch",
        "android.widget.RadioButton": "radio",
        "android.widget.Spinner": "dropdown",
        "android.widget.ListView": "list",
        "android.widget.GridView": "grid",
        "android.support.v7.widget.RecyclerView": "list",
        "androidx.recyclerview.widget.RecyclerView": "list",
        "android.view.View": "view",
        "android.widget.ProgressBar": "progress_bar",
        "android.widget.SeekBar": "slider",
        "android.widget.TabWidget": "tab_container",
        "android.widget.HorizontalScrollView": "scroll_container",
        "android.widget.ScrollView": "scroll_container",
    }

    SYSTEM_PACKAGES = {
        "com.android.systemui",
        "com.google.android.inputmethod.latin",
        "com.android.launcher3",
    }

    def __init__(self, screen_width: int = 1080, screen_height: int = 2400):
        self.screen_width = screen_width
        self.screen_height = screen_height

    def parse_bounds(self, bounds_str: str) -> Optional[Tuple[int, int, int, int]]:
        """Parses Android XML bounds string format: [x1,y1][x2,y2]"""
        if not bounds_str:
            return None
        match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", bounds_str)
        if match:
            return tuple(map(int, match.groups()))
        return None

    def get_role_from_class(self, class_name: str, clickable: bool = False) -> str:
        """Determines semantic role from Android class name and interactivity."""
        role = self.CLASS_ROLE_MAP.get(class_name, "view")
        if role == "view" and clickable:
            return "button"
        if role == "image" and clickable:
            return "icon_button"
        return role

    def get_element_label(self, node: ET.Element) -> str:
        """Determines element label using priority hierarchy."""
        text = node.get("text", "").strip()
        if text:
            return text

        content_desc = node.get("content-desc", "").strip()
        if content_desc:
            return content_desc

        resource_id = node.get("resource-id", "").strip()
        if resource_id:
            if "/" in resource_id:
                return resource_id.split("/")[-1]
            return resource_id

        return ""

    def is_visible(self, node: ET.Element, bounds: Tuple[int, int, int, int]) -> bool:
        """Checks if a node is visible based on attributes and bounds."""
        x1, y1, x2, y2 = bounds
        if x1 >= x2 or y1 >= y2:
            return False
        if x2 <= 0 or y2 <= 0:
            return False
        if x1 >= self.screen_width or y1 >= self.screen_height:
            return False

        visible = node.get("visible-to-user", "true") == "true"
        enabled = node.get("enabled", "true") == "true"

        width = x2 - x1
        height = y2 - y1
        if width <= 0 or height <= 0:
            return False

        return visible

    def is_system_ui(self, node: ET.Element, bounds: Tuple[int, int, int, int]) -> bool:
        """Determines if the element belongs to system UI (status/nav bar, keyboard)."""
        package = node.get("package", "")
        if package in self.SYSTEM_PACKAGES:
            return True

        x1, y1, x2, y2 = bounds
        status_bar_h = int(self.screen_height * 0.05)
        if y2 <= status_bar_h:
            return True

        return False

    def is_layout_only(self, node: ET.Element, has_actionable_children: bool = False) -> bool:
        """Determines if node is just a container without semantic meaning or direct actions."""
        class_name = node.get("class", "")
        clickable = node.get("clickable", "false") == "true"
        focusable = node.get("focusable", "false") == "true"
        text = node.get("text", "").strip()
        desc = node.get("content-desc", "").strip()
        res_id = node.get("resource-id", "").strip()

        if clickable or focusable or text or desc or res_id:
            return False

        if "Layout" in class_name or "ViewGroup" in class_name or class_name.endswith("View"):
            return not has_actionable_children

        return True

    def get_screen_region(self, bounds: Tuple[int, int, int, int]) -> str:
        """Categorizes coordinates into screen regions."""
        x1, y1, x2, y2 = bounds
        cy = (y1 + y2) / 2

        if y2 < self.screen_height * 0.15:
            return "header"
        if y1 > self.screen_height * 0.88:
            return "bottom_nav"

        return "main_content"

    def parse_hierarchy(self, xml_str: str) -> List[Dict[str, Any]]:
        """Parses hierarchy XML, cleans, filters, normalizes, and returns structured elements."""
        try:
            root = ET.fromstring(xml_str.encode("utf-8") if isinstance(xml_str, str) else xml_str)
        except Exception as e:
            print(f"[XMLProcessor] XML parsing failed: {e}")
            return []

        elements = []
        raw_elements = []

        def traverse(node, parent_id=None):
            bounds_str = node.get("bounds", "")
            bounds = self.parse_bounds(bounds_str)

            node_id = len(raw_elements) + 1
            node_data = {
                "id": node_id,
                "node": node,
                "parent_id": parent_id,
                "bounds": bounds,
                "children_ids": [],
                "is_actionable": (
                    node.get("clickable", "false") == "true" or
                    node.get("focusable", "false") == "true" or
                    node.get("long-clickable", "false") == "true" or
                    node.get("scrollable", "false") == "true"
                )
            }
            raw_elements.append(node_data)

            if parent_id is not None:
                raw_elements[parent_id - 1]["children_ids"].append(node_id)

            for child in node:
                traverse(child, node_id)

        traverse(root)

        has_actionable_descendant = {}

        def check_actionable_descendants(node_id):
            if node_id in has_actionable_descendant:
                return has_actionable_descendant[node_id]

            node_data = raw_elements[node_id - 1]
            val = node_data["is_actionable"]
            for child_id in node_data["children_ids"]:
                if check_actionable_descendants(child_id):
                    val = True
                    break
            has_actionable_descendant[node_id] = val
            return val

        for r in raw_elements:
            check_actionable_descendants(r["id"])

        for r in raw_elements:
            node = r["node"]
            bounds = r["bounds"]

            if not bounds:
                continue

            if not self.is_visible(node, bounds):
                continue

            if self.is_system_ui(node, bounds):
                continue

            has_act_children = has_actionable_descendant.get(r["id"], False)
            if self.is_layout_only(node, has_act_children):
                continue

            class_name = node.get("class", "")
            text = node.get("text", "").strip()
            desc = node.get("content-desc", "").strip()
            res_id = node.get("resource-id", "").strip()
            clickable = node.get("clickable", "false") == "true"
            focusable = node.get("focusable", "false") == "true"
            long_clickable = node.get("long-clickable", "false") == "true"
            scrollable = node.get("scrollable", "false") == "true"

            role = self.get_role_from_class(class_name, clickable)

            label = self.get_element_label(node)

            res_id_name = res_id.split("/")[-1] if "/" in res_id else res_id
            is_semantic_done_button = res_id_name in {"send_button_group", "send_button", "done_button"}
            if is_semantic_done_button:
                label = "Selesai"
                role = "button"

            is_interactive = clickable or focusable or long_clickable or is_semantic_done_button
            if not label and not is_interactive:
                continue

            x1, y1, x2, y2 = bounds
            cx, cy = int((x1 + x2) / 2), int((y1 + y2) / 2)

            state = {
                "enabled": node.get("enabled", "true") == "true",
                "focused": node.get("focused", "false") == "true",
                "checked": node.get("checked", "false") == "true",
                "selected": node.get("selected", "false") == "true",
                "scrollable": scrollable,
                "password": node.get("password", "false") == "true",
            }

            elements.append({
                "raw_id": r["id"],
                "label": label,
                "role": role,
                "bounds": [x1, y1, x2, y2],
                "cv_bounds": [x1, y1, x2, y2],
                "center": [cx, cy],
                "actionable": is_interactive,
                "state": state,
                "source": "xml",
                "group": self.get_screen_region(bounds),
                "class": class_name,
                "resource_id": res_id
            })

        elements = self.deduplicate_elements(elements)

        ranked_elements = self.rank_elements(elements)

        for idx, el in enumerate(ranked_elements, start=1):
            el["id"] = idx

        return ranked_elements

    def deduplicate_elements(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Removes overlapping/nested elements with identical bounds or text duplicates."""
        if not elements:
            return []

        def get_area(el):
            b = el["bounds"]
            return (b[2] - b[0]) * (b[3] - b[1])

        elements.sort(key=get_area, reverse=True)
        unique = []

        for el in elements:
            b1 = el["bounds"]
            dup = False
            for u in unique:
                b2 = u["bounds"]
                is_overlap = (
                    abs(b1[0] - b2[0]) < 10 and
                    abs(b1[1] - b2[1]) < 10 and
                    abs(b1[2] - b2[2]) < 10 and
                    abs(b1[3] - b2[3]) < 10
                )
                if is_overlap:
                    if not u["label"] and el["label"]:
                        u.update(el)
                    dup = True
                    break
            if not dup:
                unique.append(el)

        return unique

    def rank_elements(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Ranks elements based on priority for decision making:
        1. Actionable & Focused / Selected (urgent inputs/buttons)
        2. Actionable & Input fields (text boxes)
        3. Other Actionable elements (buttons, switches, clickable images)
        4. Static labeled elements / Titles
        5. General passive texts
        """
        def rank_score(el):
            score = 0
            if el["actionable"]:
                score += 1000
                if el["role"] == "input":
                    score += 500
                if el["state"].get("focused") or el["state"].get("selected"):
                    score += 300

            bounds = el["bounds"]
            pos_score = (self.screen_height - bounds[1]) / self.screen_height * 100

            if el["label"]:
                score += 200

            if el["role"] in ["list", "grid"]:
                score += 100

            return score + pos_score

        return sorted(elements, key=rank_score, reverse=True)

    def evaluate_confidence(self, elements: List[Dict[str, Any]], xml_str: str) -> Tuple[float, str]:
        """Evaluates whether parsed XML output is sufficient or triggers fallback.
        Returns (confidence_score, reason_if_low).
        """
        if not xml_str or len(xml_str.strip()) < 50:
            return 0.0, "Empty or extremely short XML hierarchy dump"

        if not elements:
            return 0.0, "No valid elements parsed after filtering"

        actionable = [el for el in elements if el["actionable"]]
        inputs = [el for el in elements if el["role"] == "input"]

        is_webview = "WebView" in xml_str or "webkit.WebView" in xml_str

        if is_webview and len(actionable) <= 2:
            return 0.3, "WebView detected with minimal actionable elements. Custom canvas/hybrid rendering likely."

        if len(actionable) == 0:
            return 0.1, "No actionable (clickable/focusable) elements detected in hierarchy."

        if len(xml_str) > 200000 and len(elements) < 3:
            return 0.4, "Large XML structure but parsed less than 3 components. Layout extraction failed."

        return 1.0, ""
