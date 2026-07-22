"""Structured configuration for an uncertainty measurement run."""
from dataclasses import dataclass


@dataclass
class UncertaintyConfig:
    enabled: bool
    samples: int
    temperature: float
    provider: str
    model: str
    judge_model: str
