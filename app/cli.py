import argparse
import asyncio
import json
from pathlib import Path

from qdrant_client import AsyncQdrantClient

from app.config import get_settings
from app.database.session import create_database_engine, initialize_database, make_session_factory
from app.embeddings.ollama_embeddings import OllamaEmbeddings
from app.evaluation import compute_metrics
from app.ingestion.chunker import StructureAwareChunker
from app.ingestion.markitdown_converter import MarkItDownConverter
from app.ingestion.okf_builder import OKFBuilder
from app.ingestion.pipeline import IngestionPipeline
from app.llm.ollama_client import OllamaClient
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.index import QdrantIndex


async def rebuild_index() -> None:
    settings = get_settings()
    engine = create_database_engine(settings)
    initialize_database(engine)
    factory = make_session_factory(engine)
    ollama = OllamaClient(settings)
    embeddings = OllamaEmbeddings(ollama)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    index = QdrantIndex(settings, embeddings, qdrant)
    try:
        with factory() as session:
            pipeline = IngestionPipeline(
                settings,
                session,
                MarkItDownConverter(),
                OKFBuilder(settings.okf_dir, settings.ollama_llm_model),
                StructureAwareChunker(settings.chunk_target_tokens, settings.chunk_overlap_tokens),
                index,
            )
            result = await pipeline.rebuild_index()
            print(json.dumps(result, indent=2))
    finally:
        await ollama.close()
        await qdrant.close()
        engine.dispose()


async def evaluate(path: Path) -> None:
    settings = get_settings()
    questions = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    ollama = OllamaClient(settings)
    embeddings = OllamaEmbeddings(ollama)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)
    retriever = HybridRetriever(settings, embeddings, qdrant)
    expected: list[list[str]] = []
    retrieved: list[list[str]] = []
    try:
        for item in questions:
            if not item.get("expected_concepts"):
                continue
            batch = await retriever.search(item["question"])
            expected.append(item["expected_concepts"])
            retrieved.append([result.concept_id for result in batch.results])
        print(json.dumps(compute_metrics(expected, retrieved).__dict__, indent=2))
    finally:
        await ollama.close()
        await qdrant.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="smart-rag")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("rebuild-index", help="Recreate Qdrant entirely from canonical OKF")
    evaluator = subcommands.add_parser("evaluate", help="Run the labelled retrieval evaluation")
    evaluator.add_argument(
        "--questions", type=Path, default=Path("tests/evaluation/questions.jsonl")
    )
    args = parser.parse_args()
    if args.command == "rebuild-index":
        asyncio.run(rebuild_index())
    elif args.command == "evaluate":
        asyncio.run(evaluate(args.questions))


if __name__ == "__main__":
    main()
