import json
import os
import base64
import datetime
from typing import List, Optional
from memory.schemas import ResourceEntry


class ResourceMemoryStore:
    """
    Manages file references for screenshots, Figma gold standards, and other
    media. The actual binary data stays on disk; this store tracks metadata.
    """

    def __init__(self, session_id: str, output_dir: str):
        self._path = os.path.join(output_dir, "memory", "resource.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._entries: List[dict] = []
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                self._entries = json.load(f)

    def write(self, entry: dict):
        """
        entry keys: title, summary, resource_type, path, step
        """
        self._entries.append({
            "title":         entry.get("title", ""),
            "summary":       entry.get("summary", ""),
            "resource_type": entry.get("resource_type", "screenshot"),
            "path":          entry.get("path", ""),
            "step":          entry.get("step", 0),
            "timestamp":     entry.get("timestamp", datetime.datetime.now().isoformat(timespec="seconds")),
        })
        self._flush()

    def save_figma_gold(self, b64_data: str, output_dir: str) -> str:
        """
        Decodes a base64 Figma screenshot, saves it to disk, and registers
        the path in Resource Memory. Returns the saved file path.
        """
        if not b64_data:
            return ""
        figma_dir = os.path.join(output_dir, "figma")
        os.makedirs(figma_dir, exist_ok=True)
        dest = os.path.join(figma_dir, "end_state.png")
        try:
            with open(dest, "wb") as f:
                f.write(base64.b64decode(b64_data))
            self.write({
                "title":         "figma_gold_standard",
                "summary":       "Figma end-state Gold Standard for final verification",
                "resource_type": "figma_gold",
                "path":          dest,
                "step":          0,
            })
        except Exception:
            return ""
        return dest

    def get_figma_gold_b64(self) -> str:
        """Reads the Figma gold standard from disk and returns as base64."""
        entry = self._find_by_type("figma_gold")
        if not entry:
            return ""
        path = entry.get("path", "")
        if not path or not os.path.exists(path):
            return ""
        try:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception:
            return ""

    def get_latest_screenshot_path(self, resource_type: str = "screenshot") -> str:
        for entry in reversed(self._entries):
            if entry.get("resource_type") == resource_type:
                return entry.get("path", "")
        return ""

    def search(self, topic: str, max_results: int = 3) -> List[ResourceEntry]:
        topic_lower = topic.lower()
        results = []
        for e in reversed(self._entries):
            if (topic_lower in e.get("title", "").lower()
                    or topic_lower in e.get("summary", "").lower()
                    or topic_lower in e.get("resource_type", "").lower()):
                results.append(self._to_entry(e))
            if len(results) >= max_results:
                break
        for rtype in ("figma_gold", "screenshot"):
            path = self.get_latest_screenshot_path(rtype)
            if path and not any(r.path == path for r in results):
                e = self._find_by_path(path)
                if e:
                    results.append(self._to_entry(e))
        return results[:max_results + 2]

    def _find_by_type(self, resource_type: str) -> Optional[dict]:
        for e in reversed(self._entries):
            if e.get("resource_type") == resource_type:
                return e
        return None

    def _find_by_path(self, path: str) -> Optional[dict]:
        for e in reversed(self._entries):
            if e.get("path") == path:
                return e
        return None

    @staticmethod
    def _to_entry(e: dict) -> ResourceEntry:
        return ResourceEntry(
            title=e.get("title", ""),
            summary=e.get("summary", ""),
            resource_type=e.get("resource_type", ""),
            path=e.get("path", ""),
            step=e.get("step", 0),
            timestamp=e.get("timestamp", ""),
        )

    def _flush(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=2, ensure_ascii=False)
