import json
import os
from typing import List
from memory.schemas import ProceduralEntry


class ProceduralMemoryStore:
    """
    Stores structured, goal-directed processes: test case sub-steps and
    bridge navigation sequences. Backed by a JSON file per session.
    """

    def __init__(self, session_id: str, output_dir: str):
        self._path = os.path.join(output_dir, "memory", "procedural.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._entries: List[dict] = []
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                self._entries = json.load(f)

    def write(self, entry: dict):
        """
        entry keys: entry_type, description, steps (list[str]), tcs_id
        Replaces existing entry with same tcs_id + entry_type if present.
        """
        tcs_id = entry.get("tcs_id", "")
        entry_type = entry.get("entry_type", "workflow")
        existing_idx = next(
            (i for i, e in enumerate(self._entries)
             if e.get("tcs_id") == tcs_id and e.get("entry_type") == entry_type),
            None,
        )
        if existing_idx is not None:
            self._entries[existing_idx] = entry
        else:
            self._entries.append(entry)
        self._flush()

    def get_steps(self, tcs_id: str, entry_type: str = "workflow") -> List[str]:
        for e in self._entries:
            if e.get("tcs_id") == tcs_id and e.get("entry_type") == entry_type:
                return e.get("steps", [])
        return []

    def search(self, topic: str) -> List[ProceduralEntry]:
        topic_lower = topic.lower()
        results = []
        for e in self._entries:
            if (topic_lower in e.get("description", "").lower()
                    or topic_lower in e.get("tcs_id", "").lower()
                    or any(topic_lower in s.lower() for s in e.get("steps", []))):
                results.append(ProceduralEntry(
                    entry_type=e.get("entry_type", "workflow"),
                    description=e.get("description", ""),
                    steps=e.get("steps", []),
                    tcs_id=e.get("tcs_id", ""),
                ))
        if not results:
            results = [
                ProceduralEntry(
                    entry_type=e.get("entry_type", "workflow"),
                    description=e.get("description", ""),
                    steps=e.get("steps", []),
                    tcs_id=e.get("tcs_id", ""),
                )
                for e in self._entries
            ]
        return results

    def _flush(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=2, ensure_ascii=False)
