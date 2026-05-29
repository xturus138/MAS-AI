from dataclasses import dataclass, field
from typing import List


@dataclass
class CoreEntry:
    key: str
    value: str
    updated_at: str = ""


@dataclass
class EpisodicEntry:
    event_type: str       # "observer_analysis" | "action_executed" | "verification" | "orchestrator_decision"
    summary: str
    details: str
    actor: str            # "observer" | "decider" | "executor" | "reflector" | "orchestrator"
    timestamp: str
    step: int


@dataclass
class SemanticEntry:
    name: str             # widget label / entity identifier
    summary: str          # one-line description
    details: str          # extended context (bounds, screen, function)
    source: str           # "observer" | "inferred"
    screen_context: str   # screen on which this was observed
    bounds: List[int] = field(default_factory=list)  # [x1, y1, x2, y2]


@dataclass
class ProceduralEntry:
    entry_type: str       # "workflow" | "bridge"
    description: str
    steps: List[str]
    tcs_id: str


@dataclass
class ResourceEntry:
    title: str
    summary: str
    resource_type: str    # "screenshot" | "annotated_screenshot" | "figma_gold" | "figma_composite"
    path: str
    step: int
    timestamp: str


@dataclass
class VaultEntry:
    entry_type: str       # "credential" | "api_key" | "device_id"
    key: str
    value: str
    sensitivity: str      # "low" | "medium" | "high"
