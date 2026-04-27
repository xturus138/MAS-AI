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

    def _get(self, path: str, params: dict = None) -> dict:
        url = f"{config.FIGMA_API_BASE}{path}"
        response = requests.get(url, headers=self._headers, params=params or {}, timeout=30)
        response.raise_for_status()
        return response.json()

    def get_all_frames(self) -> list:
        """Fetch all top-level frames from the Figma file.
        Returns a list of {name, id} dicts for LLM-based discovery.
        Result is cached to avoid repeated API calls in a single run.
        """
        if self._frames_cache is not None:
            return self._frames_cache

        try:
            data = self._get(f"/files/{self.file_key}")
            frames = []

            def _walk(node: dict, depth: int = 0):
                # Only collect FRAME nodes that are direct children of a CANVAS page
                if depth == 2 and node.get("type") == "FRAME":
                    frames.append({"name": node["name"], "id": node["id"]})
                for child in node.get("children", []):
                    _walk(child, depth + 1)

            _walk(data["document"])
            print(f"[Figma] Discovered {len(frames)} top-level frame(s) in file.")
            self._frames_cache = frames
            return frames
        except Exception as e:
            print(f"[Figma] WARN: Could not retrieve frames: {e}")
            return []

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

    def trace_prototype_path(self, start_node_id: str, steps: list) -> Optional[str]:
        try:
            current_node_id = start_node_id
            print(f"[Figma] Tracing prototype path from node {start_node_id} ({len(steps)} steps)...")

            context = self.get_node_context(current_node_id)
            transitions = self._extract_transitions(context)

            for i, step in enumerate(steps):
                next_node = self._match_transition(step, transitions)
                if next_node:
                    print(f"[Figma] Step {i+1}: '{step[:60]}' -> node {next_node}")
                    current_node_id = next_node
                    context = self.get_node_context(current_node_id)
                    transitions = self._extract_transitions(context)
                else:
                    print(f"[Figma] Step {i+1}: No transition matched, staying on {current_node_id}")

            print(f"[Figma] End-state resolved: node_id={current_node_id}")
            return current_node_id

        except Exception as e:
            print(f"[Figma] WARN: trace_prototype_path failed: {e}")
            return None

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
            print(f"[Figma] Gold Standard saved to: {output_path}")
            return True
        except Exception as e:
            print(f"[Figma] WARN: Could not save screenshot to {output_path}: {e}")
            return False


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
