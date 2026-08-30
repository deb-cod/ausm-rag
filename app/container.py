from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.agents.answer_generator import AnswerGenerator
from app.agents.evidence_checker import EvidenceChecker
from app.agents.planner import RetrievalPlanner
from app.agents.query_analyzer import QueryAnalyzer
from app.config import Settings
from app.embeddings.ollama_embeddings import OllamaEmbeddings
from app.knowledge.graph import KnowledgeGraph
from app.knowledge.okf import discover_concepts
from app.llm.ollama_client import OllamaClient
from app.rag.orchestrator import SmartRAGOrchestrator
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.index import QdrantIndex
from app.retrieval.relationship_expander import RelationshipExpander
from app.retrieval.reranker import AdaptiveReranker


@dataclass
class AppContainer:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker[Session]
    ollama: OllamaClient
    embeddings: OllamaEmbeddings
    qdrant_client: AsyncQdrantClient
    index: QdrantIndex

    def orchestrator(self, session: Session) -> SmartRAGOrchestrator:
        graph = KnowledgeGraph(discover_concepts(self.settings.okf_dir), self.settings.okf_dir)
        return SmartRAGOrchestrator(
            session=session,
            analyzer=QueryAnalyzer(
                self.ollama, self.settings.cache_dir, self.settings.max_subqueries
            ),
            planner=RetrievalPlanner(self.settings.max_subqueries),
            retriever=HybridRetriever(self.settings, self.embeddings, self.qdrant_client),
            expander=RelationshipExpander(self.settings, self.qdrant_client, graph),
            reranker=AdaptiveReranker(
                self.ollama, self.settings.enable_llm_rerank, self.settings.rerank_top_k
            ),
            checker=EvidenceChecker(self.settings, self.ollama),
            generator=AnswerGenerator(self.ollama),
            max_rounds=self.settings.max_retrieval_rounds,
        )
