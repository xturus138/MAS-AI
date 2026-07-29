"""Correctness-judge prompt for the DSE calibration experiment. SEPARATE from
observer_prompts.py and entailment_prompts.py.

Adapted, not invented: this is Farquhar, Kossen, Kuhn, Gal (Nature, 2024)'s
own yes/no correctness-labeling template — "The expected answer is: ...
The proposed answer is: ... does the proposed answer mean the same as the
expected answer? Respond only with yes or no." — with QA vocabulary
("question", "answer") swapped for widget vocabulary ("widget", "description"),
per `Dokumen Kepake/DSE Calibration Experiment - Big Plan.md`, Phase 2. The
prompt's structure and intent are unchanged from the paper; only domain
nouns differ.

Used only by the offline calibration pipeline (Farquhar et al. 2024, steps
5-6: correctness labeling -> AUROC/AURAC) — NOT part of the live
predefined/autonomous test workflow, and never gates a test verdict.
"""
CORRECTNESS_SYSTEM_PROMPT = (
    "You are assessing whether an automated description of a mobile app UI "
    "widget matches a human-verified ground-truth description of the same "
    "widget. Respond only with yes or no."
)

CORRECTNESS_HUMAN_TEMPLATE = (
    "We are assessing the quality of descriptions of a UI widget on the "
    "screen described as: {screen_desc}\n"
    "The expected widget description is: {reference_description}\n"
    "The proposed widget description is: {predicted_description}\n"
    "Within the context of this screen, does the proposed description mean "
    "the same as the expected description? Respond only with yes or no."
)
