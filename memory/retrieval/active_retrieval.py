from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.stores import (
        CoreMemoryStore,
        EpisodicMemoryStore,
        KnowledgeVaultStore,
        ProceduralMemoryStore,
        ResourceMemoryStore,
        SemanticMemoryStore,
    )


def _format_core(entries) -> str:
    if not entries:
        return ""
    lines = [f"  {e.key}: {e.value}" for e in entries]
    return "<core_memory>\n" + "\n".join(lines) + "\n</core_memory>"


def _format_episodic(entries) -> str:
    if not entries:
        return ""
    lines = []
    for e in entries:
        summary = (e.summary or "")[:120]
        lines.append(
            f"  [{e.actor}] step={e.step} | {e.event_type}: {summary}"
        )
        if e.details:
            lines.append(f"    {e.details[:120]}")
    return "<episodic_memory>\n" + "\n".join(lines) + "\n</episodic_memory>"


def _format_semantic(entries) -> str:
    if not entries:
        return ""
    lines = []
    for e in entries:
        bounds_str = f" bounds={e.bounds}" if e.bounds else ""
        lines.append(f"  [{e.name}]{bounds_str}: {e.summary}")
        if e.details:
            lines.append(f"    {e.details[:200]}")
    return "<semantic_memory>\n" + "\n".join(lines) + "\n</semantic_memory>"


def _format_procedural(entries) -> str:
    if not entries:
        return ""
    lines = []
    for e in entries:
        lines.append(f"  [{e.entry_type}] {e.description} (tcs={e.tcs_id})")
        for i, step in enumerate(e.steps, 1):
            lines.append(f"    {i}. {step}")
    return "<procedural_memory>\n" + "\n".join(lines) + "\n</procedural_memory>"


def _format_resource(entries) -> str:
    if not entries:
        return ""
    lines = []
    for e in entries:
        lines.append(f"  [{e.resource_type}] step={e.step} path={e.path} | {e.summary}")
    return "<resource_memory>\n" + "\n".join(lines) + "\n</resource_memory>"


def _format_vault(entries) -> str:
    if not entries:
        return ""
    lines = []
    for e in entries:
        lines.append(f"  [{e.entry_type}] {e.key}: {e.value}")
    return "<knowledge_vault>\n" + "\n".join(lines) + "\n</knowledge_vault>"


class ActiveRetrieval:
    """
    Implements MIRIX Active Retrieval (Section 3.2 of the paper).

    Given a topic string, it searches all six memory stores in parallel
    and returns a tagged context string ready for injection into an LLM prompt.
    """

    def __init__(
        self,
        core: "CoreMemoryStore",
        episodic: "EpisodicMemoryStore",
        semantic: "SemanticMemoryStore",
        procedural: "ProceduralMemoryStore",
        resource: "ResourceMemoryStore",
        vault: "KnowledgeVaultStore",
    ):
        self._core = core
        self._episodic = episodic
        self._semantic = semantic
        self._procedural = procedural
        self._resource = resource
        self._vault = vault

    def retrieve(self, topic: str, max_per_store: int = 5) -> str:
        """
        Active Retrieval: search all stores in parallel, tag results by source.
        Returns a multi-tag context string ready for LLM injection.
        """
        return "\n\n".join(
            text for text in self.retrieve_with_labels(topic, max_per_store).values() if text
        )

    def retrieve_with_labels(self, topic: str, max_per_store: int = 5) -> dict[str, str]:
        """
        Active Retrieval with explicit source labels.

        Returns a dict mapping store name to its tagged context string.
        Empty stores return empty strings, making it easy to select only the
        sources an agent needs (e.g., semantic + vault for general knowledge).
        """
        tasks = {
            "core": lambda: self._core.search(topic),
            "episodic": lambda: self._episodic.search(topic, max_per_store),
            "semantic": lambda: self._semantic.search(topic, max_per_store),
            "procedural": lambda: self._procedural.search(topic),
            "resource": lambda: self._resource.search(topic, max_per_store),
            "vault": lambda: self._vault.search(topic),
        }

        results = {}
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {ex.submit(fn): name for name, fn in tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result(timeout=5)
                except Exception:
                    results[name] = []

        return {
            "core": _format_core(results.get("core", [])),
            "episodic": _format_episodic(results.get("episodic", [])),
            "semantic": _format_semantic(results.get("semantic", [])),
            "procedural": _format_procedural(results.get("procedural", [])),
            "resource": _format_resource(results.get("resource", [])),
            "vault": _format_vault(results.get("vault", [])),
        }
