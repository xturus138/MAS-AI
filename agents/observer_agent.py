import base64
import json
import os
import re
import cv2
from langchain_core.prompts import ChatPromptTemplate
from langgraph.types import Command
from core.models.state import AgentState
from core.ports.llm_port import ILLMClient
from core.utils.toons_helper import compress_and_report, prune_history_by_tokens
from shared.prompts.observer_prompts import SYSTEM_PROMPT, FEW_SHOT_EXAMPLES
from shared import config
from core.utils.process_logger import LogLevel as _LL


class ObserverAgent:
    def __init__(self, llm: ILLMClient, tools: list, memory=None, logger=None, monitor=None):
        self.llm = llm
        self.take_screenshot = tools[0]
        self.ocr_extract_text = tools[1]
        self.detect_visual_elements = tools[2]
        self.annotate_screenshot = tools[3]
        self.check_keyboard_state = tools[4]
        self.dump_hierarchy = tools[5]
        # Optional: OmniParser unified vision backend (index 6 now)
        self.parse_screen_omniparser = tools[6] if len(tools) > 6 else None
        self.memory = memory
        self.logger = logger
        self.monitor = monitor

    def _encode_image(self, image_path: str, max_height: int = 720) -> str:
        img = cv2.imread(image_path)
        if img is None:
            return ""

        h, w = img.shape[:2]
        if h > max_height:
            scale = max_height / h
            new_w = int(w * scale)
            img = cv2.resize(img, (new_w, max_height), interpolation=cv2.INTER_AREA)

        success, buffer = cv2.imencode(".webp", img, [int(cv2.IMWRITE_WEBP_QUALITY), 70])
        if not success:
            success, buffer = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
        if not success:
            return ""

        return base64.b64encode(buffer).decode("utf-8")

    def _merge_ocr_blocks(self, ocr_elements: list) -> list:
        if not ocr_elements:
            return []

        sorted_ocr = sorted(ocr_elements, key=lambda x: (x["bounds"][1], x["bounds"][0]))

        merged = []
        if not sorted_ocr:
            return []

        current = sorted_ocr[0]

        for next_el in sorted_ocr[1:]:
            curr_b = current["bounds"]
            next_b = next_el["bounds"]

            y_overlap = min(curr_b[3], next_b[3]) - max(curr_b[1], next_b[1])
            h_dist = next_b[0] - curr_b[2]

            height = curr_b[3] - curr_b[1]
            if y_overlap > height * 0.5 and h_dist < 40:
                current["bounds"] = [
                    min(curr_b[0], next_b[0]),
                    min(curr_b[1], next_b[1]),
                    max(curr_b[2], next_b[2]),
                    max(curr_b[3], next_b[3])
                ]
                current["text"] = current.get("text", "") + " " + next_el.get("text", "")
            else:
                merged.append(current)
                current = next_el

        merged.append(current)
        return merged

    def _group_keyboard_elements(self, elements: list, image_height: int, is_kb_shown: bool) -> list:
        if not is_kb_shown:
            return elements

        kb_threshold_y = image_height * 0.65  # fix: was 0.50, too aggressive for screens with bottom sheets

        kb_candidates = []
        non_kb_elements = []

        for el in elements:
            b = el.get("bounds", [0, 0, 0, 0])
            cy = (b[1] + b[3]) / 2

            if cy > kb_threshold_y:
                kb_candidates.append(el)
            else:
                non_kb_elements.append(el)

        if kb_candidates:
            all_x1 = min(el["bounds"][0] for el in kb_candidates)
            all_y1 = min(el["bounds"][1] for el in kb_candidates)
            all_x2 = max(el["bounds"][2] for el in kb_candidates)
            all_y2 = max(el["bounds"][3] for el in kb_candidates)

            keyboard_el = {
                "bounds": [all_x1, all_y1, all_x2, all_y2],
                "cv_bounds": [all_x1, all_y1, all_x2, all_y2],
                "text": "On-Screen Keyboard",
                "type": "container"
            }
            non_kb_elements.append(keyboard_el)
            return non_kb_elements

        return elements

    def _merge_and_filter(self, cv_elements: list, ocr_elements: list, image_height: int, is_kb_shown: bool = False) -> list:
        status_bar_threshold = image_height * 0.05

        ocr_elements = self._merge_ocr_blocks(ocr_elements)

        filtered_cv = [
            el for el in cv_elements
            if el.get("bounds", [0, 0])[1] >= status_bar_threshold
        ]
        filtered_ocr = [
            el for el in ocr_elements
            if el.get("bounds", [0, 0])[1] >= status_bar_threshold
        ]

        def compute_iou(boxA, boxB):
            xA = max(boxA[0], boxB[0])
            yA = max(boxA[1], boxB[1])
            xB = min(boxA[2], boxB[2])
            yB = min(boxA[3], boxB[3])
            inter_w = max(0, xB - xA)
            inter_h = max(0, yB - yA)
            inter_area = inter_w * inter_h
            if inter_area == 0:
                return 0.0
            areaA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
            areaB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
            union_area = areaA + areaB - inter_area
            return inter_area / union_area if union_area > 0 else 0.0

        def boxes_nearby(boxA, boxB, threshold=25):
            cx_a = (boxA[0] + boxA[2]) / 2
            cy_a = (boxA[1] + boxA[3]) / 2
            cx_b = (boxB[0] + boxB[2]) / 2
            cy_b = (boxB[1] + boxB[3]) / 2
            distance = ((cx_a - cx_b) ** 2 + (cy_a - cy_b) ** 2) ** 0.5
            return distance < threshold

        merged = []
        used_ocr = set()

        for cv_el in filtered_cv:
            cv_bounds = cv_el["bounds"]
            matched_text = []
            matched_ocr_bounds = []

            for ocr_idx, ocr_el in enumerate(filtered_ocr):
                if ocr_idx in used_ocr:
                    continue
                ocr_bounds = ocr_el["bounds"]

                is_inside = (ocr_bounds[0] >= cv_bounds[0] - 10 and
                             ocr_bounds[1] >= cv_bounds[1] - 10 and
                             ocr_bounds[2] <= cv_bounds[2] + 10 and
                             ocr_bounds[3] <= cv_bounds[3] + 10)

                if is_inside or compute_iou(cv_bounds, ocr_bounds) > 0.1 or boxes_nearby(cv_bounds, ocr_bounds):
                    matched_text.append(ocr_el.get("text", ""))
                    matched_ocr_bounds.append(ocr_bounds)
                    used_ocr.add(ocr_idx)

            if matched_ocr_bounds:
                all_x1 = min(b[0] for b in matched_ocr_bounds)
                all_y1 = min(b[1] for b in matched_ocr_bounds)
                all_x2 = max(b[2] for b in matched_ocr_bounds)
                all_y2 = max(b[3] for b in matched_ocr_bounds)
                click_bounds = [all_x1, all_y1, all_x2, all_y2]
            else:
                click_bounds = cv_bounds

            entry = {
                "bounds": click_bounds,
                "cv_bounds": cv_bounds,
                "text": " ".join(matched_text) if matched_text else "",
                "type": "container"
            }
            merged.append(entry)

        for ocr_idx, ocr_el in enumerate(filtered_ocr):
            if ocr_idx not in used_ocr:
                text = ocr_el.get("text", "").strip()
                if len(text) < 2 or len(text) > 100:
                    continue

                b = ocr_el["bounds"]
                w, h = b[2] - b[0], b[3] - b[1]
                if h > 0 and w / h < 0.2:
                    continue

                merged.append({
                    "bounds": ocr_el["bounds"],
                    "text": text,
                    "type": "text_stub"
                })

        merged = self._group_keyboard_elements(merged, image_height, is_kb_shown)

        final_widget_set = []
        for idx, el in enumerate(merged, start=1):
            el["id"] = idx
            el["class"] = "Interactive" if el["type"] == "container" else "StaticText"
            el["resource_id"] = "none"
            final_widget_set.append(el)

        return final_widget_set

    def _detect_stagnation(self, current_summary: str, current_step: int, prev_stagnation: int) -> int:
        """Compare current UI summary against the last episodic observer entry to detect stagnation."""
        if self.memory is None:
            return prev_stagnation

        last_obs = self.memory.episodic.last_by_actor("observer")
        if last_obs is None:
            return 0

        prev_summary = last_obs.details or ""
        if current_summary and prev_summary and current_summary == prev_summary:
            return prev_stagnation + 1
        return 0

    def _filter_omniparser_widgets(self, elements: list, image_width: int, image_height: int) -> list:
        """
        Post-process OmniParser output to remove card-container background boxes
        and merge horizontally fragmented text elements.

        Two passes:
        1. Drop any element whose area exceeds MAX_AREA_RATIO of the screen AND
           has at least MIN_CHILDREN smaller elements contained within it — these
           are YOLO-detected card/container backgrounds, not actionable items.
        2. Merge text_stub elements that sit on the same row and are horizontally
           close, so split tokens like ["Notulensi Rapat", "Jaist"] become one.
        """
        if not elements:
            return elements

        total_area = image_width * image_height
        MAX_AREA_RATIO = 0.12   # card containers are typically 9-11 % of screen
        MIN_CHILDREN   = 1      # drop the large box only if ≥1 smaller box is inside
        EDGE_MARGIN    = 5      # pixels from screen edge to consider an element as clipped

        # Regex to detect SVG path data mistakenly read by OCR as text
        _SVG_PATH_RE = re.compile(r'^[MmCcLlZzHhVvAaSsQqTt][\.\d,\s\-]+', re.ASCII)

        def _is_svg_noise(text: str) -> bool:
            """Return True if text looks like an SVG path command or graphic artifact."""
            t = text.strip()
            if not t:
                return False
            if _SVG_PATH_RE.match(t):
                return True
            # String that is mostly non-alphanumeric (e.g. "M0,0L0,5 4.5,5z")
            alnum = sum(c.isalnum() for c in t)
            return len(t) > 3 and alnum / len(t) < 0.3

        def _is_edge_clipped(b: list) -> bool:
            """Return True if a small element is clipped at the screen edge."""
            is_clipped = (b[0] <= EDGE_MARGIN or b[2] >= image_width - EDGE_MARGIN)
            is_small   = (b[2] - b[0]) < 30
            return is_clipped and is_small

        def _area(b):
            return max(0, b[2] - b[0]) * max(0, b[3] - b[1])

        def _contained(inner, outer, margin=15):
            return (inner[0] >= outer[0] - margin and
                    inner[1] >= outer[1] - margin and
                    inner[2] <= outer[2] + margin and
                    inner[3] <= outer[3] + margin)

        # ── Pass 1: remove large card-container backgrounds ───────────────────
        big, normal = [], []
        for el in elements:
            b = el.get("bounds", [0, 0, 0, 0])
            if _area(b) / total_area > MAX_AREA_RATIO:
                big.append(el)
            else:
                normal.append(el)

        kept = list(normal)
        for big_el in big:
            big_b = big_el.get("bounds", [0, 0, 0, 0])
            children = sum(1 for el in normal if _contained(el.get("bounds", [0,0,0,0]), big_b))
            if children < MIN_CHILDREN:
                kept.append(big_el)  # no children → might be a real large widget, keep it

        # ── Pass 1b: remove SVG path noise and edge-clipped micro-elements ─────
        before_noise = len(kept)
        kept = [
            el for el in kept
            if not _is_svg_noise(el.get("text", ""))
            and not _is_edge_clipped(el.get("bounds", [0, 0, 0, 0]))
        ]
        if len(kept) != before_noise:
            removed = before_noise - len(kept)
            print(f"[Observer] Noise filter removed {removed} SVG/edge-clipped element(s)")

        # ── Pass 1c: remove narrow dangling text fragments ──────────────────────
        # OmniParser sometimes produces orphan tokens like a standalone date part
        # (e.g. "1", "Mei", ".") split away from their parent text block.
        # Detection rule is purely geometric: a text_stub is a dangling fragment if
        #   - it is non-interactive (text_stub type), AND
        #   - its bounding box width is very small (< 6% of screen width), AND
        #   - its text is very short (<= 3 characters).
        # No word lists, no locale assumptions — works for any language/domain.
        before_frag = len(kept)
        narrow_threshold = image_width * 0.06
        kept = [
            el for el in kept
            if not (
                el.get("type") == "text_stub"
                and len(el.get("text", "").strip()) <= 3
                and (el.get("bounds", [0, 0, 0, 0])[2] - el.get("bounds", [0, 0, 0, 0])[0]) < narrow_threshold
            )
        ]
        if len(kept) != before_frag:
            removed = before_frag - len(kept)
            print(f"[Observer] Fragment filter removed {removed} narrow text stub(s)")

        # ── Pass 2: merge horizontally adjacent text_stub elements ────────────
        text_stubs   = [el for el in kept if el.get("type") == "text_stub"]
        other_els    = [el for el in kept if el.get("type") != "text_stub"]

        text_stubs.sort(key=lambda e: (e["bounds"][1], e["bounds"][0]))

        merged_stubs = []
        if text_stubs:
            cur = dict(text_stubs[0])
            for nxt in text_stubs[1:]:
                cb, nb = cur["bounds"], nxt["bounds"]
                cur_h       = cb[3] - cb[1]
                y_overlap   = min(cb[3], nb[3]) - max(cb[1], nb[1])
                h_gap       = nb[0] - cb[2]    # horizontal gap between boxes
                same_row    = y_overlap > cur_h * 0.4
                close_enough = h_gap < 40
                if same_row and close_enough:
                    cur["bounds"] = [
                        min(cb[0], nb[0]), min(cb[1], nb[1]),
                        max(cb[2], nb[2]), max(cb[3], nb[3]),
                    ]
                    cur["cv_bounds"] = cur["bounds"]
                    cur["text"] = (cur.get("text", "") + " " + nxt.get("text", "")).strip()
                else:
                    merged_stubs.append(cur)
                    cur = dict(nxt)
            merged_stubs.append(cur)

        return other_els + merged_stubs

    def _log(self, msg: str, detail: str = "", level=None):
        if self.logger is not None:
            from core.utils.process_logger import LogLevel
            lvl = level if level is not None else _LL.INFO
            self.logger.log("OBSERVER", msg, detail, level=lvl)

    def _generate_compact_xml_tree(
        self,
        widgets: list,
        scenario_desc: str = "",
        navigation_context: str = ""
    ) -> str:
        """Generate prioritized compact semantic UI tree from XML widgets.

        Prioritization order:
        1. Dialogs, errors, alerts (highest priority)
        2. Selected/focused elements
        3. Clickable interactive elements (buttons, inputs)
        4. Navigation controls (back, menu, tabs)
        5. List items with content
        6. Visible labels and text
        7. Other structural elements (summarized)
        """
        if not widgets:
            return "UI Tree: (no elements)"

        # Categorize widgets by priority
        dialogs_errors = []
        selected_focused = []
        interactive = []
        navigation = []
        list_items = []
        labeled_static = []
        other = []

        # Keywords for categorization
        dialog_keywords = {"dialog", "alert", "popup", "modal", "error", "warning", "confirm", "permission"}
        nav_keywords = {"back", "menu", "nav", "toolbar", "tab", "home", "close", "exit"}
        list_container_keywords = {"list", "recycler", "scroll", "item"}

        for w in widgets:
            role = w.get("role", "view")
            label = (w.get("label", "") or "").lower()
            is_actionable = w.get("actionable", False)
            state = w.get("state", {})
            is_selected = state.get("selected", False) or state.get("focused", False)
            res_id = (w.get("resource_id", "") or "").lower()

            # Check for dialogs/errors first
            if any(k in label or k in res_id for k in dialog_keywords):
                dialogs_errors.append(w)
                continue

            # Selected/focused elements
            if is_selected:
                selected_focused.append(w)
                continue

            # Navigation controls
            if any(k in label or k in res_id for k in nav_keywords):
                navigation.append(w)
                continue

            # Interactive elements (buttons, inputs, etc.)
            if is_actionable:
                if role in {"button", "icon_button", "input", "checkbox", "switch", "radio", "dropdown"}:
                    interactive.append(w)
                    continue

            # List items (elements in scrollable containers with content)
            if role in {"list", "grid"} or (is_actionable and any(k in res_id for k in list_container_keywords)):
                if label:  # Only if they have content
                    list_items.append(w)
                    continue

            # Static labeled elements
            if label and len(label) > 0:
                labeled_static.append(w)
                continue

            # Everything else
            other.append(w)

        # Build compact tree sections
        sections = []
        element_count = 0
        max_elements = 40  # Limit total for LLM context

        def format_element(w: dict, prefix: str = "") -> str:
            role = w.get("role", "view")
            label = w.get("label", "") or ""
            if role == "input" and not label:
                label = "<empty>"
            # Truncate long labels
            if len(label) > 50:
                label = label[:47] + "..."
            is_actionable = "⚡" if w.get("actionable") else "○"
            state_markers = []
            state = w.get("state", {})
            if state.get("selected"):
                state_markers.append("★")
            if state.get("focused"):
                state_markers.append("▸")
            if state.get("checked"):
                state_markers.append("✓")
            state_str = "".join(state_markers)
            return f"{prefix}[{w.get('id', '?'):2}] {is_actionable} {role:12} | {label}" + (f" {state_str}" if state_str else "")

        # Section 1: Critical (dialogs/errors)
        if dialogs_errors:
            sections.append("\n⚠️ DIALOGS/ALERTS:")
            for w in dialogs_errors[:5]:
                sections.append(format_element(w, "  "))
                element_count += 1

        # Section 2: Selected/Focused
        if selected_focused:
            sections.append("\n⭐ SELECTED/FOCUSED:")
            for w in selected_focused[:5]:
                sections.append(format_element(w, "  "))
                element_count += 1

        # Section 3: Interactive Elements
        if interactive:
            sections.append("\n⚡ INTERACTIVE:")
            remaining = max_elements - element_count
            for w in interactive[:min(15, remaining)]:
                sections.append(format_element(w, "  "))
                element_count += 1

        # Section 4: Navigation
        if navigation:
            sections.append("\n🧭 NAVIGATION:")
            remaining = max_elements - element_count
            for w in navigation[:min(5, remaining)]:
                sections.append(format_element(w, "  "))
                element_count += 1

        # Section 5: List Items
        if list_items:
            sections.append("\n📋 LIST ITEMS:")
            remaining = max_elements - element_count
            for w in list_items[:min(10, remaining)]:
                sections.append(format_element(w, "  "))
                element_count += 1

        # Section 6: Static Content (labels, text)
        if labeled_static:
            sections.append("\n📝 CONTENT:")
            remaining = max_elements - element_count
            for w in labeled_static[:min(10, remaining)]:
                sections.append(format_element(w, "  "))
                element_count += 1

        # Section 7: Others (summarized if many)
        if other:
            remaining = max_elements - element_count
            if remaining > 0 and len(other) <= remaining:
                sections.append("\n📦 OTHER:")
                for w in other:
                    sections.append(format_element(w, "  "))
            elif len(other) > 0:
                sections.append(f"\n📦 OTHER: ({len(other)} structural elements)")

        # Build header with summary stats
        actionable_count = sum(1 for w in widgets if w.get("actionable"))
        input_count = sum(1 for w in widgets if w.get("role") == "input")

        header_lines = [
            f"UI Analysis: {len(widgets)} total elements",
            f"  Interactive: {actionable_count} | Inputs: {input_count} | Shown: {element_count}",
        ]
        if scenario_desc and scenario_desc != "N/A":
            header_lines.append(f"  Context: {scenario_desc[:60]}")

        return "\n".join(header_lines + sections)

    def _call_text_only_llm(
        self,
        compact_tree: str,
        scenario_desc: str,
        navigation_context: str,
        current_step: int
    ) -> str:
        """Call Observer LLM with text-only compact XML tree (no image)."""
        from langchain_core.messages import SystemMessage, HumanMessage

        system_prompt = (
            "You are an expert mobile UI analyst. Analyze the provided structured UI tree "
            "and produce a semantic understanding of the screen.\n\n"
            "Output format:\n"
            "SEMANTIC_MAP:\n"
            "[1]: Description of element 1\n"
            "[2]: Description of element 2\n"
            "...\n\n"
            "SUMMARY: One-sentence summary of the screen state and purpose.\n\n"
            "Be objective and generic. Do not reference specific task goals. "
            "Focus on what UI elements exist and their apparent functions. "
            "For editable input elements, describe existing content ONLY when that same input element has a non-empty label/text value. "
            "Never infer that an empty focused input contains nearby list-item text or repeated text elsewhere on screen."
        )

        user_prompt = f"""App Context: {scenario_desc}
Navigation Path: {navigation_context}
Step: {current_step}

{compact_tree}

Provide semantic mapping of this UI."""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]

        self._log("LLM call started (text-only XML interpretation)", level=_LL.DEBUG)
        try:
            response = self.llm.invoke(
                messages,
                config={
                    "tags": ["observer", f"step_{current_step}", "xml_fast"],
                    "timeout": 30.0
                }
            )
            return response.content
        except Exception as e:
            print(f"\n[!] Observer Text LLM Failed: {str(e)}")
            self._log("LLM ERROR in XML-fast path", str(e), level=_LL.ERROR)
            # Return minimal fallback analysis
            return f"SEMANTIC_MAP:\n(fallback: {len(compact_tree)} chars of UI data)\n\nSUMMARY: XML-derived UI analysis failed, using raw structure."

    def _run_canny_pipeline(
        self,
        raw_path: str,
        ocr_path: str,
        cv_path: str,
        image_height: int,
        is_kb_shown: bool,
    ) -> list:
        """Run the classic Canny edge detection + EasyOCR vision pipeline."""
        ocr_raw = self.ocr_extract_text.invoke({"image_path": raw_path, "save_path": ocr_path})
        cv_raw = self.detect_visual_elements.invoke({"image_path": raw_path, "save_path": cv_path})
        try:
            ocr_elements = json.loads(ocr_raw)
            cv_elements = json.loads(cv_raw)
        except (json.JSONDecodeError, TypeError):
            ocr_elements, cv_elements = [], []
        self._log(
            "Canny+OCR pipeline complete",
            f"ocr_elements={len(ocr_elements)}  cv_elements={len(cv_elements)}",
            level=_LL.DEBUG
        )
        return self._merge_and_filter(cv_elements, ocr_elements, image_height, is_kb_shown)

    def analyze(self, state: AgentState) -> Command:
        current_step = state.get("current_step", 0)
        mode_desc = "XML-First Hybrid" if getattr(config, "OBSERVER_MODE", "xml_first") == "xml_first" else "Pure Vision"
        print(f"\n--- CYCLE {current_step} | [Observer] Starting {mode_desc} Perception... ---")
        self._log(f"=== CYCLE {current_step} — {mode_desc} Perception started ===")

        step_dir = state.get("step_dir", "outputs")
        raw_path = os.path.join(step_dir, "raw.png")
        xml_path = os.path.join(step_dir, "hierarchy.xml")
        ocr_path = os.path.join(step_dir, "ocr.json")
        cv_path = os.path.join(step_dir, "cv.json")
        merged_path = os.path.join(step_dir, "merged.json")
        annotated_path = os.path.join(step_dir, "annotated.png")
        analysis_path = os.path.join(step_dir, "analysis.txt")

        # ── Active Retrieval ──────────────────────────────────────────────────
        memory_context = ""
        scenario_desc = "N/A"
        navigation_context = "N/A"
        if self.memory is not None:
            memory_context = self.memory.retrieve(f"navigation screen step={current_step}")
            scenario_desc = self.memory.core.get("scenario_desc") or "N/A"
            navigation_context = self.memory.core.get("navigation_context") or "N/A"
        self._log("Memory retrieval complete", f"scenario_desc={scenario_desc[:80]}", level=_LL.DEBUG)

        print("[Observer] Checking keyboard state via ADB...")
        kb_resp = self.check_keyboard_state.invoke({})
        try:
            is_kb_shown = json.loads(kb_resp).get("is_shown", False)
        except Exception:
            is_kb_shown = False

        # ── Hybrid XML-First Pipeline ────────────────────────────────────────
        final_widget_set = []
        observation_source = "vision"
        confidence_score = 1.0
        fallback_reason = ""

        # Check if XML mode is enabled
        use_xml = getattr(config, "OBSERVER_MODE", "xml_first") == "xml_first"

        if use_xml:
            print("[Observer] Dumping UI hierarchy XML via ADB...")
            xml_data = self.dump_hierarchy.invoke({"save_path": xml_path})
            if xml_data and not xml_data.startswith("<error>"):
                from core.utils.xml_processor import XMLProcessor
                # ADB uiautomator coordinates calibrate sizes
                # We retrieve current screen dimensions (usually standard)
                processor = XMLProcessor(screen_width=1080, screen_height=2400)
                xml_elements = processor.parse_hierarchy(xml_data)

                score, reason = processor.evaluate_confidence(xml_elements, xml_data)
                confidence_score = score

                if score >= 0.5:
                    print(f"[Observer] XML hierarchy parsed successfully. Confidence: {score:.2f}. Found {len(xml_elements)} elements.")
                    final_widget_set = xml_elements
                    observation_source = "xml"
                else:
                    print(f"[Observer] Low XML confidence ({score:.2f}): {reason}. Triggering Vision Fallback...")
                    fallback_reason = reason
                    observation_source = "hybrid"
            else:
                print("[Observer] Failed to dump XML hierarchy. Triggering Vision Fallback...")
                fallback_reason = "XML dump failure"
                observation_source = "hybrid"

        # Vision Path (primary if not use_xml, or fallback if XML confidence is low)
        if not final_widget_set or observation_source == "hybrid":
            print("[Observer] Taking screenshot for vision pipeline...")
            self.take_screenshot.invoke({"target_path": raw_path})
            self._log("Screenshot captured", raw_path, level=_LL.DEBUG)

            img = cv2.imread(raw_path)
            image_height = img.shape[0] if img is not None else 1920
            image_width  = img.shape[1] if img is not None else 1080

            # ── Vision Pipeline Selection ────────────────────────────────────────
            use_omniparser = self.parse_screen_omniparser is not None and not config.FAST_VISION_MODE

            if use_omniparser:
                print("[Observer] Running OmniParser unified vision pipeline (YOLO + Florence-2 + OCR)...")
                self._log("Vision pipeline: OmniParser", level=_LL.DEBUG)
                omni_raw = self.parse_screen_omniparser.invoke({
                    "image_path": raw_path,
                    "save_path": cv_path,
                })
                try:
                    omni_elements = json.loads(omni_raw)
                    if isinstance(omni_elements, dict) and "error" in omni_elements:
                        raise ValueError(omni_elements["error"])
                except Exception as exc:
                    print(f"[Observer] OmniParser failed ({exc}), falling back to Canny pipeline.")
                    self._log("OmniParser FAILED — falling back to Canny+OCR", str(exc), level=_LL.WARN)
                    omni_elements = None

                if omni_elements is not None:
                    # Post-process: remove card-container backgrounds and merge split text.
                    before_count = len(omni_elements)
                    omni_elements = self._filter_omniparser_widgets(omni_elements, image_width, image_height)
                    after_count = len(omni_elements)
                    if before_count != after_count:
                        print(f"[Observer] OmniParser post-filter: {before_count} → {after_count} elements")

                    grouped = self._group_keyboard_elements(omni_elements, image_height, is_kb_shown)
                    vision_widgets = []
                    for idx, el in enumerate(grouped, start=1):
                        el["id"] = idx
                        el["class"] = "Interactive" if el["type"] == "container" else "StaticText"
                        el["resource_id"] = "none"
                        vision_widgets.append(el)

                    self._log(
                        "OmniParser pipeline complete",
                        f"widgets={len(vision_widgets)}  keyboard={'shown' if is_kb_shown else 'hidden'}",
                        level=_LL.DEBUG
                    )

                    # If we had partial XML elements, we can merge or fully fallback.
                    # Simple thesis fallback: fully use vision widgets, but tag them.
                    final_widget_set = vision_widgets
                else:
                    final_widget_set = self._run_canny_pipeline(raw_path, ocr_path, cv_path, image_height, is_kb_shown)
            else:
                # ── Canny + EasyOCR pipeline (fast mode or OmniParser unavailable) ──
                if config.FAST_VISION_MODE:
                    print("[Observer] FAST_VISION_MODE enabled — using Canny+OCR pipeline")
                print("[Observer] Running Canny+OCR vision pipeline...")
                final_widget_set = self._run_canny_pipeline(raw_path, ocr_path, cv_path, image_height, is_kb_shown)

        # For XML-first path, we must ensure we have a screenshot for Reflector and visual validation
        if observation_source == "xml" and not os.path.exists(raw_path):
            self.take_screenshot.invoke({"target_path": raw_path})

        with open(merged_path, "w", encoding="utf-8") as f:
            json.dump(final_widget_set, f, indent=4, ensure_ascii=False)

        # ── Determine if we can use XML-fast path ─────────────────────────────
        # XML-fast path: skip annotation and multimodal LLM when XML confidence is high
        xml_fast_path = (
            observation_source == "xml"
            and confidence_score >= 0.9
            and len(final_widget_set) > 0
        )

        if xml_fast_path:
            print(f"[Observer] XML-FAST: High confidence ({confidence_score:.2f}), skipping annotation")
            self._log(f"XML-FAST path: {len(final_widget_set)} elements from XML")
        else:
            print("[Observer] Annotating screenshot...")
            self.annotate_screenshot.invoke({
                "image_path": raw_path,
                "elements": final_widget_set,
                "save_path": annotated_path
            })
            self._log("Annotated screenshot saved", annotated_path, level=_LL.DEBUG)

        # ── UI Summary (computed early — used as cache key before LLM call) ────
        filtered_widgets = final_widget_set[:50]
        summary_data = [
            {"id": el.get("id", "?"), "cls": el.get("class", "Widget"), "text": el.get("text", "")}
            for el in filtered_widgets
        ]
        ui_summary_text = compress_and_report(summary_data, "ui_summary", "observer")

        # ── LLM Cache Check: skip call if UI is identical to previous cycle ───
        prev_obs = self.memory.episodic.last_by_actor("observer") if self.memory else None
        prev_ui_summary = prev_obs.details if prev_obs else ""
        cached_analysis = state.get("observer_analysis", "")

        cache_hit = (
            config.OBSERVER_CACHE_ENABLED
            and prev_ui_summary
            and cached_analysis
            and ui_summary_text == prev_ui_summary
        )

        if cache_hit:
            raw_res = cached_analysis
            new_stagnation_count = state.get("stagnation_count", 0) + 1
            print(f"[Observer] [CACHE HIT] UI unchanged — reusing previous analysis (LLM skipped)")
            self._log(f"LLM SKIPPED — UI summary identical to previous step (stagnation={new_stagnation_count})")
        elif xml_fast_path:
            # ── XML-FAST PATH: Text-only LLM with compact tree ────────────────────
            print("[Observer] Calling text-only LLM for XML semantic interpretation...")
            compact_tree = self._generate_compact_xml_tree(
                final_widget_set,
                scenario_desc,
                navigation_context
            )
            raw_res = self._call_text_only_llm(
                compact_tree,
                scenario_desc,
                navigation_context,
                current_step
            )
            with open(analysis_path, "w", encoding="utf-8") as f:
                f.write(raw_res)
            self._log("LLM analysis complete (XML-fast)", raw_res[:500] + ("..." if len(raw_res) > 500 else ""))
            new_stagnation_count = self._detect_stagnation(
                ui_summary_text, current_step, state.get("stagnation_count", 0)
            )
        else:
            # ── VISION PATH: Multimodal LLM with annotated image ──────────────────
            print("[Observer] Calling multimodal LLM for semantic interpretation...")
            img_b64 = self._encode_image(annotated_path, max_height=480)

            elements_data = [{"i": el["id"], "t": el.get("text") or ""} for el in final_widget_set]
            elements_json = compress_and_report(elements_data, "elements", "observer")

            # Build prompt with Few-Shot examples for output format locking
            prompt_messages = [
                ("system", SYSTEM_PROMPT),
            ]
            # Unpack few-shot examples (human, assistant) pairs
            for role, content in FEW_SHOT_EXAMPLES:
                prompt_messages.append((role, content))
            # Add the actual user input
            prompt_messages.append(("human", [
                {"type": "text", "text": "App Context: {scenario_desc}\nNavigation Path: {navigation_context}\nElements: {elements_json}\n\nMap every ID in the screenshot to its generic UI function. Be objective. Do not reference any task or goal."},
                {"type": "image_url", "image_url": {"url": "data:image/webp;base64,{img_b64}"}}
            ]))

            prompt = ChatPromptTemplate.from_messages(prompt_messages)

            messages = prompt.format_messages(
                scenario_desc=scenario_desc,
                navigation_context=navigation_context,
                elements_json=elements_json,
                img_b64=img_b64
            )

            self._log("LLM call started (multimodal screen interpretation)", level=_LL.DEBUG)
            try:
                # Use invoke() for faster response on short outputs (~500-1000 tokens)
                # stream() only beneficial for very long responses
                response = self.llm.invoke(
                    messages,
                    config={
                        "tags": ["observer", f"step_{current_step}"],
                        "timeout": 45.0
                    }
                )
                raw_res = response.content
            except Exception as e:
                print(f"\n[!] Observer Vision LLM Failed/Timed Out: {str(e)}")
                self._log("LLM FATAL ERROR — aborting graph", str(e), level=_LL.ERROR)
                return Command(
                    goto="__end__",
                    update={
                        "execution_result": f"Fatal failure in Observer: {str(e)}. Exiting system.",
                        "sender": "observer",
                        "is_completed": False
                    }
                )

            with open(analysis_path, "w", encoding="utf-8") as f:
                f.write(raw_res)
            self._log("LLM analysis complete", raw_res[:500] + ("..." if len(raw_res) > 500 else ""))

            new_stagnation_count = self._detect_stagnation(
                ui_summary_text, current_step, state.get("stagnation_count", 0)
            )

        if new_stagnation_count > 0:
            self._log(f"STAGNATION detected — count={new_stagnation_count} (UI unchanged from previous step)")

        # ── Semantic Memory: persist detected UI elements ─────────────────────
        semantic_entries = []
        for el in final_widget_set:
            text = el.get("text", "").strip()
            if not text:
                continue
            semantic_entries.append({
                "name": f"widget_{el['id']}_{text[:30]}",
                "summary": f"[{el.get('class', 'Widget')}] {text}",
                "details": "",
                "source": "observer",
                "screen_context": scenario_desc,
                "bounds": str(el.get("bounds", [])),
            })

        # ── Memory Update ─────────────────────────────────────────────────────
        if self.memory is not None:
            update_packet = {
                "episodic": {
                    "event_type": "observer_analysis",
                    "summary": raw_res.split("\n")[0][:200] if raw_res else "Screen analyzed",
                    "details": ui_summary_text,
                    "actor": "observer",
                    "step": current_step,
                },
            }
            # Semantic widget writes are expensive at scale; only include when
            # the memory system explicitly opts in (set write_semantic_widgets=True).
            if semantic_entries and getattr(self.memory, "write_semantic_widgets", False):
                update_packet["semantic"] = semantic_entries
            self.memory.update(update_packet)

        if self.logger is not None:
            self.logger.separator()

        if self.monitor is not None:
            self.monitor.on_observer(final_widget_set)

        return {
            "screenshot_path": raw_path,
            "widgets": final_widget_set,
            "observer_analysis": raw_res,
            "observer_analysis_step": current_step,
            "stagnation_count": new_stagnation_count,
            "memory_context": memory_context,
            "sender": "observer",
            "observation_source": observation_source,
            "confidence_score": confidence_score,
            "fallback_reason": fallback_reason,
        }
