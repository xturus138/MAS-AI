"""AUROC / rejection-accuracy / AURAC computation for the DSE calibration
experiment.

Implements Farquhar et al. 2024's own definitions from "Metrics and
accuracy measurements" (see `Dokumen Kepake/DSE Calibration Experiment -
Big Plan.md`, Phase 4) — Phase 5-6 of MAS AI's own engineering breakdown of
the paper's protocol. No sklearn/scipy dependency: AUROC is computed via
the standard Mann-Whitney U / Wilcoxon rank-sum equivalence to the
ROC-curve integral (mathematically identical to `sklearn.metrics
.roc_auc_score`, just without adding a new dependency to the project for
one metric).

DSE (`raw_dse`) is an UNCERTAINTY score: higher = more entropy = less
confident. The paper's metrics are defined in terms of CONFIDENCE (higher =
more likely correct). AUROC and rank-based accuracy curves are invariant to
any monotonic transform of the score, so using `confidence = -raw_dse`
internally is exactly equivalent to whatever positive confidence scale the
paper's own uncertainty methods use — no information is lost or distorted
by the sign flip.

Not part of the live predefined/autonomous test workflow — offline
calibration-experiment analysis only.
"""


def auroc(uncertainty_scores: list, is_correct: list) -> float:
    """Farquhar et al. 2024: "the probability that a randomly chosen
    correct answer has been assigned a higher confidence score than a
    randomly chosen incorrect answer. For a perfect classifier, this is 1."

    Returns 0.5 (uninformative / undefined) if either class (correct,
    incorrect) is empty — there is no "probability a correct beats an
    incorrect" to compute without both classes present.
    """
    n = len(uncertainty_scores)
    if n != len(is_correct):
        raise ValueError("uncertainty_scores and is_correct must be the same length")
    if n == 0:
        return 0.5

    confidence = [-u for u in uncertainty_scores]

    order = sorted(range(n), key=lambda i: confidence[i])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and confidence[order[j + 1]] == confidence[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 1-indexed average rank across the tie group
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1

    n_pos = sum(1 for c in is_correct if c)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5

    pos_ranks_sum = sum(ranks[i] for i in range(n) if is_correct[i])
    return (pos_ranks_sum - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def rejection_accuracy_curve(uncertainty_scores: list, is_correct: list, steps: int = 100) -> list:
    """Farquhar et al. 2024: rejection accuracy at X% = "the
    question-answering accuracy of the model on the most-confident X% of
    the inputs as identified by the respective uncertainty method."

    Returns a list of (x_percent, accuracy) points for X = 100/steps,
    200/steps, ..., 100 — each cutoff keeping the X% most-confident inputs
    (lowest `raw_dse` first) and reporting accuracy on that retained
    subset.
    """
    n = len(uncertainty_scores)
    if n == 0:
        return []
    order = sorted(range(n), key=lambda i: uncertainty_scores[i])  # most confident (lowest entropy) first
    curve = []
    for step in range(1, steps + 1):
        x_percent = 100.0 * step / steps
        k = max(1, round(n * step / steps))
        subset = order[:k]
        acc = sum(1 for i in subset if is_correct[i]) / len(subset)
        curve.append((x_percent, acc))
    return curve


def aurac(curve: list) -> float:
    """Farquhar et al. 2024: AURAC = "the total area enclosed by the
    accuracies at all cut-off percentages X%." Trapezoidal integration of
    the rejection-accuracy curve over X in [0, 100], normalized to [0, 1]
    so a perfect classifier (100% accuracy retained at every cutoff)
    scores 1.0, matching AUROC's [0, 1] scale for easy side-by-side
    reporting.
    """
    if not curve:
        return 0.0
    xs = [0.0] + [x for x, _ in curve]
    ys = [curve[0][1]] + [y for _, y in curve]  # flat extension back to X=0
    area = 0.0
    for i in range(1, len(xs)):
        dx = xs[i] - xs[i - 1]
        area += dx * (ys[i] + ys[i - 1]) / 2.0
    return area / 100.0
