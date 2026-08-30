from app.llm.schemas import QueryPlan, QueryType, RetrievalPlan


class RetrievalPlanner:
    def __init__(self, max_subqueries: int):
        self.max_subqueries = max_subqueries

    def build(self, plan: QueryPlan) -> RetrievalPlan:
        queries = self.queries(plan)
        entity_queries: dict[str, list[str]] = {}
        if plan.query_type == QueryType.COMPARISON:
            dimensions = ", ".join(plan.comparison_dimensions)
            entity_queries = {
                target: [f"{target} {dimensions}".strip()] for target in plan.comparison_targets
            }
        complex_types = {
            QueryType.LOCATOR,
            QueryType.COMPARISON,
            QueryType.MULTI_HOP,
            QueryType.ANALYTICAL,
            QueryType.SYNTHESIS,
        }
        return RetrievalPlan(
            strategy=plan.retrieval_strategy,
            queries=queries,
            entity_queries=entity_queries,
            metadata_filters={"document": plan.document_filters} if plan.document_filters else {},
            rerank=plan.query_type in complex_types,
        )

    def queries(self, plan: QueryPlan) -> list[str]:
        if plan.query_type == QueryType.NO_RETRIEVAL:
            return []
        if plan.query_type == QueryType.LOCATOR:
            return list(dict.fromkeys([*plan.exact_terms, plan.standalone_query]))[
                : self.max_subqueries
            ]
        if plan.query_type == QueryType.COMPARISON and plan.comparison_targets:
            dimensions = ", ".join(plan.comparison_dimensions)
            target_queries = [
                f"{target} {dimensions}".strip() for target in plan.comparison_targets
            ]
            return (target_queries + [plan.standalone_query])[: self.max_subqueries]
        if plan.requires_decomposition and plan.subquestions:
            return plan.subquestions[: self.max_subqueries]
        return [plan.standalone_query]
