"""LLM-judge correctness labeling for the DSE calibration experiment.

Implements Farquhar et al. 2024's correctness-labeling step (paper's
unnumbered "Metrics and accuracy measurements" section — see
`Dokumen Kepake/DSE Calibration Experiment - Big Plan.md`, Phase 2), applied
to widget descriptions instead of QA answers. Mirrors the style of
`core/uncertainty/clusterer.py`'s EntailmentClusterer so both judges share
one convention: system+human prompt pair, first-line label parsing, no
fabricated defaults on ambiguous output.

Not part of the live predefined/autonomous test workflow. Output here is
calibration-experiment ground truth only, never a live test verdict.
"""
from dataclasses import dataclass

from shared.prompts.correctness_prompts import (
    CORRECTNESS_HUMAN_TEMPLATE,
    CORRECTNESS_SYSTEM_PROMPT,
)


@dataclass
class CorrectnessResult:
    predicted_description: str
    reference_description: str
    raw_response: str
    label: str  # "yes" | "no" | "unparseable"

    @property
    def is_correct(self) -> bool:
        return self.label == "yes"


class CorrectnessJudge:
    def __init__(self, llm, system_prompt=CORRECTNESS_SYSTEM_PROMPT,
                 human_template=CORRECTNESS_HUMAN_TEMPLATE):
        self.llm = llm
        self.system_prompt = system_prompt
        self.human_template = human_template

    @staticmethod
    def _parse_label(text) -> str:
        if not text:
            return "unparseable"
        first = str(text).strip().splitlines()[0].strip().lower()
        if "yes" in first and "no" not in first:
            return "yes"
        if "no" in first and "yes" not in first:
            return "no"
        # Ambiguous (both/neither present) — never guess a verdict.
        return "unparseable"

    def judge(self, predicted_description: str, reference_description: str,
              screen_desc: str) -> CorrectnessResult:
        human = self.human_template.format(
            screen_desc=screen_desc,
            reference_description=reference_description,
            predicted_description=predicted_description,
        )
        messages = [("system", self.system_prompt), ("human", human)]
        resp = self.llm.invoke(messages)
        content = getattr(resp, "content", resp)
        label = self._parse_label(content)
        return CorrectnessResult(
            predicted_description=predicted_description,
            reference_description=reference_description,
            raw_response=str(content),
            label=label,
        )
