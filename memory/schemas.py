from dataclasses import dataclass, field
from typing import List


@dataclass
class CoreEntry:
    """Core store — immutable session facts. CoALA extension (not in original 4 types)."""
    key: str
    value: str
    updated_at: str = ""


@dataclass
class EpisodicEntry:
    """Episodic store — long-term memory of past experiences/events."""
    event_type: str
    summary: str
    details: str
    actor: str
    timestamp: str
    step: int


@dataclass
class SemanticEntry:
    """Semantic store — UI concepts/widget descriptions for cross-step recall."""
    name: str
    summary: str
    details: str
    source: str
    screen_context: str
    bounds: List[int] = field(default_factory=list)


@dataclass
class ProceduralEntry:
    """Procedural store — ordered task sub-steps. CoALA extension (not in original 4 types)."""
    entry_type: str
    description: str
    steps: List[str]
    tcs_id: str


@dataclass
class ResourceEntry:
    """Resource store — binary assets (screenshots, Figma gold standard)."""
    title: str
    summary: str
    resource_type: str
    path: str
    step: int
    timestamp: str


@dataclass
class VaultEntry:
    """Knowledge Vault — domain heuristics accumulated across runs."""
    entry_type: str
    key: str
    value: str
    sensitivity: str
