"""Pure Discrete Semantic Entropy (DSE) math. No I/O, no LLM, deterministic.

Single source of truth for the entropy formulas. `effective_M` is the sum of the
cluster counts passed in — callers must pass counts derived only from successfully
parsed samples.
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


def normalized_dse(cluster_counts: list) -> float:
    """raw_dse / ln(effective_M). Returns 0.0 when effective_M <= 1."""
    effective_m = sum(cluster_counts)
    if effective_m <= 1:
        return 0.0
    return raw_dse(cluster_counts) / math.log(effective_m)
