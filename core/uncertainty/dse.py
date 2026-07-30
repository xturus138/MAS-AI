"""Pure Discrete Semantic Entropy (DSE) math. No I/O, no LLM, deterministic.

Single source of truth for the entropy formula. `effective_M` is the sum of the
cluster counts passed in — callers must pass counts derived only from successfully
parsed samples.

Deliberately matches Farquhar, Kossen, Kuhn, Gal, "Detecting hallucinations in large
language models using semantic entropy" (Nature, 2024) exactly: discrete semantic
entropy approximates P(Ci|x) as count_i / M (proportion of samples in cluster i,
"disregarding the token probabilities"), then SE(x) ~= -sum P(Ci|x) log P(Ci|x).
No normalization by log(M) is applied — the paper does not do this, and MAS AI's
own added normalization step was removed on 2026-07-24 to stay paper-exact (see
Dokumen Kepake checklist and [[thesis_dse_calibration_methodology]]).
"""
import math


def raw_dse(cluster_counts: list) -> float:
    """DSE = -sum(p_k * ln(p_k)), p_k = count_k / effective_M."""
    effective_m = sum(cluster_counts)
    if effective_m <= 0:
        return 0.0
    entropy = 0.0
    for c in cluster_counts:
        if c <= 0:
            continue
        p = c / effective_m
        entropy -= p * math.log(p)
    return entropy
