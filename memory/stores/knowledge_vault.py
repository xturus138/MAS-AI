import json
import os
from typing import List, Optional
from memory.schemas import VaultEntry


class KnowledgeVaultStore:
    """
    Secure repository for verbatim and sensitive data: test credentials,
    API keys, device IDs. High-sensitivity entries are excluded from
    general retrieval and only surfaced via explicit key lookup.
    """

    def __init__(self, session_id: str, output_dir: str):
        self._path = os.path.join(output_dir, "memory", "vault.json")
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._entries: List[dict] = []
        if os.path.exists(self._path):
            with open(self._path, "r", encoding="utf-8") as f:
                self._entries = json.load(f)

    def write(self, entry: dict):
        """
        entry keys: entry_type, key, value, sensitivity
        """
        existing_idx = next(
            (i for i, e in enumerate(self._entries) if e.get("key") == entry.get("key")),
            None,
        )
        if existing_idx is not None:
            self._entries[existing_idx] = entry
        else:
            self._entries.append(entry)
        self._flush()

    def get(self, key: str) -> Optional[str]:
        for e in self._entries:
            if e.get("key") == key:
                return e.get("value", "")
        return None

    def search(self, topic: str) -> List[VaultEntry]:
        """
        Only surfaces low/medium sensitivity entries in search.
        High-sensitivity items require explicit key lookup via get().
        """
        topic_lower = topic.lower()
        results = []
        for e in self._entries:
            if e.get("sensitivity", "high") == "high":
                continue
            if (topic_lower in e.get("key", "").lower()
                    or topic_lower in e.get("entry_type", "").lower()):
                results.append(VaultEntry(
                    entry_type=e.get("entry_type", ""),
                    key=e.get("key", ""),
                    value="[REDACTED]",
                    sensitivity=e.get("sensitivity", "low"),
                ))
        return results

    def _flush(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._entries, f, indent=2, ensure_ascii=False)
