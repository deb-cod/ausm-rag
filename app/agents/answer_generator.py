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
WORD_COUNT_RE = re.compile(r"\b(\d{2,5})\s*(?:-|\s)?\s*words?\b", re.IGNORECASE)


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
        excerpt_limit = 4000 if plan.query_type.value == "summarization" else 2800
        evidence_text = "\n\n".join(
            f"[{number}] Source: {item.source_file}; heading: {item.heading or item.title}\n"
            f"Trust: {item.trust_tier}; status: {item.status or 'unspecified'}; "
            f"stale: {item.is_stale}\n"
            f"{self._focused_excerpt(plan, item.content, limit=excerpt_limit)}"
            for number, item in enumerate(selected_evidence, 1)
        )
        target_words = self.requested_word_count(plan.original_query)
        generation_words = target_words or self.default_word_count(plan)
        answer_instructions = self.answer_instructions(plan, target_words)
        prompt = (
            f"Question: {plan.original_query}\nStandalone question: {plan.standalone_query}\n\n"
            f"Query type: {plan.query_type.value}\n"
            f"Comparison targets: {plan.comparison_targets}\n"
            f"Comparison dimensions: {plan.comparison_dimensions}\n\n"
            f"Evidence:\n{evidence_text}\n\n"
            f"Response requirements:\n{answer_instructions}\n"
            "Use only the evidence above. Include numeric citations for supported claims."
        )
        answer = await self.client.chat(
            [
                {"role": "system", "content": ANSWER_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            max_tokens=self.generation_token_budget(generation_words),
        )
        if target_words and self.word_count(answer) < target_words * 0.6:
            answer = await self.client.chat(
                [
                    {"role": "system", "content": ANSWER_SYSTEM},
                    {"role": "user", "content": prompt},
                    {"role": "assistant", "content": answer},
                    {
                        "role": "user",
                        "content": (
                            f"The draft is only {self.word_count(answer)} words and does not "
                            f"satisfy the requested approximately {target_words}-word response. "
                            "Rewrite it as a complete, evidence-grounded answer. Cover distinct "
                            "major points rather than repeating one detail, and retain citations."
                        ),
                    },
                ],
                max_tokens=self.generation_token_budget(target_words),
            )
        return self.validate_citations(answer, len(selected_evidence))

    @staticmethod
    def requested_word_count(query: str) -> int | None:
        match = WORD_COUNT_RE.search(query)
        if not match:
            return None
        return min(2000, max(50, int(match.group(1))))

    @staticmethod
    def default_word_count(plan: QueryPlan) -> int | None:
        defaults = {
            "summarization": 400,
            "comparison": 350,
            "analytical": 400,
            "synthesis": 400,
            "multi_hop": 350,
            "exploratory": 350,
            "how_to": 250,
        }
        return defaults.get(plan.query_type.value)

    @staticmethod
    def generation_token_budget(target_words: int | None) -> int | None:
        if target_words is None:
            return None
        return min(4096, max(512, int(target_words * 1.8)))

    @staticmethod
    def word_count(text: str) -> int:
        return len(re.findall(r"\b[\w'-]+\b", text))

    @staticmethod
    def answer_instructions(plan: QueryPlan, target_words: int | None) -> str:
        query_type = plan.query_type.value
        if query_type == "summarization":
            length = (
                f"Aim for approximately {target_words} words (within about 10% when the evidence "
                "supports that length)."
                if target_words
                else "Provide a substantive overview of roughly 300-500 words."
            )
            return " ".join(
                (
                    length,
                    "Synthesize the document's purpose, major themes, important developments, "
                    "and conclusions across the supplied sections.",
                    "Use a short opening overview followed by clear thematic paragraphs or "
                    "headings; do not mistake one isolated passage for the whole document.",
                    "If the supplied evidence covers only part of the document, state that "
                    "limitation instead of pretending the summary is complete.",
                )
            )
        if query_type == "comparison":
            return (
                "Give a balanced, descriptive comparison. Start with a short conclusion, then "
                "compare each requested target across the supported dimensions, preferably in a "
                "compact table, and clearly identify missing evidence."
            )
        if query_type in {"analytical", "synthesis", "multi_hop", "exploratory"}:
            return (
                "Develop a structured explanation that connects the relevant evidence, explains "
                "why the points matter, and states any evidence limitations."
            )
        if query_type == "how_to":
            return (
                "Give a practical step-by-step explanation, including prerequisites, important "
                "warnings, and the expected result when those details are supported."
            )
        return (
            "Answer the exact question directly. Keep a simple factual, definition, or location "
            "answer concise, but include enough surrounding explanation to make it understandable."
        )

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
