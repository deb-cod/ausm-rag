import json

from app.config import Settings
from app.llm.ollama_client import OllamaClient, OllamaError
from app.llm.prompts import EVIDENCE_SYSTEM
from app.llm.schemas import QueryPlan, QueryType, SufficiencyAssessment
from app.retrieval.models import SearchResult
from app.utils.text import (
    compact_alphanumeric,
    find_numbered_heading,
    parse_locator_query,
    tokenize,
)


class EvidenceChecker:
    def __init__(self, settings: Settings, client: OllamaClient):
        self.settings = settings
        self.client = client

    async def assess(self, plan: QueryPlan, evidence: list[SearchResult]) -> SufficiencyAssessment:
        fallback = self._deterministic(plan, evidence)
        if not evidence or plan.query_type not in {
            QueryType.COMPARISON,
            QueryType.MULTI_HOP,
            QueryType.ANALYTICAL,
            QueryType.SYNTHESIS,
        }:
            return fallback
        try:
            snippets = [
                {"id": item.chunk_id, "title": item.title, "text": item.content[:1800]}
                for item in evidence
            ]
            return await self.client.structured_chat(
                [
                    {"role": "system", "content": EVIDENCE_SYSTEM},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"query_plan": plan.model_dump(mode="json"), "evidence": snippets}
                        ),
                    },
                ],
                SufficiencyAssessment,
            )
        except OllamaError:
            return fallback

    def _deterministic(
        self, plan: QueryPlan, evidence: list[SearchResult]
    ) -> SufficiencyAssessment:
        if not evidence:
            return SufficiencyAssessment(
                sufficient=False,
                confidence=0.0,
                missing_aspects=["relevant supporting evidence"],
                refinement_query=plan.standalone_query + " documentation details",
            )
        if plan.query_type == QueryType.LOCATOR:
            locator = parse_locator_query(plan.standalone_query)
            target = locator[1] if locator else next(iter(plan.exact_terms), "")
            matching = [
                item
                for item in evidence
                if find_numbered_heading(item.content, target)
            ]
            if not matching:
                return SufficiencyAssessment(
                    sufficient=False,
                    confidence=0.1,
                    missing_aspects=[f"numbered heading for {target}"],
                    refinement_query=f'"{target}" table of contents numbered heading',
                )
            confidence = min(0.98, 0.7 + 0.25 * max(item.score for item in matching))
            return SufficiencyAssessment(
                sufficient=True,
                confidence=confidence,
                covered_aspects=[f"location of {target}"],
            )
        joined = " ".join(item.content.casefold() for item in evidence)
        query_terms = {
            token
            for token in tokenize(plan.standalone_query)
            if token not in {"what", "which", "when", "where", "does", "about", "with", "the"}
        }
        evidence_terms = set(tokenize(joined))
        lexical_coverage = len(query_terms & evidence_terms) / max(1, len(query_terms))
        compact_query = compact_alphanumeric(plan.standalone_query)
        direct_match = bool(compact_query) and any(
            compact_query in compact_alphanumeric(item.content) for item in evidence
        )
        dense_score = max((item.channel_scores.get("dense", 0.0) for item in evidence), default=0.0)
        if dense_score < self.settings.min_evidence_score and lexical_coverage < 0.1:
            return SufficiencyAssessment(
                sufficient=False,
                confidence=0.1,
                missing_aspects=["relevant supporting evidence"],
                refinement_query=plan.standalone_query + " exact documentation",
            )
        missing = [target for target in plan.comparison_targets if target.casefold() not in joined]
        rank_score = sum(item.score for item in evidence[:3]) / min(3, len(evidence))
        confidence = min(
            0.95,
            max(0.0, 0.45 * rank_score + 0.35 * max(0.0, dense_score) + 0.2 * lexical_coverage),
        )
        if direct_match:
            confidence = max(confidence, 0.95)
        return SufficiencyAssessment(
            sufficient=not missing,
            confidence=confidence if not missing else confidence * 0.5,
            covered_aspects=[target for target in plan.comparison_targets if target not in missing],
            missing_aspects=missing,
            refinement_query=(
                f"{plan.standalone_query} specifically {' and '.join(missing)}" if missing else None
            ),
        )
