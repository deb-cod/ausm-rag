# AUSM Smart RAG — Presentation Dialogue and Speaker Script

This script matches `AUSM_Smart_RAG_Complete_Presentation.pptx` exactly. Slides 1–21 form the main presentation. Slides 22–32 are the technical component appendix. Present all slides for a deep technical session of roughly 45–55 minutes, or stop after slide 21 for a 25–35 minute overview and use the appendix to answer technical questions.

The wording is intentionally direct. Do not claim that hallucination is impossible, that confidence is a probability of truth, or that the current local deployment is already production-hardened. Those boundaries are explained explicitly below.

<!-- SLIDE 1 -->
## Slide 1 — AUSM Smart RAG

SAY

“Today I will show AUSM Smart RAG, a local document-question-answering system. Its purpose is simple: we upload approved documents, ask questions in normal language, and receive answers that are tied to visible source passages. The important words are local, grounded, and inspectable. Local means the language model, embeddings, database, and vector search run on this computer by default. Grounded means the model is instructed to answer from retrieved document evidence rather than general memory. Inspectable means we can see citations, confidence signals, retrieval rounds, latency, and diagnostic traces.

This is not being presented as a general chatbot or as a system that makes model errors impossible. It is a controlled retrieval-and-answering layer over a private document collection. I will cover the user journey, architecture, ingestion, retrieval, persistence, setup, failure recovery, limitations, and then a component-level appendix.”

TRANSITION

“Before looking at individual technologies, let us reduce the entire system to one minute.”

<!-- SLIDE 2 -->
## Slide 2 — The whole system in one minute

SAY

“There are three user-visible stages. First, upload: the system validates the file, extracts readable text, converts it into a structured knowledge format, divides it into meaningful passages, and indexes those passages. Second, ask: the system understands the question, searches both by meaning and by exact wording, checks whether the retrieved material is sufficient, and can make one bounded retry when coverage is weak. Third, verify: the final answer exposes its source passages and operational details so a person can inspect the evidence.

RAG means retrieval-augmented generation. Retrieval happens before generation. Instead of asking the model to answer from everything it learned during training, we first supply the most relevant passages from our indexed documents. The model then writes from that bounded evidence. This is why the system is useful for private manuals, policies, specifications, reports, and books. It remains a document assistant; questions outside the indexed collection should receive an honest no-answer.”

TRANSITION

“Now that the behavior is clear, here is the problem this design is solving.”

<!-- SLIDE 3 -->
## Slide 3 — Why this exists

SAY

“The problem is not merely that documents are long. Search requirements conflict. Sometimes users remember the meaning but not the wording. Sometimes they need an exact identifier such as an error code, protocol name, or clause. A conventional chatbot may respond fluently while using outside knowledge or inventing a connection. For professional use, fluent text without evidence is not enough.

AUSM addresses those problems with local storage and inference, combined semantic and lexical retrieval, an evidence-sufficiency gate, citations, and saved traces. This reduces model risk but does not eliminate it. A citation proves which passage was supplied; a human should still verify high-stakes conclusions. Confidence is also not a mathematically calibrated probability of truth. It summarizes retrieval and evidence quality. The business value is faster access to internal knowledge while preserving provenance, privacy, and the ability to investigate why an answer was produced.”

TRANSITION

“Let us follow the workflow from the user’s point of view before opening the architecture.”

<!-- SLIDE 4 -->
## Slide 4 — What a user actually does

SAY

“A user begins in Library and uploads one or more supported files. The upload is complete only after validation, conversion, chunking, vector indexing, and registration succeed. The user then opens Ask and uses a conversation ID. Keeping the same ID is what gives follow-up questions access to recent conversation context. A new ID starts a deliberately clean conversation.

The answer screen is not limited to prose. It shows whether the evidence check passed, the query type, confidence, retrieval rounds, latency, and cited passages. Operations shows service health and allows reindexing. Insights summarizes query and comparison patterns. Diagnostics exposes plans and retrieval traces.

A good demonstration should include four question types: a simple factual question, a broader summary, a follow-up that uses earlier context, and a comparison. This proves that the system changes its retrieval and answer behavior according to the request rather than returning the same style every time.”

TRANSITION

“Those screens all sit on top of one local architecture.”

<!-- SLIDE 5 -->
## Slide 5 — Local deployment architecture

SAY

“The browser opens Streamlit on port 8501. Streamlit is the presentation layer; it does not contain a second RAG implementation. It calls FastAPI on port 8000 through documented REST or server-sent-event endpoints. FastAPI validates requests and delegates to the agentic RAG workflow. The workflow uses Ollama on port 11434 for local language and embedding models, and Qdrant on port 6333 for vector retrieval.

Three persistence areas have different purposes. Files and OKF preserve source knowledge in an inspectable form. SQLite records documents, sessions, messages, queries, plans, retrieval runs, citations, and analytics. Qdrant stores the derived search index. These are local loopback services unless someone intentionally changes the configuration.

If Streamlit stops, the API and stored knowledge remain. If FastAPI stops, data remains but clients cannot use it. If Qdrant is lost, it can be rebuilt from OKF. If Ollama is unavailable, language and embedding operations cannot complete.”

TRANSITION

“The next slide explains why these parts are separated instead of putting everything in one database.”

<!-- SLIDE 6 -->
## Slide 6 — One component, one responsibility

SAY

“Each technology has one primary responsibility. FastAPI is the stable application contract. Streamlit is the human workspace. Ollama is the local model runtime. Qdrant is the fast dense-and-sparse retrieval index. OKF is the readable canonical knowledge representation used for provenance, chunking, relationships, and rebuild. SQLite is operational memory: it records what was uploaded, what was asked, what was retrieved, and what was answered.

This separation is deliberate, not unnecessary duplication. Vector databases are optimized for similarity search, but they are not convenient master editing or auditing formats. SQLite is excellent for relational history, but it is not a semantic search engine. OKF is portable and inspectable, but scanning all files for every question would be inefficient. Separating concerns also improves recovery: the UI can be replaced without changing retrieval, and the Qdrant collection can be replaced without re-uploading documents when canonical OKF remains.”

TRANSITION

“With responsibilities established, we can examine exactly what happens during upload.”

<!-- SLIDE 7 -->
## Slide 7 — Document ingestion: from file to searchable knowledge

SAY

“Ingestion is a controlled pipeline. Validation checks file size, allowed extension, safe naming, and content signatures such as the PDF header. SHA-256 identifies exact duplicate content. MarkItDown then extracts normalized Markdown and useful metadata. The OKF builder wraps the converted text with document identity, provenance, hash, tags, generation information, and a self-contained source reference.

The structure-aware chunker divides the concept by headings and semantic blocks. It attempts to keep tables and code fences intact and uses overlap so ideas at boundaries are not lost. Each chunk retains source file, heading path, document and concept IDs, trust information, freshness, and the original hash. EmbeddingGemma produces dense vectors, a local sparse encoder produces exact-word features, and Qdrant stores both. SQLite is marked ready only after the required work succeeds.

Image-only PDFs contain pixels rather than extractable text. They must be OCR-processed before upload; changing the extension cannot create text.”

TRANSITION

“The ingestion output leads to the most important storage distinction in this project.”

<!-- SLIDE 8 -->
## Slide 8 — OKF is the source of truth; Qdrant is replaceable

SAY

“Here, ‘source of truth’ means the canonical knowledge representation used to reconstruct search—not that the original upload is discarded. The project preserves the original source, normalized Markdown, and an OKF concept. OKF contains readable content plus metadata and provenance. Qdrant is generated from the chunks and embeddings derived from those concepts.

Therefore OKF is not just an archive. It actively feeds chunking and rebuild, carries fields that become retrieval metadata, and supplies relationships for optional graph expansion. Qdrant serves ordinary search because it is much faster than scanning files. If Qdrant’s Docker volume disappears or an embedding dimension changes, `rebuild-index` discovers the remaining OKF concepts, rechunks them, recreates the collection, and indexes them again.

The cache is different from both. It stores reusable embeddings and query analyses. Removing cache may make future work slower, but it does not remove canonical knowledge. Final answers are not blindly returned from this cache.”

TRANSITION

“That hierarchy makes duplicate, replacement, deletion, and restart behavior predictable.”

<!-- SLIDE 9 -->
## Slide 9 — Duplicate, update, delete, and restart behavior

SAY

“If the uploaded bytes have an existing SHA-256 hash, the system returns the existing document and does not index a duplicate. If the filename matches but the content hash changes, it is treated as a replacement. The new version receives a new ID and is completely converted and indexed first. Only after success is the old version removed. This protects the last working copy from a broken replacement.

Deleting through Library or the API coordinates all stores: Qdrant points, document-specific OKF and reference artifacts, normalized Markdown, original source files, and the SQLite document record are removed. Deleting an OKF file manually does not notify Qdrant. Existing vectors can continue answering until a rebuild recreates Qdrant from the OKF files that remain.

A computer restart does not require re-uploading. Restart Docker Desktop, Ollama, FastAPI, and Streamlit. Persistence depends on preserving the project `data` directory and the Qdrant named Docker volume.”

TRANSITION

“Now we move from the document lifecycle to the lifecycle of a question.”

<!-- SLIDE 10 -->
## Slide 10 — Question flow: analyze, retrieve, verify, answer

SAY

“A question first passes request validation. The analyzer then classifies the query, identifies exact terms and comparison targets, incorporates recent conversation context, and produces a standalone query. The planner converts that analysis into one or several bounded searches. This matters because a summary may need multiple thematic searches while a locator question should remain focused.

The retriever runs semantic and exact search, optionally expands linked OKF concepts, and reranks candidates. The evidence checker decides whether those passages cover the requested claim. If not, it can suggest one refinement and the orchestrator performs another round. The default maximum is two retrieval rounds and six subqueries, so ‘agentic’ does not mean uncontrolled autonomy or endless loops.

If evidence remains weak, the system returns a supported no-answer. If it is sufficient, the generator selects focused excerpts, adapts length and structure, writes the answer, validates citation markers, stores the trace, and returns the response.”

TRANSITION

“The reason retrieval has multiple stages becomes clearer when we compare meaning search with exact search.”

<!-- SLIDE 11 -->
## Slide 11 — Why retrieval uses two search channels

SAY

“Dense search uses embeddings. It is valuable when the question and document express the same idea with different words. Sparse search protects exact language such as names, clause numbers, error codes, protocol labels, and quoted fragments. This implementation also uses compact character features because extracted PDFs sometimes join words that were visually separated.

The two result lists are combined using reciprocal-rank fusion. Fusion rewards passages that rank well without assuming dense and sparse raw scores are directly comparable. The fused candidate set is then reranked. Reranking considers directness, exact-term coverage, comparison balance, trust metadata, and freshness. Optional LLM reranking can be used, while deterministic scoring remains available.

The default flow narrows approximately fifteen fused candidates to eight evidence candidates. Dense search alone may miss exact identifiers; sparse search alone may miss paraphrases. Together they increase recall, and reranking improves precision before the answer model sees the evidence.”

TRANSITION

“Finding relevant text is not enough; the system still needs an explicit answer policy.”

<!-- SLIDE 12 -->
## Slide 12 — Grounded answers and adaptive detail

SAY

“Answer depth follows the request. A simple factual question should receive a direct answer rather than an unnecessary essay. A summary or analysis triggers broader retrieval and structured synthesis. A comparison attempts to balance both targets. A how-to request should return ordered steps when the evidence supports them.

The model receives evidence-only instructions. Retrieved document text is treated as untrusted content, not as executable instructions, which helps defend against prompt injection inside documents. Citation numbers are checked against the number of supplied sources, and impossible markers are removed. When a user requests a word count, the generation budget expands accordingly; an obviously short first draft can receive one correction attempt.

Confidence remains an evidence-quality signal rather than proof. A complete-looking answer may still require human review. Conversely, a no-answer is an intended safety result: it means the indexed evidence did not justify a supported response.”

TRANSITION

“Adaptive answering also depends on understanding genuine follow-up questions.”

<!-- SLIDE 13 -->
## Slide 13 — Follow-up conversations are real persisted context

SAY

“Conversation continuity is based on the session ID. SQLite stores both user and assistant messages. When a new question arrives, the analyzer receives up to the eight most recent messages and uses them to interpret references such as ‘that’, ‘it’, or ‘the second approach’. It then rewrites the request as a standalone retrieval query.

The important boundary is that conversation history helps interpret the question; it is not automatically treated as factual document evidence. Retrieval still searches indexed documents, and the answer still depends on retrieved passages. This prevents an unsupported statement from an earlier message from silently becoming a trusted source.

The Streamlit frontend reloads stored messages when a known session is reopened, so navigation or a UI restart does not erase the conversation. Choosing a new session ID intentionally creates a clean context. If SQLite is lost, conversation and trace history disappear even if Qdrant still contains searchable vectors.”

TRANSITION

“The same conversation capability is available through both the UI and the API.”

<!-- SLIDE 14 -->
## Slide 14 — Two interfaces, one backend contract

SAY

“Streamlit organizes the capabilities for a person: Ask handles grounded chat and citations; Library handles upload, listing, and coordinated deletion; Operations displays health and rebuild controls; Insights shows aggregates; Diagnostics exposes detailed plans and retrieval traces.

FastAPI exposes the actual application contract. It provides ingestion, document lifecycle, normal JSON query, streaming query, conversation messages, query history, trace, analytics, statistics, and health endpoints. Interactive Swagger documentation is available at `http://localhost:8000/docs`.

There is no hidden path where Streamlit writes directly to a database. Its API client uses the same endpoints another application would use. This means a React interface, mobile client, command-line tool, or enterprise integration can replace Streamlit without rewriting the RAG core. It also keeps lifecycle rules consistent: upload and delete behavior remains the same regardless of the calling interface.”

TRANSITION

“Next is the exact setup expected on a new Windows computer.”

<!-- SLIDE 15 -->
## Slide 15 — New-computer setup: Windows

SAY

“The supported setup assumes Git, 64-bit Python 3.12, Docker Desktop, and Ollama. Python 3.10 is not sufficient for this project’s declared environment, but Python versions can coexist. We do not copy a virtual environment between computers because it contains machine-specific paths and compiled packages.

After cloning the repository, `setup.ps1` discovers Python 3.12, creates or safely recreates `.venv`, installs the pinned direct dependencies, creates `.env` when needed, verifies or pulls the generation and embedding models, starts Qdrant, and waits for health. `doctor.ps1` independently checks Python, environment consistency, Ollama, both models, Docker, Qdrant, Ruff, and Pytest.

The first setup can take time because Python wheels and local model files are downloaded. Later runs use caches and should be faster. Setup should be run only after Docker Desktop and Ollama are started.”

TRANSITION

“Once installation is complete, daily startup is much shorter.”

<!-- SLIDE 16 -->
## Slide 16 — Daily startup and live-demo script

SAY

“For normal use, confirm Docker Desktop and Ollama are running. Start FastAPI in one terminal and Streamlit in a second terminal using the project’s `.venv` Python. The API is then available at `localhost:8000`, and the UI at `localhost:8501`.

For a reliable live demo, I first open Operations and prove that FastAPI, SQLite, Qdrant, Ollama, and the expected models are healthy. I then upload a small text-based PDF in Library. In Ask, I use a precise factual question, a broad summary, a follow-up, and a comparison. I expand citations and open Diagnostics to show the retrieval plan and trace. Finally, reopening the same conversation demonstrates persistence.

Before presenting, both models should already be pulled and a known-good file should be available. The first inference after model loading can be slower, so warm the model before the audience arrives.”

TRANSITION

“If something does fail, diagnosis should follow the failing stage rather than guesswork.”

<!-- SLIDE 17 -->
## Slide 17 — Troubleshooting by symptom

SAY

“Start with `doctor.ps1` and the `/health` response. A health request can return an HTTP response while still reporting a degraded component, so read the JSON body. ‘API offline’ usually means Uvicorn is not running or the URL is wrong. A Qdrant failure points to Docker Desktop, the container, or port 6333. An Ollama or model failure points to port 11434 or missing model files.

Upload errors are stage-specific. ‘File extension and PDF content do not match’ means the bytes are not a genuine PDF. ‘Conversion produced no text’ usually means an image-only scan requiring OCR. ‘No indexed information’ means the Library is empty, Qdrant is unavailable, or the index must be rebuilt from existing OKF.

An unrelated answer should be investigated through citations and the trace: confirm extraction quality, query classification, dense and sparse candidates, and final evidence. First-answer latency often reflects Ollama loading a model into memory.”

TRANSITION

“Operational recovery is only one side of trust; security boundaries and limitations must also be explicit.”

<!-- SLIDE 18 -->
## Slide 18 — Security boundaries and honest limitations

SAY

“Built-in controls include local inference and storage, upload validation, safe filename handling, prompt-injection instructions, evidence gating, no-answer behavior, citation validation, loopback service defaults, and exclusion of generated knowledge data from Git.

The current boundaries are equally important. There is no built-in OCR, authentication, user authorization, multi-tenancy, high availability, or production monitoring stack. Retrieval quality depends on source quality and successful text extraction. Confidence is heuristic. Manual changes to OKF do not automatically synchronize Qdrant. Citations reduce the chance of unsupported claims but cannot guarantee model correctness.

Therefore the correct description is a modular, testable local system—not a fully hardened multi-user production service. Before production use, add identity and access control, network security, secret management, backup and restore procedures, monitoring, rate limits, data-retention policy, OCR where required, and deployment-specific testing. High-stakes decisions still require human review.”

TRANSITION

“Within that declared scope, several concrete reliability and quality improvements have already been verified.”

<!-- SLIDE 19 -->
## Slide 19 — What was hardened during implementation

SAY

“Setup was hardened through Python 3.12 discovery, virtual-environment recreation, pinned direct dependencies, and doctor checks. PDF handling now distinguishes invalid PDF content from valid files with no extractable text. Retrieval was improved for joined PDF words, exact locator questions, comparison detection, and sentence fragments.

Answer generation now adapts context and length to the request, including larger budgets and a correction attempt for requested long summaries. Persistence includes the Qdrant named volume, OKF-based rebuilding, and saved conversation messages loaded by the UI. Streamlit issues such as invalid avatars, header overlap, URL normalization, and follow-up display were addressed.

The evidence is not only a feature list: the current suite contains 32 passing automated tests, supported by live health and real-stack query checks performed during implementation. Tests reduce regression risk, but they do not prove every document or question will work. Evaluation should continue with representative domain questions and known expected sources.”

TRANSITION

“The next two slides answer the architecture and operation questions people most commonly raise.”

<!-- SLIDE 20 -->
## Slide 20 — Frequently asked questions: architecture

SAY

“Why not keep everything only in Qdrant? Because vectors are derived and inconvenient to review or edit. OKF keeps knowledge readable and rebuildable, while SQLite preserves operational history. Why is the cache present? To avoid repeating deterministic embedding and analysis work; it is not another source of truth.

Does normal querying use the internet? No. After packages and Ollama models have been installed, ordinary model inference, embedding, retrieval, and persistence remain local unless configuration is intentionally changed. Why are there two models? Generating language and measuring semantic similarity are different tasks, so Gemma 4 handles language while EmbeddingGemma creates vectors.

What makes the workflow agentic? Specialized stages analyze, plan, retrieve, assess, and adapt. The behavior is bounded by maximum subqueries and retrieval rounds. It cannot browse freely, execute arbitrary tools, or continue indefinitely. Separation of concerns is what makes these parts independently testable, recoverable, and replaceable.”

TRANSITION

“The corresponding operational answers are just as concrete.”

<!-- SLIDE 21 -->
## Slide 21 — Frequently asked questions: operation

SAY

“A restart does not require re-upload when the `data` directory and Qdrant volume remain. Start the services again. The same filename with identical bytes is detected as a duplicate; the same filename with changed content becomes a safe replacement built before removal of the old version.

Deleting OKF by hand does not immediately delete Qdrant. Coordinated deletion must use Library or the API. If a manual OKF change was intentional, rebuild Qdrant from the remaining OKF concepts. Can the system hallucinate? The risk is reduced through retrieval, evidence checks, no-answer behavior, citations, and source inspection, but it is not eliminated. Can another frontend use it? Yes; the full contract is documented through Swagger and `api_documentation.md`.

The main conclusion is: private knowledge goes in, a recoverable search index is built, and evidence-backed answers come out. The following slides are a technical appendix explaining every major component’s input, output, failure impact, and recovery path.”

TRANSITION

“For a non-technical audience, stop here and move to the demo. For a technical audience, continue into the component catalog.”

<!-- SLIDE 22 -->
## Slide 22 — Frontend components: the human workspace

SAY

“The frontend has four major responsibilities. `frontend/app.py` controls the five pages and translates user actions into API-client calls. `frontend/api_client.py` is the only HTTP boundary; it normalizes the base URL, handles REST and SSE, decodes responses, and converts network or HTTP failures into readable errors. The conversation renderer loads saved messages and presents the answer, evidence, confidence, rounds, and latency. `frontend/styles.py` owns layout and visual consistency.

No frontend component writes directly to SQLite, OKF, or Qdrant. That rule prevents the UI from bypassing lifecycle validation. If Streamlit fails, users lose the workspace temporarily, but the API, models, index, and stored data remain. If styles fail, functionality remains but presentation quality drops. If the API client cannot connect, its message tells the operator to start Uvicorn and inspect health. This separation makes the UI replaceable and keeps backend behavior authoritative.”

TRANSITION

“The backend receives those calls through a thin API layer.”

<!-- SLIDE 23 -->
## Slide 23 — Backend components: API and dependency wiring

SAY

“`app/main.py` owns application startup and shutdown, route registration, database initialization, and client cleanup. `app/container.py` is dependency wiring: it constructs validated settings, the SQLite engine and sessions, Ollama and embedding clients, the Qdrant client and index, the OKF graph, and the RAG orchestrator.

Document routes handle upload, list, delete, and rebuild. Query routes handle normal and streaming answers, conversation messages, query detail, and trace. Analytics and health routes expose aggregates and dependency state. These route functions remain intentionally thin: they validate transport data, create request-scoped database sessions, delegate to domain services, and translate known failures into HTTP responses.

If the API process stops, no endpoint is available, but persisted stores are not erased. If dependency wiring fails, the failure appears at startup or request construction rather than producing a partially initialized system. External clients and Streamlit both receive the same contract.”

TRANSITION

“The document routes delegate the most complex write operation to the ingestion pipeline.”

<!-- SLIDE 24 -->
## Slide 24 — Ingestion components: safe file processing

SAY

“The upload validator operates before expensive work. It creates a safe filename, enforces the configured size and allowed types, checks signatures where applicable, and calculates SHA-256. The converter then uses MarkItDown to produce normalized Markdown and source metadata. A converter failure is reported explicitly; a scanned PDF needs OCR because the converter cannot infer text from pixels.

`IngestionPipeline` coordinates every store. It writes the original source, saves converted Markdown, builds OKF, creates chunks, indexes Qdrant, and registers SQLite. On failure it rolls back database work, deletes new Qdrant points where possible, and removes partial files. Exact duplicate hashes return the existing record.

For same-name changed content, the new document is fully indexed first. The old document is deleted only after success. Delete and rebuild are also centralized here so normal application actions preserve cross-store consistency.”

TRANSITION

“The next components turn converted text into canonical, structured knowledge.”

<!-- SLIDE 25 -->
## Slide 25 — Knowledge components: OKF, structure, and links

SAY

“The OKF builder creates a version 0.2 concept using YAML frontmatter and Markdown. It records type, title, tags, status, generation details, document ID, source hash, and a reference to a copied original source. The parser validates required metadata and preserves producer extension fields rather than discarding them.

The chunker reads the OKF concept body. It recognizes headings, lists, tables, and code blocks, creates semantic groups with overlap, and copies provenance and lifecycle metadata into every chunk. Stable IDs connect Qdrant evidence back to its document and concept.

The knowledge graph discovers sibling concepts and explicit Markdown links. Relationship expansion can add directly related concepts within a configured hop limit. It is best-effort: missing relationships do not stop dense and sparse retrieval.

This is the precise reason OKF is not merely an archive. It is the inspectable master representation for chunking, rebuild, provenance, metadata, and graph relationships.”

TRANSITION

“Those knowledge files sit beside two other persistence mechanisms with different jobs.”

<!-- SLIDE 26 -->
## Slide 26 — Persistence components: files, SQLite, and cache

SAY

“The filesystem under `data` stores the uploaded source, normalized Markdown, OKF concepts and references, cache files, and the SQLite database file. The SQLite schema stores operational entities: documents, sessions, messages, queries, plans, retrieval runs and results, answer sources, comparison counts, and feedback-ready records.

The repository centralizes transactions and queries so application code does not scatter SQL behavior. It is responsible for recent conversation messages, document lookup by filename or hash, trace assembly, statistics, and analytics.

Cache has a narrower purpose. Embedding entries are keyed by model and exact content, while query-analysis entries depend on the query and history. Cache can be deleted safely; missing entries are recomputed. It should not be the primary backup target.

For backup, prioritize original sources, OKF, and SQLite. Qdrant is useful to back up for fast recovery, but it is derived. Cache preserves processing time, not knowledge.”

TRANSITION

“The derived index itself contains several distinct search structures.”

<!-- SLIDE 27 -->
## Slide 27 — Qdrant components: the replaceable search index

SAY

“`QdrantIndex` manages collection health, creation, dimension checking, batched indexing, document deletion, and full recreation. Each point contains a dense vector, a sparse vector, and payload. Dense vectors represent semantic meaning from EmbeddingGemma. Sparse vectors represent deterministic token and compact character features for exact and spacing-resistant matching.

Payload contains the passage text and everything required for filtering and citation: document and concept IDs, source filename, heading path, tags, trust tier, freshness, source hash, and other source metadata. The Docker named volume persists the collection across ordinary container restarts.

When an embedding model produces a different dimension, the application does not silently mix incompatible vectors. It raises a clear rebuild requirement. Rebuild recreates the configured collection from the OKF concepts. Qdrant is therefore operationally important for speed but architecturally replaceable.”

TRANSITION

“Vectors and answers are produced by two separate local model responsibilities.”

<!-- SLIDE 28 -->
## Slide 28 — Model components: local generation and embeddings

SAY

“Ollama is the model runtime on port 11434. It hosts model files and accepts local HTTP requests; it is not a database and does not store project documents as knowledge. `OllamaClient` handles timeouts, chat, streaming, structured JSON, retry behavior, and embedding batches.

The configured language model, `gemma4:e4b`, performs query analysis, optional model-assisted ranking and evidence assessment, and grounded answer generation. The smaller model can make structured-output mistakes, so deterministic validation, repair, and fallback logic protect critical planning behavior.

`embeddinggemma` maps document chunks and questions into dense vectors. The vector dimension is detected at runtime rather than hard-coded. Changing to a model with another dimension requires rebuilding Qdrant so all stored vectors remain compatible.

Both models run locally for normal use after installation. They perform different jobs: one generates and interprets language, while the other measures semantic similarity.”

TRANSITION

“The retrieval layer combines those embeddings with exact lexical evidence.”

<!-- SLIDE 29 -->
## Slide 29 — Retrieval components: finding and ordering evidence

SAY

“`HybridRetriever` embeds each subquery, sends a dense search and a sparse search to Qdrant, and fuses the rankings. Optional filters restrict retrieval to selected document or concept IDs. For locator-style questions, compact versions of target text help match PDFs where extraction removed spaces.

`LocalSparseEncoder` is deterministic and local. It creates stable indices for words and compact character features, so it does not require Elasticsearch or another external lexical service. Relationship expansion can add passages from OKF-linked concepts after initial retrieval.

`AdaptiveReranker` improves precision. Locator questions emphasize exact compact coverage. General scoring considers directness, trust, freshness, and comparison balance. Optional LLM reranking can refine ordering, but deterministic behavior remains when that feature is disabled or fails.

The sequence is intentional: first retrieve broadly enough to avoid missing evidence, then narrow and order it before the evidence checker evaluates sufficiency.”

TRANSITION

“Those candidates are handled by four specialized decision stages.”

<!-- SLIDE 30 -->
## Slide 30 — Agent components: bounded decision stages

SAY

“The query analyzer acts like an analyst. It reads the question and recent history, determines query type, resolves follow-up references, extracts exact terms, comparison targets, and document filters, and emits a validated QueryPlan. Its repair and fallback logic prevents an empty or obviously unsafe plan.

The retrieval planner acts like a search strategist. It turns the QueryPlan into a bounded RetrievalPlan with no more than the configured number of subqueries. The evidence checker acts like a reviewer. It evaluates whether the reranked passages cover the request, assigns an evidence confidence signal, and may propose one refinement query.

The answer generator acts like a controlled writer. It selects appropriate evidence, focuses excerpts, chooses structure and word budget, produces a grounded answer or no-answer, and validates citations.

Calling these components agents describes specialization and adaptive decisions. They remain ordinary testable classes inside a strict orchestrated workflow, not independent autonomous processes.”

TRANSITION

“The orchestrator connects those roles and records what happened.”

<!-- SLIDE 31 -->
## Slide 31 — Orchestration and observability components

SAY

“`SmartRAGOrchestrator` is the central state machine. It loads conversation history, analyzes and plans, records the query, executes each subquery, balances merged results, expands relationships, reranks evidence, checks sufficiency, performs at most the configured number of rounds, generates the answer, attaches citations, stores messages and sources, and returns QueryResponse.

Typed Pydantic models define QueryPlan, RetrievalPlan, SearchResult, RetrievalBatch, RAGState, and QueryResponse. These explicit contracts catch malformed data at stage boundaries.

The repository records the analysis, retrieval plan, every retrieval run, candidate counts, result ranks, evidence, confidence, latency, final sources, and comparison analytics. Diagnostics reconstructs this trace. Structured logging adds operation and timing fields for runtime troubleshooting.

Therefore the ‘agent’ is not hidden inside a framework. Its sequence is readable in `app/rag/orchestrator.py`, while typed state, SQLite traces, and structured logs make behavior explainable.”

TRANSITION

“The final component group makes the same architecture reproducible on another computer.”

<!-- SLIDE 32 -->
## Slide 32 — Runtime, configuration, and verification components

SAY

“`Settings` centralizes service URLs, model names, paths, timeouts, retrieval limits, thresholds, and feature flags, loading them from `.env` with validated defaults. `docker-compose.yml` pins Qdrant, exposes loopback ports, defines a health check, and attaches a persistent named volume.

`setup.ps1` builds the machine-local environment and starts dependencies. `doctor.ps1` verifies the result and names the failing prerequisite instead of leaving the operator with a vague symptom. The tests cover core parsing and retrieval logic, database behavior, ingestion lifecycle, frontend client behavior, Ollama response handling, evaluation, and a local Qdrant integration path.

These are architectural components because reliable operation is not separate from software design. Reproducible setup, explicit configuration, health checks, persistent storage, traceability, and tests determine whether the system can be trusted and maintained.

To close: every major component has one responsibility, known inputs and outputs, a visible failure mode, and a recovery path. That is what makes AUSM Smart RAG understandable, inspectable, and replaceable rather than a black box.”

FINAL CLOSE

“Thank you. I will now demonstrate the upload, query, citations, follow-up memory, and diagnostic trace using the same architecture we have just examined.”
