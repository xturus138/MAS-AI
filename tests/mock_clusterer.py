"""Deterministic test-only clusterer. NOT the research implementation.

Clusters responses by exact string equality so tests can assert DSE values
without any LLM call. Injected into ObserverUncertaintyService during --self-test.
"""
import sys
sys.path.append(".")
from core.uncertainty.clusterer import ClusterResult, SemanticClusterer


class MockClusterer(SemanticClusterer):
    def cluster(self, responses, context):
        buckets = {}
        order = []
        for r in responses:
            if r not in buckets:
                buckets[r] = 0
                order.append(r)
            buckets[r] += 1
        clusters = [[k] * buckets[k] for k in order]
        counts = [buckets[k] for k in order]
        return ClusterResult(clusters=clusters, counts=counts, pairwise=[])
