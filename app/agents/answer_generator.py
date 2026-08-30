import re

from app.llm.ollama_client import OllamaClient
from app.llm.prompts import ANSWER_SYSTEM
from app.llm.schemas import QueryPlan
from app.retrieval.models import SearchResult
from app.utils.text import (
    find_compact_span,
    find_numbered_heading,
    humanize_compound_label,
    parse_locator_query,
)

NO_ANSWER = (
    "I don't have enough supported information in the indexed knowledge base to answer that."
)


class AnswerGenerator:
    def __init__(self, client: OllamaClient):
        self.client = client

    async def generate(
        self, plan: QueryPlan, evidence: list[SearchResult], sufficient: bool
    ) -> str:
        if not sufficient or not evidence:
            return NO_ANSWER
        locator_answer = self._locator_answer(plan, evidence)
        if locator_answer:
            return locator_answer
        clause_answer = self._clause_answer(plan, evidence)
        if clause_answer:
            return clause_answer
        selected_evidence = self._select_evidence(plan, evidence)
        evidence_text = "\n\n".join(
            f"[{number}] Source: {item.source_file}; heading: {item.heading or item.title}\n"
            f"Trust: {item.trust_tier}; status: {item.status or 'unspecified'}; "
            f"stale: {item.is_stale}\n"
            f"{self._focused_excerpt(plan, item.content)}"
            for number, item in enumerate(selected_evidence, 1)
        )
        prompt = (
            f"Question: {plan.original_query}\nStandalone question: {plan.standalone_query}\n\n"
            f"Query type: {plan.query_type.value}\n"
            f"Comparison targets: {plan.comparison_targets}\n"
            f"Comparison dimensions: {plan.comparison_dimensions}\n\n"
            f"Evidence:\n{evidence_text}\n\n"
            "Answer only the exact question from this evidence. Prefer the passage that most "
            "directly matches the wording. Give the direct answer in the first sentence, omit "
            "unrelated background, and include numeric citations for supported claims."
        )
        answer = await self.client.chat(
            [
                {"role": "system", "content": ANSWER_SYSTEM},
                {"role": "user", "content": prompt},
            ]
        )
        return self.validate_citations(answer, len(selected_evidence))

    @staticmethod
    def _select_evidence(plan: QueryPlan, evidence: list[SearchResult]) -> list[SearchResult]:
        if plan.query_type.value in {"factual", "definition", "document_specific", "follow_up"}:
            return evidence[:4]
        return evidence

    @staticmethod
    def _focused_excerpt(plan: QueryPlan, content: str, limit: int = 2800) -> str:
        if len(content) <= limit:
            return content
        candidates = [
            plan.standalone_query,
            *plan.exact_terms,
            *plan.entities,
        ]
        candidates.sort(key=len, reverse=True)
        for candidate in candidates:
            span = find_compact_span(content, candidate)
            if not span:
                continue
            midpoint = (span[0] + span[1]) // 2
            start = max(0, midpoint - limit // 2)
            end = min(len(content), start + limit)
            start = max(0, end - limit)
            return content[start:end]
        return content[:limit]

    @staticmethod
    def _clause_answer(plan: QueryPlan, evidence: list[SearchResult]) -> str | None:
        query = plan.standalone_query.strip()
        clause = re.match(r"^(?:which|that|who)\s+(?P<predicate>.+?)[?.!]*$", query, re.I)
        if not clause:
            return None
        for citation, item in enumerate(evidence, 1):
            span = find_compact_span(item.content, query)
            if not span:
                continue
            prefix = item.content[max(0, span[0] - 240) : span[0]]
            antecedent_match = re.search(
                r"(?:includes?|contains?|carries?|has|uses)\s+(?:an?|the)?\s*"
                r"(?P<label>[A-Za-z][A-Za-z0-9_+./\-\s]{0,80}?)\s*,\s*$",
                prefix,
                re.IGNORECASE,
            )
            if not antecedent_match:
                antecedent_match = re.search(
                    r"(?P<label>[A-Za-z][A-Za-z0-9_+./\-]{1,60})\s*,\s*$", prefix
                )
            if not antecedent_match:
                continue
            label = humanize_compound_label(antecedent_match.group("label"))
            predicate = clause.group("predicate").strip(" \t\r\n?.!")
            if label and predicate:
                return f"The **{label}** {predicate} [{citation}]."
        return None

    @staticmethod
    def _locator_answer(plan: QueryPlan, evidence: list[SearchResult]) -> str | None:
        locator = parse_locator_query(plan.standalone_query)
        if not locator:
            return None
        kind, target = locator
        for citation, item in enumerate(evidence, 1):
            heading = find_numbered_heading(item.content, target)
            if not heading:
                continue
            number, title = heading
            if kind == "chapter":
                chapter = number.split(".", 1)[0]
                return f'"{target}" is in chapter **{chapter}** [{citation}].'
            if kind == "page":
                page_match = re.search(r"\s+(\d+)\s*$", title)
                if page_match:
                    return f'"{target}" starts on page **{page_match.group(1)}** [{citation}].'
                continue
            return f'"{target}" is in section **{number}** [{citation}].'
        return None

    @staticmethod
    def validate_citations(answer: str, source_count: int) -> str:
        """Drop impossible markers and keep the actual evidence visible."""
        if source_count <= 0:
            return re.sub(r"\[\d+\]", "", answer).strip()

        def normalize_markers(match: re.Match[str]) -> str:
            numbers = [int(value) for value in re.findall(r"\d+", match.group(1))]
            valid = list(dict.fromkeys(number for number in numbers if 1 <= number <= source_count))
            return " ".join(f"[{number}]" for number in valid)

        validated = re.sub(r"\[([\d,\s]+)\]", normalize_markers, answer).strip()
        validated = re.sub(r"\[(?!\d+(?:[\s,]+\d+)*\])[^\]\r\n]+\]", "", validated).strip()
        if not re.search(r"\[\d+\]", validated):
            validated += "\n\nSource: [1]"
        return validated
