"""
Optimized Prompts Package for MAS AI

This package contains prompt templates and few-shot examples for all LLM agents.
Prompts follow best practices from the Prompt Engineering literature:
- Few-Shot Learning for output format locking
- Chain-of-Thought (CoT) for reasoning before action
- ReAct pattern for decision-making
- Directional Stimulus for focused evaluation
"""

from .observer_prompts import SYSTEM_PROMPT as OBSERVER_SYSTEM_PROMPT, FEW_SHOT_EXAMPLES as OBSERVER_FEW_SHOT
from .decider_prompts import SYSTEM_PROMPT as DECIDER_SYSTEM_PROMPT
from .orchestrator_prompts import FEW_SHOT_EXAMPLES as ORCHESTRATOR_FEW_SHOT
from .reflector_prompts import (
    DIRECTIONAL_STIMULUS,
    FINAL_STEP_STIMULUS,
    LOADING_STIMULUS,
    UI_CHANGE_STIMULUS,
)
from .predefined_orchestrator_prompts import (
    FIGMA_FLOW_SYSTEM_PROMPT,
    FIGMA_FLOW_EXAMPLES,
    BRIDGE_SYSTEM_PROMPT,
    BRIDGE_EXAMPLES,
)

__all__ = [
    "OBSERVER_SYSTEM_PROMPT",
    "OBSERVER_FEW_SHOT",
    "DECIDER_SYSTEM_PROMPT",
    "ORCHESTRATOR_FEW_SHOT",
    "DIRECTIONAL_STIMULUS",
    "FINAL_STEP_STIMULUS",
    "LOADING_STIMULUS",
    "UI_CHANGE_STIMULUS",
    "FIGMA_FLOW_SYSTEM_PROMPT",
    "FIGMA_FLOW_EXAMPLES",
    "BRIDGE_SYSTEM_PROMPT",
    "BRIDGE_EXAMPLES",
]
