"""Structured configuration for an uncertainty measurement run."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class UncertaintyConfig:
    enabled: bool
    samples: int
    temperature: float
    provider: str
    model: str
    judge_model: str
    max_widgets: int = 20
    target_widget_id: Optional[int] = None
    threshold: Optional[float] = None

