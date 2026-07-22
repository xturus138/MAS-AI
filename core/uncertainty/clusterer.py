"""Semantic clustering for DSE via context-aware bidirectional entailment."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from shared.prompts.entailment_prompts import (
    ENTAILMENT_HUMAN_TEMPLATE,
    ENTAILMENT_SYSTEM_PROMPT,
)

_VALID_LABELS = ("entailment", "neutral", "contradiction")


@dataclass
class WidgetContext:
    element_id: int
    text: str
    role: str
    screen_desc: str


@dataclass
class PairwiseDecision:
    a: str
    b: str
    a_entails_b: str
    b_entails_a: str
    merged: bool
    context: dict


@dataclass
class ClusterResult:
    clusters: list = field(default_factory=list)   # list[list[str]]
    counts: list = field(default_factory=list)     # list[int]
    pairwise: list = field(default_factory=list)    # list[PairwiseDecision]


class SemanticClusterer(ABC):
    @abstractmethod
    def cluster(self, responses: list, context: WidgetContext) -> ClusterResult:
        ...


class EntailmentClusterer(SemanticClusterer):
    def __init__(self, llm, system_prompt=ENTAILMENT_SYSTEM_PROMPT,
                 human_template=ENTAILMENT_HUMAN_TEMPLATE):
        self.llm = llm
        self.system_prompt = system_prompt
        self.human_template = human_template

    @staticmethod
    def _parse_label(text) -> str:
        if not text:
            return "neutral"
        first = str(text).strip().splitlines()[0].strip().lower()
        for label in _VALID_LABELS:
            if label in first:
                return label
        return "neutral"

    def _entails(self, a: str, b: str, context: WidgetContext) -> str:
        human = self.human_template.format(
            screen_desc=context.screen_desc,
            element_id=context.element_id,
            text=context.text,
            role=context.role,
            a=a,
            b=b,
        )
        messages = [("system", self.system_prompt), ("human", human)]
        resp = self.llm.invoke(messages)
        content = getattr(resp, "content", resp)
        return self._parse_label(content)

    def cluster(self, responses: list, context: WidgetContext) -> ClusterResult:
        result = ClusterResult()
        for resp in responses:
            placed = False
            for idx, members in enumerate(result.clusters):
                rep = members[0]
                ab = self._entails(resp, rep, context)
                ba = self._entails(rep, resp, context)
                merged = ab == "entailment" and ba == "entailment"
                result.pairwise.append(
                    PairwiseDecision(
                        a=resp, b=rep, a_entails_b=ab, b_entails_a=ba, merged=merged,
                        context={
                            "element_id": context.element_id,
                            "role": context.role,
                            "screen_desc": context.screen_desc,
                        },
                    )
                )
                if merged:
                    members.append(resp)
                    placed = True
                    break
            if not placed:
                result.clusters.append([resp])
        result.counts = [len(m) for m in result.clusters]
        return result
