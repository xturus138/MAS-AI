"""Entailment-judge prompts for DSE clustering. SEPARATE from observer_prompts.py.

The judge decides, within a specific widget/screenshot context, whether one
semantic description entails another. Output must be a single machine-parseable
label: entailment | neutral | contradiction.
"""
ENTAILMENT_SYSTEM_PROMPT = (
    "You are a strict natural-language-inference judge for UI element descriptions.\n"
    "Given the on-screen context of a single widget and two descriptions A and B, "
    "decide whether A ENTAILS B: does A being true force B to be true, for THIS "
    "widget on THIS screen?\n"
    "Answer with exactly one lowercase word on the first line: "
    "entailment, neutral, or contradiction. No other text."
)

ENTAILMENT_HUMAN_TEMPLATE = (
    "Widget context:\n"
    "  screen: {screen_desc}\n"
    "  element_id: {element_id}\n"
    "  visible_text: {text}\n"
    "  role: {role}\n\n"
    "A: {a}\n"
    "B: {b}\n\n"
    "Does A entail B? Answer: entailment | neutral | contradiction"
)
