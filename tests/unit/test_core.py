from pathlib import Path

import frontmatter
import pytest

from app.agents.answer_generator import AnswerGenerator
from app.agents.evidence_checker import EvidenceChecker
from app.agents.planner import RetrievalPlanner
from app.agents.query_analyzer import QueryAnalyzer
from app.config import Settings
from app.ingestion.chunker import StructureAwareChunker
from app.ingestion.security import InvalidUpload, validate_upload
from app.knowledge.okf import OKFConcept, OKFGenerated, OKFSource, parse_concept
from app.llm.schemas import QueryPlan, QueryType
from app.rag.state import QueryResponse
from app.retrieval.models import SearchResult
from app.retrieval.reranker import AdaptiveReranker
from app.retrieval.sparse import LocalSparseEncoder


class FailingClient:
    async def structured_chat(self, *args, **kwargs):
        raise RuntimeError("not used")


class DraftingClient:
    def __init__(self):
        self.calls = []

    async def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        if len(self.calls) == 1:
            return "A very short summary [1]."
        return " ".join(["Supported"] * 450) + " [1]."


def concept(tmp_path: Path, body: str) -> OKFConcept:
    return OKFConcept(
        concept_id="documents/test/topic",
        path=tmp_path / "topic.md",
        type="Reference",
        title="Topic",
        tags=["test"],
        status="draft",
        generated=OKFGenerated(by="process:test", at="2026-08-30T00:00:00Z"),
        sources=[OKFSource(id="doc-1", resource="/references/doc.txt", title="doc.txt")],
        body=body,
        extra={"document_id": "doc-1", "source_sha256": "abc"},
    )


def test_chunker_preserves_table_and_code(tmp_path: Path):
    body = """# Authentication

Intro paragraph about authentication.

| Method | Enabled |
|---|---|
| SSO | yes |

```python
def authenticate():
    return True
```
"""
    chunks = StructureAwareChunker(target_tokens=100, overlap_tokens=10).chunk(
        concept(tmp_path, body)
    )
    combined = "\n".join(item.content for item in chunks)
    assert "| SSO | yes |" in combined
    assert "def authenticate():\n    return True" in combined
    assert all(item.heading == "Authentication" for item in chunks)


def test_okf_round_trip_and_required_type(tmp_path: Path):
    path = tmp_path / "concept.md"
    post = frontmatter.Post(
        "# Body\nKnowledge.",
        type="Policy",
        title="Policy",
        status="draft",
        generated={"by": "process:test", "at": "2026-08-30T00:00:00Z"},
        sources=[{"id": "x", "resource": "/references/x.pdf", "title": "X"}],
    )
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    parsed = parse_concept(path, tmp_path)
    assert parsed.type == "Policy"
    assert parsed.sources[0].resource == "/references/x.pdf"
    assert "verified" not in parsed.frontmatter()


def test_upload_validation_blocks_traversal_and_spoofed_pdf(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    with pytest.raises(InvalidUpload):
        validate_upload("../secret.txt", b"text", settings)
    with pytest.raises(InvalidUpload):
        validate_upload("fake.pdf", b"not pdf", settings)


def test_comparison_fallback_and_canonical_sparse_indices(tmp_path: Path):
    analyzer = QueryAnalyzer(FailingClient(), tmp_path, 6)  # type: ignore[arg-type]
    plan = analyzer.fallback("Compare Qdrant vs Chroma for filtering and speed")
    assert plan.query_type == QueryType.COMPARISON
    assert plan.comparison_targets == ["Qdrant", "Chroma"]
    assert plan.comparison_dimensions == ["filtering", "speed"]
    encoder = LocalSparseEncoder()
    first = encoder.encode("Qdrant filtering filtering")
    second = encoder.encode("Qdrant filtering filtering")
    assert first.indices == second.indices
    assert first.values == second.values


def test_sparse_encoder_matches_pdf_text_even_when_spaces_are_lost():
    encoder = LocalSparseEncoder()
    spaced = encoder.encode("which indicates whether the mobile supports IPv4 IPv6 or both")
    joined = encoder.encode("whichindicateswhetherthemobilesupportsIPv4IPv6orboth")

    shared_features = set(spaced.indices) & set(joined.indices)

    assert len(shared_features) >= 20


def test_retrieval_plan_and_citation_validation(tmp_path: Path):
    analyzer = QueryAnalyzer(FailingClient(), tmp_path, 6)  # type: ignore[arg-type]
    analysis = analyzer.fallback("Compare Qdrant vs Chroma for filtering")
    plan = RetrievalPlanner(6).build(analysis)
    assert set(plan.entity_queries) == {"Qdrant", "Chroma"}
    assert plan.rerank
    assert AnswerGenerator.validate_citations("Supported [1], invalid [9].", 2) == (
        "Supported [1], invalid ."
    )
    assert AnswerGenerator.validate_citations("Supported.", 2).endswith("Source: [1]")
    assert AnswerGenerator.validate_citations("Supported [1, 2, 9].", 2) == (
        "Supported [1] [2]."
    )
    assert "[Preface]" not in AnswerGenerator.validate_citations("Supported [Preface].", 2)


def test_explicit_summary_request_is_repaired_and_broadly_planned(tmp_path: Path):
    analyzer = QueryAnalyzer(FailingClient(), tmp_path, 6)  # type: ignore[arg-type]
    query = "Provide the whole summary of the book in 500 words"
    unreliable_plan = QueryPlan(
        original_query=query,
        standalone_query=query,
        query_type=QueryType.FACTUAL,
    )

    repaired = analyzer._repair(unreliable_plan, query)
    retrieval = RetrievalPlanner(6).build(repaired)

    assert repaired.query_type == QueryType.SUMMARIZATION
    assert len(retrieval.queries) == 3
    assert any("main themes" in item for item in retrieval.queries)


@pytest.mark.asyncio
async def test_summary_honors_requested_length_with_corrective_retry():
    client = DraftingClient()
    generator = AnswerGenerator(client)  # type: ignore[arg-type]
    query = "Provide the whole summary of the book in 500 words"
    plan = QueryPlan(
        original_query=query,
        standalone_query=query,
        query_type=QueryType.SUMMARIZATION,
    )
    evidence = [
        SearchResult(
            chunk_id="summary-source",
            document_id="doc",
            concept_id="concept",
            content="The document introduces its purpose, develops its main themes, and concludes.",
            title="Book",
            source_file="book.pdf",
            source_sha256="abc",
            okf_type="Reference",
            score=0.9,
        )
    ]

    answer = await generator.generate(plan, evidence, sufficient=True)

    assert len(client.calls) == 2
    assert client.calls[0][1]["max_tokens"] == 900
    assert "approximately 500 words" in client.calls[0][0][1]["content"]
    assert generator.word_count(answer) >= 400


def test_locator_query_is_repaired_and_planned_as_exact_lookup(tmp_path: Path):
    analyzer = QueryAnalyzer(FailingClient(), tmp_path, 6)  # type: ignore[arg-type]
    query = "Third Generation Systems is in which section?"
    unreliable_model_plan = QueryPlan(
        original_query=query,
        standalone_query=query,
        query_type=QueryType.FACTUAL,
        entities=["Third Generation Systems"],
        retrieval_strategy="none",
    )

    repaired = analyzer._repair(unreliable_model_plan, query)
    retrieval = RetrievalPlanner(6).build(repaired)

    assert repaired.query_type == QueryType.LOCATOR
    assert repaired.retrieval_strategy == "locator"
    assert repaired.exact_terms == ["Third Generation Systems"]
    assert retrieval.queries == ["Third Generation Systems", query]


def test_bare_topic_cannot_be_misclassified_as_locator(tmp_path: Path):
    analyzer = QueryAnalyzer(FailingClient(), tmp_path, 6)  # type: ignore[arg-type]
    query = "Default EPS Bearer Context Request?"
    unreliable_model_plan = QueryPlan(
        original_query=query,
        standalone_query=query,
        query_type=QueryType.LOCATOR,
        retrieval_strategy="locator",
    )

    repaired = analyzer._repair(unreliable_model_plan, query)

    assert repaired.query_type == QueryType.DEFINITION
    assert repaired.retrieval_strategy == "standard"
    assert repaired.exact_terms == ["Default EPS Bearer Context Request"]


@pytest.mark.asyncio
async def test_locator_ranking_and_answer_use_numbered_heading(tmp_path: Path):
    irrelevant = SearchResult(
        chunk_id="references",
        document_id="doc",
        concept_id="concept",
        content="Section 7. Section 8. General specification references.",
        title="References",
        source_file="book.pdf",
        source_sha256="abc",
        okf_type="Reference",
        score=0.95,
    )
    exact = SearchResult(
        chunk_id="target",
        document_id="doc",
        concept_id="concept",
        content=(
            "1.2 HistoryofMobileTelecommunicationSystems\n"
            "The preceding flattened PDF sentence ends here. 1.2.2 ThirdGenerationSystems\n"
            "The world's dominant 3G system is UMTS."
        ),
        title="Introduction",
        source_file="book.pdf",
        source_sha256="abc",
        okf_type="Reference",
        score=0.55,
    )
    query = "Third Generation Systems is in which section?"
    plan = QueryPlan(
        original_query=query,
        standalone_query=query,
        query_type=QueryType.LOCATOR,
        entities=["Third Generation Systems"],
        exact_terms=["Third Generation Systems"],
        retrieval_strategy="locator",
    )
    reranker = AdaptiveReranker(FailingClient(), enabled=True, top_k=8)  # type: ignore[arg-type]

    ranked = await reranker.rerank(query, [irrelevant, exact], plan.query_type, plan.exact_terms)

    assert [item.chunk_id for item in ranked] == ["target"]
    assert AnswerGenerator._locator_answer(plan, ranked) == (
        '"Third Generation Systems" is in section **1.2.2** [1].'
    )

    checker = EvidenceChecker(Settings(data_dir=tmp_path), FailingClient())  # type: ignore[arg-type]
    assessment = await checker.assess(plan, ranked)
    assert assessment.sufficient
    assert assessment.confidence >= 0.7


@pytest.mark.asyncio
async def test_direct_clause_ranks_glued_pdf_passage_and_extracts_antecedent(tmp_path: Path):
    query = "which indicates whether the mobile supports IPv4, IPv6 or both"
    irrelevant = SearchResult(
        chunk_id="unrelated",
        document_id="doc",
        concept_id="concept",
        content=(
            "The mobile supports voice over IMS. IPv4 and IPv6 addresses are assigned during "
            "the broader attach procedure."
        ),
        title="Unrelated",
        source_file="book.pdf",
        source_sha256="abc",
        okf_type="Reference",
        score=0.95,
    )
    exact = SearchResult(
        chunk_id="exact",
        document_id="doc",
        concept_id="concept",
        content=(
            "ThemobilethencomposesanESMmessage,PDNConnectivityRequest. "
            "The message includes a\nPDNtype,whichindicateswhetherthemobile"
            "supportsIPv4,IPv6orboth."
        ),
        title="Attach Request",
        source_file="book.pdf",
        source_sha256="abc",
        okf_type="Reference",
        score=0.55,
    )
    plan = QueryPlan(
        original_query=query,
        standalone_query=query,
        query_type=QueryType.FACTUAL,
    )
    reranker = AdaptiveReranker(FailingClient(), enabled=True, top_k=8)  # type: ignore[arg-type]

    ranked = await reranker.rerank(query, [irrelevant, exact], plan.query_type)

    assert ranked[0].chunk_id == "exact"
    assert AnswerGenerator._clause_answer(plan, ranked) == (
        "The **PDN type** indicates whether the mobile supports IPv4, IPv6 or both [1]."
    )
    checker = EvidenceChecker(Settings(data_dir=tmp_path), FailingClient())  # type: ignore[arg-type]
    assessment = await checker.assess(plan, ranked)
    assert assessment.sufficient
    assert assessment.confidence == 0.95


def test_followup_comparison_rewriting(tmp_path: Path):
    analyzer = QueryAnalyzer(FailingClient(), tmp_path, 6)  # type: ignore[arg-type]
    plan = analyzer.fallback(
        "How does it compare with Chroma?",
        [{"role": "user", "content": "Tell me about Qdrant."}],
    )
    assert plan.query_type == QueryType.COMPARISON
    assert plan.standalone_query == "Compare Qdrant with Chroma."
    assert plan.comparison_targets == ["Qdrant", "Chroma"]


def test_query_response_exposes_trace_id():
    response = QueryResponse(
        query_id="query-1",
        trace_id="query-1",
        session_id="session",
        answer="Supported [1]",
        query_type="factual",
        standalone_query="Question",
        comparison_targets=[],
        confidence=0.8,
        no_answer=False,
        retrieval_rounds=1,
        latency_ms=10,
        sources=[],
    )
    assert response.trace_id == response.query_id


@pytest.mark.asyncio
async def test_no_answer_when_evidence_missing(tmp_path: Path):
    settings = Settings(data_dir=tmp_path)
    checker = EvidenceChecker(settings, FailingClient())  # type: ignore[arg-type]
    assessment = await checker.assess(
        QueryPlan(original_query="Unknown?", standalone_query="Unknown?"), []
    )
    assert not assessment.sufficient
    assert assessment.confidence == 0


@pytest.mark.asyncio
async def test_comparison_requires_both_targets(tmp_path: Path):
    settings = Settings(data_dir=tmp_path, min_evidence_score=0.1)
    checker = EvidenceChecker(settings, FailingClient())  # type: ignore[arg-type]
    plan = QueryPlan(
        original_query="A vs B",
        standalone_query="A vs B",
        query_type=QueryType.COMPARISON,
        comparison_targets=["Product A", "Product B"],
        retrieval_strategy="comparison",
    )
    evidence = [
        SearchResult(
            chunk_id="c",
            document_id="d",
            concept_id="x",
            content="Product A supports local mode.",
            title="A",
            source_file="a.md",
            source_sha256="x",
            okf_type="Reference",
            score=0.8,
        )
    ]
    assessment = checker._deterministic(plan, evidence)
    assert not assessment.sufficient
    assert assessment.missing_aspects == ["Product B"]
