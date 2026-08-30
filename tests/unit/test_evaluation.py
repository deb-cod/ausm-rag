from app.evaluation import compute_metrics


def test_retrieval_metrics():
    metrics = compute_metrics([["a"], ["b"]], [["a", "x"], ["x", "b"]])
    assert metrics.recall_at_5 == 1
    assert metrics.mrr == 0.75
    assert metrics.ndcg_at_10 > 0.8
