# core/uncertainty/banned_words.py
"""Fixed banned-word list for Observer uncertainty explanations.

These words characterize quality/correctness/decision status. The explainer
must only describe *what* the samples said and *how often* — never whether
the result was good, bad, reliable, or correct. See
docs/observer-uncertainty-explanations-design.md Section 2.
"""
import re

BANNED_WORDS = (
    "uncertain",
    "unreliable",
    "failed",
    "wrong",
    "correct",
    "confident",
    "accurate",
    "reliable",
    "good",
    "bad",
    "pass",
    "fail",
    "accepted",
    "rejected",
    "certain",
)

_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in BANNED_WORDS) + r")\b",
    re.IGNORECASE,
)


def contains_banned_word(text: str) -> bool:
    if not text:
        return False
    return bool(_PATTERN.search(text))
