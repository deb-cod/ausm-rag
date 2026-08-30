import math
from dataclasses import dataclass


@dataclass
class RetrievalMetrics:
    recall_at_5: float
    recall_at_10: float
    mrr: float
    ndcg_at_10: float
    evaluated: int


def compute_metrics(expected: list[list[str]], retrieved: list[list[str]]) -> RetrievalMetrics:
    if not expected:
        return RetrievalMetrics(0, 0, 0, 0, 0)
    recall5 = recall10 = reciprocal = ndcg = 0.0
    for relevant, results in zip(expected, retrieved, strict=True):
        relevant_set = set(relevant)
        if not relevant_set:
            continue
        recall5 += len(relevant_set & set(results[:5])) / len(relevant_set)
        recall10 += len(relevant_set & set(results[:10])) / len(relevant_set)
        first_rank = next(
            (rank for rank, item in enumerate(results, 1) if item in relevant_set), None
        )
        reciprocal += 1 / first_rank if first_rank else 0
        dcg = sum(
            (1 / math.log2(rank + 1))
            for rank, item in enumerate(results[:10], 1)
            if item in relevant_set
        )
        ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(10, len(relevant_set)) + 1))
        ndcg += dcg / ideal if ideal else 0
    count = len(expected)
    return RetrievalMetrics(
        recall5 / count, recall10 / count, reciprocal / count, ndcg / count, count
    )
