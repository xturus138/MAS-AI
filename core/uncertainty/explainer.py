# core/uncertainty/explainer.py
"""Generates a plain-English explanation of DSE disagreement for one step.

Reads already-computed per-widget DSE data (raw_dse, clusters) and produces
one LLM call describing what disagreed, only for widgets with raw_dse > 0.
Reporting/XAI layer only — never affects DSE measurement itself. See
docs/observer-uncertainty-explanations-design.md.
"""
from core.uncertainty.banned_words import contains_banned_word
from shared.prompts.uncertainty_explainer_prompts import (
    EXPLAINER_HUMAN_TEMPLATE,
    EXPLAINER_RETRY_REMINDER,
    EXPLAINER_SYSTEM_PROMPT,
)


def _format_widgets_block(uncertain_widgets: list) -> str:
    lines = []
    for w in uncertain_widgets:
        cluster_lines = []
        for cluster in w["clusters"]:
            count = len(cluster)
            sample_desc = cluster[0] if cluster else ""
            cluster_lines.append(f"    - {count}x: {sample_desc}")
        lines.append(
            f"- Widget {w['element_id']} (text={w.get('text', '') or '(none)'}, "
            f"role={w.get('role', '') or '(unknown)'}):\n" + "\n".join(cluster_lines)
        )
    return "\n".join(lines)


def explain_step_uncertainty(llm, widgets_data: list, screen_desc: str):
    uncertain = [w for w in widgets_data if w.get("raw_dse", 0) > 0]
    if not uncertain:
        return None

    widgets_block = _format_widgets_block(uncertain)
    human_text = EXPLAINER_HUMAN_TEMPLATE.format(
        screen_desc=screen_desc, widgets_block=widgets_block
    )
    messages = [("system", EXPLAINER_SYSTEM_PROMPT), ("human", human_text)]

    try:
        resp = llm.invoke(messages)
        text = (getattr(resp, "content", resp) or "").strip()
    except Exception:  # noqa: BLE001 — explanation generation must never break the run
        return None

    if not contains_banned_word(text):
        return text

    retry_messages = [
        ("system", EXPLAINER_SYSTEM_PROMPT),
        ("human", human_text + EXPLAINER_RETRY_REMINDER),
    ]
    try:
        resp = llm.invoke(retry_messages)
        text = (getattr(resp, "content", resp) or "").strip()
    except Exception:  # noqa: BLE001
        return None

    if contains_banned_word(text):
        return None
    return text
