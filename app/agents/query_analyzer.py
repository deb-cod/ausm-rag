import hashlib
import json
import re
from pathlib import Path

from app.llm.ollama_client import OllamaClient, OllamaError
from app.llm.prompts import QUERY_ANALYSIS_SYSTEM
from app.llm.schemas import QueryPlan, QueryType
from app.utils.text import parse_locator_query

COMPARISON_RE = re.compile(
    r"(?:compare\s+)?(.+?)\s+(?:vs\.?|versus|compared\s+(?:to|with)|and)\s+(.+?)(?:\s+for\s+|\s+on\s+|[?.!,]|$)",
    re.IGNORECASE,
)
FOLLOWUP_RE = re.compile(r"\b(it|that|this|those|they|them|former|latter|above)\b", re.I)
FOLLOWUP_COMPARE_RE = re.compile(
    r"\bcompare\s+(?:it|that|this)?\s*(?:with|to)\s+(.+?)[?.!]*$", re.I
)
SUMMARY_RE = re.compile(r"\b(summar(?:y|ize|ise)|overview|synopsis|recap)\b", re.I)
QUESTION_OPENERS = {
    "compare",
    "define",
    "describe",
    "explain",
    "how",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
}


class QueryAnalyzer:
    def __init__(self, client: OllamaClient, cache_dir: Path, max_subqueries: int):
        self.client = client
        self.cache_dir = cache_dir / "query_analysis"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_subqueries = max_subqueries

    async def analyze(self, query: str, history: list[dict[str, str]]) -> QueryPlan:
        history = history[-8:]
        cache_key = hashlib.sha256(
            json.dumps({"query": query, "history": history}, sort_keys=True).encode()
        ).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"
        if cache_path.exists():
            try:
                plan = QueryPlan.model_validate_json(cache_path.read_text(encoding="utf-8"))
                plan = self._repair(plan, query)
                cache_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
                return plan
            except Exception:
                cache_path.unlink(missing_ok=True)
        try:
            plan = await self.client.structured_chat(
                [
                    {"role": "system", "content": QUERY_ANALYSIS_SYSTEM},
                    {
                        "role": "user",
                        "content": json.dumps({"chat_history": history, "current_query": query}),
                    },
                ],
                QueryPlan,
            )
            plan.original_query = query
            plan.subquestions = plan.subquestions[: self.max_subqueries]
        except OllamaError:
            plan = self.fallback(query, history)
        plan = self._repair(plan, query)
        cache_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        return plan

    @staticmethod
    def _repair(plan: QueryPlan, query: str) -> QueryPlan:
        """Enforce invariants that must not depend on small-model structured output quality."""
        plan.original_query = query
        locator = parse_locator_query(plan.standalone_query) or parse_locator_query(query)
        if locator:
            _kind, target = locator
            plan.query_type = QueryType.LOCATOR
            plan.retrieval_strategy = "locator"
            plan.entities = list(dict.fromkeys([target, *plan.entities]))
            plan.exact_terms = list(dict.fromkeys([target, *plan.exact_terms]))
            plan.subquestions = []
            plan.requires_decomposition = False
        elif SUMMARY_RE.search(query):
            # Do not let a small structured-output model turn an explicit summary request into a
            # one-passage factual lookup.
            plan.query_type = QueryType.SUMMARIZATION
            plan.retrieval_strategy = "standard"
        elif plan.query_type == QueryType.LOCATOR or plan.retrieval_strategy == "locator":
            # A small model can over-apply a recently described query type. Locator mode is
            # allowed only when deterministic syntax identifies a requested location.
            words = re.findall(r"[\w-]+", query)
            terse_topic = bool(words) and words[0].casefold() not in QUESTION_OPENERS
            plan.query_type = QueryType.DEFINITION if terse_topic else QueryType.FACTUAL
            plan.retrieval_strategy = "standard"
            if terse_topic:
                topic = query.strip(" \t\r\n'\"?.!")
                plan.entities = list(dict.fromkeys([topic, *plan.entities]))
                plan.exact_terms = list(dict.fromkeys([topic, *plan.exact_terms]))
        elif plan.query_type != QueryType.NO_RETRIEVAL and plan.retrieval_strategy == "none":
            plan.retrieval_strategy = "standard"
        return plan

    def fallback(self, query: str, history: list[dict[str, str]] | None = None) -> QueryPlan:
        lowered = query.casefold()
        match = COMPARISON_RE.search(query)
        followup_compare = FOLLOWUP_COMPARE_RE.search(query)
        targets: list[str] = []
        query_type = QueryType.FACTUAL
        strategy = "standard"
        standalone = query
        requires_context = False
        locator = parse_locator_query(query)
        if locator:
            _kind, target = locator
            targets = [target]
            query_type = QueryType.LOCATOR
            strategy = "locator"
        elif followup_compare and history:
            last_user = next(
                (item["content"] for item in reversed(history) if item.get("role") == "user"), ""
            )
            previous_topic = re.sub(
                r"^(?:tell me about|what is|explain)\s+", "", last_user, flags=re.I
            ).strip(" .?!")
            new_target = followup_compare.group(1).strip(" ,")
            targets = [previous_topic, new_target] if previous_topic else [new_target]
            standalone = f"Compare {' with '.join(targets)}."
            query_type = QueryType.COMPARISON
            strategy = "comparison"
            requires_context = True
        elif match and any(term in lowered for term in ("compare", " vs", "versus", "different")):
            targets = [match.group(1).strip(" ,"), match.group(2).strip(" ,")]
            query_type = QueryType.COMPARISON
            strategy = "comparison"
        elif lowered.startswith(("how ", "how do", "how can")):
            query_type = QueryType.HOW_TO
        elif lowered.startswith(("what is", "define", "what does")):
            query_type = QueryType.DEFINITION
        elif any(word in lowered for word in ("summarize", "summary", "overview")):
            query_type = QueryType.SUMMARIZATION
        elif any(word in lowered for word in ("across", "relationship between", "combine")):
            query_type = QueryType.MULTI_HOP
            strategy = "multi_hop"
        requires_context = requires_context or (bool(FOLLOWUP_RE.search(query)) and bool(history))
        if requires_context and history and query_type != QueryType.COMPARISON:
            last_user = next(
                (item["content"] for item in reversed(history) if item.get("role") == "user"), ""
            )
            standalone = f"Regarding the previous question '{last_user}': {query}"
            query_type = QueryType.FOLLOW_UP
        dimensions = []
        if targets and " for " in lowered:
            dimensions = [
                item.strip(" .?")
                for item in re.split(r",|\band\b", query.split(" for ", 1)[1], flags=re.I)
                if item.strip(" .?")
            ]
        subquestions = (
            []
            if query_type == QueryType.LOCATOR
            else [f"What does the knowledge base say about {target}?" for target in targets]
        )
        return QueryPlan(
            original_query=query,
            standalone_query=standalone,
            query_type=query_type,
            entities=targets,
            comparison_targets=targets if query_type == QueryType.COMPARISON else [],
            comparison_dimensions=dimensions,
            exact_terms=targets,
            subquestions=subquestions,
            requires_decomposition=bool(subquestions),
            requires_conversation_context=requires_context,
            retrieval_strategy=strategy,
        )
