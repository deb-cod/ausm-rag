import json

from app.llm.ollama_client import OllamaClient, OllamaError
from app.llm.prompts import RERANK_SYSTEM
from app.llm.schemas import QueryType, RerankResponse
from app.retrieval.models import SearchResult
from app.utils.text import compact_alphanumeric, parse_locator_query, tokenize


class AdaptiveReranker:
    def __init__(self, client: OllamaClient, enabled: bool, top_k: int):
        self.client = client
        self.enabled = enabled
        self.top_k = top_k

    async def rerank(
        self,
        query: str,
        candidates: list[SearchResult],
        query_type: QueryType,
        exact_terms: list[str] | None = None,
    ) -> list[SearchResult]:
        if not candidates:
            return []
        if query_type == QueryType.LOCATOR:
            return self._rerank_locator(query, candidates, exact_terms or [])
        if self.enabled and query_type in {
            QueryType.COMPARISON,
            QueryType.MULTI_HOP,
            QueryType.ANALYTICAL,
            QueryType.SYNTHESIS,
        }:
            try:
                ranked = await self._llm_rerank(query, candidates)
                return self._apply_trust_and_freshness(ranked)
            except OllamaError:
                pass
        query_terms = set(tokenize(query))
        match_targets = [query, *(exact_terms or [])]
        compact_targets = [
            compact_alphanumeric(target)
            for target in match_targets
            if len(compact_alphanumeric(target)) >= 8
        ]
        for candidate in candidates:
            terms = set(tokenize(candidate.content))
            lexical = len(query_terms & terms) / max(1, len(query_terms))
            compact_content = compact_alphanumeric(candidate.content)
            direct_match = any(target in compact_content for target in compact_targets)
            compact_coverage = max(
                (self._compact_coverage(target, compact_content) for target in compact_targets),
                default=0.0,
            )
            normalized_score = min(1.0, max(0.0, candidate.score))
            if direct_match:
                candidate.score = 0.8 + 0.2 * normalized_score
            else:
                candidate.score = (
                    0.4 * normalized_score + 0.25 * lexical + 0.35 * compact_coverage
                )
        return self._apply_trust_and_freshness(candidates)

    @staticmethod
    def _compact_coverage(target: str, content: str, ngram_size: int = 5) -> float:
        if not target or not content:
            return 0.0
        if target in content:
            return 1.0
        if len(target) < ngram_size:
            return float(target in content)
        grams = {
            target[offset : offset + ngram_size]
            for offset in range(len(target) - ngram_size + 1)
        }
        return sum(gram in content for gram in grams) / max(1, len(grams))

    def _rerank_locator(
        self, query: str, candidates: list[SearchResult], exact_terms: list[str]
    ) -> list[SearchResult]:
        locator = parse_locator_query(query)
        targets = list(exact_terms)
        if locator:
            targets.insert(0, locator[1])
        compact_targets = {
            compact_alphanumeric(target) for target in targets if compact_alphanumeric(target)
        }
        direct_matches: list[SearchResult] = []
        for candidate in candidates:
            searchable = compact_alphanumeric(
                "\n".join(
                    [candidate.heading or "", *candidate.heading_path, candidate.content]
                )
            )
            if any(target in searchable for target in compact_targets):
                normalized_score = min(1.0, max(0.0, candidate.score))
                candidate.score = 0.75 + 0.25 * normalized_score
                direct_matches.append(candidate)
        if direct_matches:
            return self._apply_trust_and_freshness(direct_matches)
        return self._apply_trust_and_freshness(candidates)

    async def _llm_rerank(self, query: str, candidates: list[SearchResult]) -> list[SearchResult]:
        compact = [
            {
                "candidate_id": item.chunk_id,
                "title": item.title,
                "heading": item.heading,
                "text": item.content[:2000],
            }
            for item in candidates
        ]
        response = await self.client.structured_chat(
            [
                {"role": "system", "content": RERANK_SYSTEM},
                {"role": "user", "content": json.dumps({"query": query, "candidates": compact})},
            ],
            RerankResponse,
        )
        scores = {item.candidate_id: item.relevance for item in response.items}
        for candidate in candidates:
            if candidate.chunk_id in scores:
                candidate.score = 0.4 * candidate.score + 0.6 * scores[candidate.chunk_id]
        return sorted(candidates, key=lambda item: item.score, reverse=True)[: self.top_k]

    def _apply_trust_and_freshness(self, candidates: list[SearchResult]) -> list[SearchResult]:
        trust_factor = {
            "human-reviewed": 1.08,
            "machine-confirmed": 1.04,
            "unverified": 1.0,
        }
        for candidate in candidates:
            candidate.score *= trust_factor.get(candidate.trust_tier, 1.0)
            if candidate.status == "stable":
                candidate.score *= 1.03
            elif candidate.status == "deprecated":
                candidate.score *= 0.65
            if candidate.is_stale:
                candidate.score *= 0.75
            candidate.score = min(1.0, max(0.0, candidate.score))
        return sorted(candidates, key=lambda item: item.score, reverse=True)[: self.top_k]
