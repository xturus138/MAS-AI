import json
import os
import datetime
from typing import List
from memory.schemas import CoreEntry


class CoreMemoryStore:
    """
    Stores high-priority, persistent session constants that are always
    available to every agent. Backed by a single JSON file per session.
    """

    def __init__(self, session_id: str, output_dir: str):
        self._path = os.path.join(output_dir, "memory", "core.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._data: dict[str, str] = {}
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)

    def write(self, entries: dict):
        """Bulk-set key/value pairs. Each call merges into existing data."""
        now = datetime.datetime.now().isoformat(timespec="seconds")
        for k, v in entries.items():
            self._data[k] = str(v)
        self._flush()

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key, default)

    def search(self, topic: str) -> List[CoreEntry]:
        topic_lower = topic.lower()
        results = []
        for k, v in self._data.items():
            if topic_lower in k.lower() or topic_lower in v.lower():
                results.append(CoreEntry(key=k, value=v))
        # Always include the core constants most useful for agents
        priority_keys = [
            "tcs_id", "task_goal", "expected_result", "scenario_desc",
            "user_role", "navigation_context", "test_type",
            "figma_enabled", "figma_end_node_id",
        ]
        for pk in priority_keys:
            if pk in self._data and not any(r.key == pk for r in results):
                results.append(CoreEntry(key=pk, value=self._data[pk]))
        return results

    def all(self) -> dict:
        return dict(self._data)

    def _flush(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
