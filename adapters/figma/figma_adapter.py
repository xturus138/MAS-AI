import json
import os
import re
import base64
from typing import Optional
import requests
from shared import config





def _extract_file_key(url_or_key: str) -> str:
    pattern = r"figma\.com/(?:design|file|proto)/([A-Za-z0-9_-]+)"
    match = re.search(pattern, url_or_key)
    if match:
        return match.group(1)
    return url_or_key.strip()


class FigmaAdapter:
    def __init__(self, file_key: str, access_token: str):
        self.file_key = file_key
        self.access_token = access_token
        self._headers = {"X-FIGMA-TOKEN": self.access_token}
        self._frames_cache: Optional[list] = None
        self._flow_starting_points: list = []

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{config.FIGMA_API_BASE}{path}"
        response = requests.get(url, headers=self._headers, params=params or {}, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_all_frames(self) -> list:
        """Fetch all top-level frames and their prototype transitions."""
        if self._frames_cache is not None:
            return self._frames_cache

        try:
            data = self._get(f"/files/{self.file_key}")
            frames = []
            flow_points = []

            # Extract named Flow Starting Points from the page level
            def _extract_flow_points(node: dict):
                if "flowStartingPoints" in node:
                    for fp in node["flowStartingPoints"]:
                        flow_points.append({
                            "name": fp.get("name", "Unnamed Flow"),
                            "node_id": fp.get("nodeId")
                        })
                for child in node.get("children", []):
                    _extract_flow_points(child)

            _extract_flow_points(data["document"])
            self._flow_starting_points = flow_points

            def _get_transitions(node: dict):
                txs = []
                if "transitionNodeID" in node:
                    txs.append({
                        "trigger": node.get("name", "Unknown"),
                        "to": node["transitionNodeID"]
                    })
                for child in node.get("children", []):
                    txs.extend(_get_transitions(child))
                return txs

            def _walk(node: dict, depth: int = 0):
                if depth == 2 and node.get("type") == "FRAME":
                    # Check if this frame is a named starting point
                    is_start_point = False
                    start_point_name = ""
                    for fp in self._flow_starting_points:
                        if fp["node_id"] == node["id"]:
                            is_start_point = True
                            start_point_name = fp["name"]
                            break

                    frame_data = {
                        "name": node["name"],
                        "id": node["id"],
                        "is_flow_start": is_start_point,
                        "flow_name": start_point_name,
                        "transitions": _get_transitions(node)
                    }
                    frames.append(frame_data)
                for child in node.get("children", []):
                    _walk(child, depth + 1)

            _walk(data["document"])
            print(f"[Figma] Discovered {len(frames)} frame(s) and {len(self._flow_starting_points)} named flow starting point(s).")
            self._frames_cache = frames
            return frames
        except Exception as e:
            print(f"[Figma] WARN: Could not retrieve frames: {e}")
            return []

    def get_flow_summary(self) -> str:
        """Returns a string summary of the prototype graph for the LLM."""
        frames = self.get_all_frames()
        if not frames:
            return "No Figma frames or prototype flows found."

        summary = []
        
        if self._flow_starting_points:
            summary.append("NAMED FLOW STARTING POINTS:")
            for fp in self._flow_starting_points:
                summary.append(f"- Flow: '{fp['name']}' starts at Frame ID: {fp['node_id']}")
            summary.append("")

        summary.append("PROTOTYPE GRAPH:")
        for f in frames:
            start_marker = f" [START OF FLOW: {f['flow_name']}]" if f["is_flow_start"] else ""
            f_summary = f"Frame: '{f['name']}' (ID: {f['id']}){start_marker}"
            if f["transitions"]:
                f_summary += "\n  Connections:"
                for t in f["transitions"]:
                    dest_name = t["to"]
                    for f2 in frames:
                        if f2["id"] == t["to"]:
                            dest_name = f2["name"]
                            break
                    f_summary += f"\n    - Trigger: '{t['trigger']}' -> Leads to: '{dest_name}' (ID: {t['to']})"
            else:
                f_summary += "\n  Connections: None (End node or isolated)"
            summary.append(f_summary)
        
        return "\n".join(summary)

    def find_flow_start_node(self, menu_name: str) -> Optional[str]:
        """Manual mapping is deprecated. Use LLM discovery via Orchestrator."""
        return None

    def get_node_context(self, node_id: str) -> dict:
        try:
            safe_id = node_id.replace(":", "-")
            data = self._get(f"/files/{self.file_key}/nodes", params={"ids": safe_id})
            return data.get("nodes", {}).get(node_id, {})
        except Exception as e:
            print(f"[Figma] WARN: Could not get context for node {node_id}: {e}")
            return {}

    def get_node_screenshot_b64(self, node_id: str) -> str:
        try:
            safe_id = node_id.replace(":", "-")
            data = self._get(
                f"/images/{self.file_key}",
                params={"ids": safe_id, "format": "png", "scale": "1"}
            )
            image_url = data.get("images", {}).get(node_id) or data.get("images", {}).get(safe_id)
            if not image_url:
                print(f"[Figma] WARN: No image URL returned for node {node_id}")
                return ""
            img_resp = requests.get(image_url, timeout=30)
            img_resp.raise_for_status()
            return base64.b64encode(img_resp.content).decode("utf-8")
        except Exception as e:
            print(f"[Figma] WARN: Could not get screenshot for node {node_id}: {e}")
            return ""

    def trace_prototype_path(self, start_node_id: str, steps: list) -> list:
        try:
            path_ids = [start_node_id]
            current_node_id = start_node_id
            print(f"[Figma] Tracing prototype path from node {start_node_id} ({len(steps)} steps)...")

            context = self.get_node_context(current_node_id)
            transitions = self._extract_transitions(context)

            for i, step in enumerate(steps):
                next_node = self._match_transition(step, transitions)
                if next_node:
                    if next_node != current_node_id:
                        print(f"[Figma] Step {i+1}: '{step[:60]}' -> node {next_node}")
                        current_node_id = next_node
                        path_ids.append(current_node_id)
                        context = self.get_node_context(current_node_id)
                        transitions = self._extract_transitions(context)
                else:
                    # Check if we are already at the end of a chain or if we should skip logging stay-on
                    pass

            print(f"[Figma] Resolved path with {len(path_ids)} frame(s).")
            return path_ids

        except Exception as e:
            print(f"[Figma] WARN: trace_prototype_path failed: {e}")
            return [start_node_id]

    def _extract_transitions(self, context: dict) -> dict:
        transitions = {}
        if not context:
            return transitions
        raw = json.dumps(context)
        pattern = r'"name"\s*:\s*"([^"]+)"[^}]*?"transitionNodeID"\s*:\s*"([^"]+)"'
        for match in re.finditer(pattern, raw, re.DOTALL):
            label, dest = match.group(1), match.group(2)
            transitions[label.lower()] = dest
        return transitions

    def _match_transition(self, step: str, transitions: dict) -> Optional[str]:
        step_lower = step.lower()
        for label, dest in transitions.items():
            if label in step_lower or any(word in step_lower for word in label.split() if len(word) > 3):
                return dest
        return None

    def save_screenshot_to_file(self, node_id: str, output_path: str) -> bool:
        b64 = self.get_node_screenshot_b64(node_id)
        if not b64:
            return False
        try:
            img_bytes = base64.b64decode(b64)
            with open(output_path, "wb") as f:
                f.write(img_bytes)
            return True
        except Exception as e:
            print(f"[Figma] WARN: Could not save screenshot to {output_path}: {e}")
            return False

    def save_composite_gold_standard(self, node_ids: list, output_path: str):
        """Creates a side-by-side composite of multiple Figma frames with titles."""
        from PIL import Image, ImageDraw, ImageFont
        import io

        if not node_ids:
            return

        images = []
        titles = []
        
        # Limit to 3 frames to match user's UI layout (Start, Middle, End)
        target_ids = node_ids
        if len(node_ids) > 3:
            target_ids = [node_ids[0], node_ids[len(node_ids)//2], node_ids[-1]]

        for i, nid in enumerate(target_ids):
            b64 = self.get_node_screenshot_b64(nid)
            if not b64: continue
            
            img = Image.open(io.BytesIO(base64.b64decode(b64)))
            images.append(img)
            
            # Get frame name for title
            context = self.get_node_context(nid)
            name = context.get("document", {}).get("name", f"Frame {nid}")
            titles.append(name)

        if not images:
            return

        # Calculate canvas size
        padding = 40
        title_height = 80
        max_w = sum(img.width for img in images) + (padding * (len(images) + 1))
        max_h = max(img.height for img in images) + padding + title_height

        canvas = Image.new("RGB", (max_w, max_h), (245, 245, 245))
        draw = ImageDraw.Draw(canvas)
        
        # Try to load a font, fallback to default
        try:
            font = ImageFont.truetype("arial.ttf", 32)
        except:
            font = ImageFont.load_default()

        curr_x = padding
        for img, title in zip(images, titles):
            # Draw title
            draw.text((curr_x, 20), title, fill=(100, 100, 100), font=font)
            # Paste image
            canvas.paste(img, (curr_x, title_height))
            curr_x += img.width + padding

        canvas.save(output_path)
        print(f"[Figma] Composite Gold Standard saved to: {output_path}")


def build_figma_adapter_from_prompt(access_token: str) -> Optional[FigmaAdapter]:
    print("\n[*] MAS AI - Figma Visual Integration Setup")
    print("    Enter Figma file URL (or press Enter to skip visual validation): ", end="", flush=True)
    raw_input = input().strip()

    if not raw_input:
        print("[Figma] Skipping Figma integration. Running in text-only validation mode.")
        return None

    file_key = _extract_file_key(raw_input)
    print(f"[Figma] File key extracted: {file_key}")
    return FigmaAdapter(file_key=file_key, access_token=access_token)
