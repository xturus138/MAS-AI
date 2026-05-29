from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memory.stores import (
        CoreMemoryStore, EpisodicMemoryStore, SemanticMemoryStore,
        ProceduralMemoryStore, ResourceMemoryStore, KnowledgeVaultStore,
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
        lines.append(f"  [{e.timestamp}] [{e.actor}] step={e.step} | {e.event_type}: {e.summary}")
        if e.details:
            lines.append(f"    {e.details[:300]}")
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
        tasks = {
            "core":       lambda: self._core.search(topic),
            "episodic":   lambda: self._episodic.search(topic, max_per_store),
            "semantic":   lambda: self._semantic.search(topic, max_per_store),
            "procedural": lambda: self._procedural.search(topic),
            "resource":   lambda: self._resource.search(topic, max_per_store),
        }

        results = {}
        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = {ex.submit(fn): name for name, fn in tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result(timeout=5)
                except Exception:
                    results[name] = []

        parts = []
        core_str = _format_core(results.get("core", []))
        epis_str = _format_episodic(results.get("episodic", []))
        sem_str  = _format_semantic(results.get("semantic", []))
        proc_str = _format_procedural(results.get("procedural", []))
        res_str  = _format_resource(results.get("resource", []))

        for s in (core_str, epis_str, sem_str, proc_str, res_str):
            if s:
                parts.append(s)

        return "\n\n".join(parts)
