# AUSM Smart RAG

A production-oriented, local-first retrieval-augmented generation service built around Ollama,
MarkItDown, Open Knowledge Format (OKF) v0.2, Qdrant, SQLite, and FastAPI.

This is not a `question -> vector search -> LLM` demo. It has query intelligence,
conversation-aware rewriting, hybrid dense/lexical retrieval, balanced comparison retrieval,
OKF relationship expansion, adaptive reranking, evidence sufficiency checks, bounded retrieval
retries, grounded generation, citations, retrieval traces, and structured query analytics.

For detailed component diagrams, ingestion/query sequences, storage design, and a complete walkthrough
from `git clone` to a cited answer, see [architecture.md](architecture.md).

For a complete beginner-friendly explanation of the project, installation, everyday use, document
uploads, questions, and troubleshooting, see [explaination.md](explaination.md).

For the most detailed plain-English handbook—including the complete architecture and data flows,
setup, operations, troubleshooting, limitations, and all recent retrieval-quality changes—see
[super_explaination.md](super_explaination.md).

For every HTTP endpoint, request and response format, Swagger workflow, error case, and client
example, see [api_documentation.md](api_documentation.md).

For the ready-to-use browser interface and UI-specific setup notes, see
[frontend/README.md](frontend/README.md).

## Requirements

The project supplies exact, tested package versions so pip does not explore broad version ranges:

- `requirements.txt` installs the application, supported document converters, and Streamlit UI;
- `requirements-dev.txt` includes that file and additionally installs Pytest and Ruff;
- `pyproject.toml` mirrors the same direct versions for editable/package installation.

MarkItDown is installed only with `docx`, `pdf`, `pptx`, and `xlsx` extras. HTML, plain text, and
Markdown work through its base installation. Unused Azure, audio, Outlook, and YouTube integrations
are intentionally not installed.

From a newly created and activated virtual environment, either command works:

```powershell
python -m pip install -r requirements.txt
# Or, for development and running tests:
python -m pip install -r requirements-dev.txt
```

The recommended Windows setup remains `scripts/setup.ps1`; it creates `.venv` and installs the full
development environment automatically.

For the default Windows setup, use:

- Windows 10/11 64-bit with virtualization/WSL 2 enabled for Docker Desktop;
- 64-bit Python 3.12, available through either the `py` launcher or `python.exe` on PATH;
- Git;
- Docker Desktop with the Linux container engine running;
- Ollama running on the host;
- at least 16 GB RAM and roughly 15 GB free disk space (the generation model is about 9.6 GB).

The setup script creates `.venv`, installs Python packages, creates `.env`, downloads missing
Ollama models, starts Qdrant, and waits for it to become healthy. Do not copy `.venv` from another
computer; virtual environments contain machine-specific paths and are intentionally gitignored.

## Architecture

```text
Upload -> validation/checksum -> MarkItDown -> normalized Markdown -> OKF v0.2
                                                               -> structured chunks
                                                               -> dense + sparse vectors
                                                               -> Qdrant index

Question -> conversation resolver/query intelligence -> retrieval plan
         -> dense search + sparse search -> reciprocal-rank fusion
         -> comparison balancing + OKF links -> adaptive reranking
         -> trust/freshness adjustment -> evidence sufficiency
         -> optional refined retrieval -> grounded answer + citations
         -> SQLite query analytics and trace
```

OKF is canonical. Qdrant is a disposable search index. If Qdrant is deleted, `rebuild-index`
reconstructs it from `data/okf`.

### Why these components

- **MarkItDown** converts PDF, DOCX, PPTX, XLSX, HTML, text, and Markdown through one local
  conversion boundary while preserving normalized Markdown.
- **OKF v0.2** keeps knowledge portable and inspectable. Concepts are Markdown with YAML
  frontmatter, provenance, generated-by metadata, and lifecycle/trust fields. Automated concepts
  are `draft`; the system never fabricates `verified` or `stale_after` values.
- **Ollama** runs query analysis and grounded generation locally with `gemma4:e4b`. Embeddings use
  `embeddinggemma`; the dimension is detected dynamically.
- **Qdrant** stores named `dense` and `sparse` representations plus filterable payload metadata.
  The sparse channel uses deterministic word and spacing-resistant character features with Qdrant
  collection-level IDF.
- **SQLite** stores documents, sessions, messages, structured query plans, comparison edges,
  retrieval runs/results, citations, feedback-ready records, and analytics—not embeddings.

Hybrid search handles both semantic paraphrases and exact identifiers, names, policy terms, and
error codes. Character features preserve exact matching when PDF extraction incorrectly joins words,
such as `PDNtype,whichindicates...`. Reciprocal-rank fusion combines the rankings without assuming
their raw scores share a scale.

Comparison-aware retrieval searches each target independently and also searches the full question,
preventing the target with more documentation from taking over the evidence set.

“Agentic” means adaptive control: query type changes retrieval shape, complex questions decompose,
evidence coverage is checked, and retrieval can retry within a configured bound. It does not mean
calling the LLM when deterministic code is sufficient.

## Repository layout

```text
app/
  agents/       query analysis, planning, sufficiency, answers
  api/          FastAPI routes and request schemas
  database/     SQLAlchemy schema, initialization, repositories
  embeddings/   embedding interface and Ollama adapter
  ingestion/    validation, MarkItDown, OKF building, chunking, lifecycle
  knowledge/    OKF parser and Markdown-link graph
  llm/          central Ollama client, strict schemas, safe prompts
  rag/          orchestration state machine
  retrieval/    Qdrant index, sparse encoding, filters, RRF, reranking
frontend/
  app.py        Streamlit workspace
  api_client.py FastAPI and SSE client
  styles.py     visual theme
data/
  sources/      original accepted uploads
  markdown/     original MarkItDown output
  okf/          canonical OKF bundle and self-contained references
  cache/        content-addressed embedding/query-analysis caches
  database/     SQLite database
tests/          unit, optional integration, and evaluation data
```

## New-computer setup (Windows)

### 1. Install prerequisites

Install [Git](https://git-scm.com/download/win),
[Python 3.12](https://www.python.org/downloads/),
[Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/), and
[Ollama](https://ollama.com/download/windows). Optional `winget` commands are:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id Docker.DockerDesktop -e
winget install --id Ollama.Ollama -e
```

After installation, restart PowerShell so its PATH is refreshed. Start Docker Desktop and Ollama.
Docker Desktop must report that its engine is running before continuing.

### 2. Clone and run automated setup

```powershell
git clone https://github.com/deb-cod/ausm-rag.git
cd ausm-rag
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

The script is idempotent: rerunning it keeps an existing `.env` and `.venv`, reinstalls only what is
needed, does not redownload installed models, and safely runs `docker compose up -d`.

If models or Docker are managed separately, use:

```powershell
.\scripts\setup.ps1 -SkipModels -SkipDocker
```

### 3. Verify the installation

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\doctor.ps1 -RunTests
```

Every line should show `[OK]`. The doctor checks `.venv`, FastAPI and Streamlit imports, dependency
consistency, Ollama, both models, Docker, Qdrant, Ruff, and Pytest.

### 4. Start the API

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Keep this terminal open. Then visit:

- API documentation: `http://127.0.0.1:8000/docs`
- health report: `http://127.0.0.1:8000/health`
- Qdrant dashboard: `http://127.0.0.1:6333/dashboard`

### 5. Start the browser UI

Keep the API terminal running. Open another PowerShell terminal in the repository root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py `
  --server.address 127.0.0.1 `
  --server.port 8501
```

Open `http://127.0.0.1:8501`. The Streamlit UI supports chat and citations, multi-file upload,
document deletion, health checks, OKF-to-Qdrant reindexing, analytics, query history, and retrieval
traces. It calls the same FastAPI endpoints documented above.

Verify all components in another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 6
```

The top-level health status should be `ok`. A `degraded` result identifies the exact missing or
unreachable component.

### Manual setup (if scripts are disabled)

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env

ollama pull gemma4:e4b
ollama pull embeddinggemma
docker compose up -d
docker compose ps

.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Activating the environment is optional. Calling `.venv\Scripts\python.exe` directly avoids
PowerShell execution-policy problems.

### Linux/macOS setup

Install Python 3.12, Ollama, Docker Engine/Desktop, and the Compose plugin using their official
instructions. Then run:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cp .env.example .env
ollama pull gemma4:e4b
ollama pull embeddinggemma
docker compose up -d
```

Then start `python -m uvicorn app.main:app --reload` and
`python -m streamlit run frontend/app.py` in separate terminals.

### Service layout

Streamlit, FastAPI, and Ollama run on the host; only Qdrant runs in Docker:

```text
Streamlit http://localhost:8501
FastAPI http://localhost:8000
Ollama  http://localhost:11434
Qdrant http://localhost:6333 (REST), localhost:6334 (gRPC)
```

If FastAPI is containerized later, set `OLLAMA_BASE_URL=http://host.docker.internal:11434`. Ollama is
deliberately not containerized by this project.

## Configuration

Important tuning lives in environment variables; see `.env.example`:

- model/service addresses and names;
- chunk target and overlap;
- dense, sparse, fused, and reranked candidate counts;
- maximum subqueries, graph hops, and retrieval rounds;
- LLM reranking and evidence threshold;
- upload size and allowed extensions.

Embedding dimension is detected with a probe before collection creation. Changing to an embedding
model with a different dimension produces an explicit error and requires a rebuild.

## Ingest documents

```powershell
curl.exe -sS -X POST `
  -F "file=@C:\docs\employee-handbook.pdf;type=application/pdf" `
  http://127.0.0.1:8000/api/ingest

Invoke-RestMethod http://127.0.0.1:8000/api/documents
```

`curl.exe` is used because it works in both Windows PowerShell 5.1 and PowerShell 7. In PowerShell
7, `Invoke-RestMethod -Form` is also available.

Ingestion checks extension, filename, maximum size, common file signatures, SHA-256 duplicates, and
text/binary mismatch. Files live under generated document-ID directories, so user paths cannot
escape `data/sources`. Documents are never executed.

Identical bytes return the existing document as a duplicate. The same filename with different bytes
runs the update lifecycle and avoids duplicate vectors.

Delete a document:

```powershell
Invoke-RestMethod -Method Delete `
  -Uri http://127.0.0.1:8000/api/documents/<document-id>
```

Deletion removes its registry, original source, Markdown, OKF document/reference, and Qdrant points.
Content-addressed embedding cache entries can be shared and are safe to retain.

## Ask questions

```powershell
$body = @{
  session_id = 'demo-session'
  query = 'Compare the authentication method in Document A with Document B.'
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/query `
  -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 8
```

The response includes query ID, detected type, standalone query, comparison targets, confidence,
retrieval rounds, answer, and exact source chunks. Reuse the session ID for follow-ups.

Questions asking which section, chapter, or page contains a named topic use an exact-heading lookup.
This lookup tolerates PDF extraction that joins heading words together and returns a short, directly
cited answer instead of a document summary.

Quoted or near-quoted factual fragments receive a direct compact-phrase boost. For fragments such as
`which indicates whether ...`, the answer layer can identify the immediately preceding subject from
the evidence. Simple factual generation uses a small set of query-centered evidence excerpts to
prevent unrelated surrounding material from taking over the answer.

Answer depth adapts to the request. Definitions and locator questions remain concise, while
summaries, comparisons, how-to questions, and analytical requests receive structured detail.
Explicit requests such as `in 500 words` receive a matching Ollama generation budget and are
retried once when the first draft is far too short.

`POST /api/query/stream` uses server-sent events: `query_analyzed`, `retrieving`, `generating`,
`token`, `sources`, and `done`. Only operational status and answer text are exposed—not internal
model reasoning.

Retrieved documents are untrusted data. Instructions inside them cannot override the retrieval or
answer prompts. When evidence is absent, weak, or missing a comparison target, the system returns a
no-answer response rather than filling gaps with outside knowledge. Stale/deprecated concepts are
down-ranked; stable and verified concepts receive a small bounded preference that cannot override
relevance. Staleness is disclosed to answer generation.

## Traces and analytics

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/queries
Invoke-RestMethod http://127.0.0.1:8000/api/queries/<query-id>
Invoke-RestMethod http://127.0.0.1:8000/api/trace/<query-id>
Invoke-RestMethod http://127.0.0.1:8000/api/analytics/questions
Invoke-RestMethod http://127.0.0.1:8000/api/analytics/comparisons
Invoke-RestMethod http://127.0.0.1:8000/api/stats
```

Comparison pairs are case-insensitive and canonicalized, so `A vs B` and `B vs A` increment one
edge while original questions remain available. Traces include each subquery/round, retrieval
strategy, channel candidate counts, fused result count, and latency.

## Rebuild Qdrant from OKF

```powershell
.\.venv\Scripts\python.exe -m app.cli rebuild-index
# Or, with the environment active:
smart-rag rebuild-index
```

This replaces only the configured Qdrant collection, redetects dimension, creates payload indexes,
parses every non-reserved OKF concept, rechunks it, and reindexes it. Source files and analytics are
not deleted.

## Tests and lint

```powershell
.\.venv\Scripts\python.exe -m ruff check app frontend tests
.\.venv\Scripts\python.exe -m pytest -q
```

Tests use fakes or mock HTTP transports for service boundaries where appropriate. Coverage includes
Markdown boundaries, OKF/provenance, security, duplicate/update/delete, structured-output retry,
embeddings, comparison detection and analytics, sufficiency/no-answer, sparse stability, and metrics.

## Retrieval evaluation

`tests/evaluation/questions.jsonl` contains fact, definition, comparison, multi-hop, follow-up, exact
keyword, semantic paraphrase, no-answer, ambiguous, and document-specific examples. Replace the
illustrative concept IDs with IDs from your corpus, then run:

```powershell
.\.venv\Scripts\python.exe -m app.cli evaluate
```

It reports Recall@5, Recall@10, MRR, and nDCG@10. Traces and stored no-answer flags support citation,
subquestion-coverage, and no-answer audits.

## Troubleshooting

- **Start with the doctor:** run `.\scripts\doctor.ps1`; add `-RunTests` for a full check.
- **`docker` is not recognized:** close and reopen the terminal. If needed for the current terminal,
  run `$env:Path += ';C:\Program Files\Docker\Docker\resources\bin'`. The setup/doctor scripts also
  check that standard Docker Desktop location automatically.
- **Docker is installed but unavailable:** start Docker Desktop and wait for "Engine running". Check
  `docker info`, then run `docker compose up -d`.
- **Qdrant is unhealthy:** run `docker compose ps` and `docker compose logs qdrant`. Ensure ports
  6333 and 6334 are not already occupied.
- **Embedding model missing:** run `ollama pull embeddinggemma`; verify with `ollama list`.
- **Generation model missing:** run `ollama pull gemma4:e4b`, or set `OLLAMA_LLM_MODEL` in `.env` to
  another locally installed model that supports chat and structured JSON.
- **Ollama unavailable:** start Ollama and check `http://localhost:11434/api/tags`.
- **`py` is not found:** this means the optional Windows launcher is unavailable. Check
  `python --version`; the setup script now accepts a direct Python 3.12 installation on PATH or in
  its standard per-user location.
- **Only Python 3.10 is found:** install 64-bit Python 3.12 beside it, enable the PATH option, close
  and reopen PowerShell, and then rerun `setup.ps1`. Python 3.10 does not need to be removed.
- **PowerShell blocks scripts:** use `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1`.
- **Dimension changed:** run `python -m app.cli rebuild-index`.
- **Conversion failure:** confirm the extension/signature and that the source is not encrypted or
  corrupted. The API returns a safe error instead of a traceback.
- **FFmpeg warning:** optional MarkItDown audio tooling may warn; supported document ingestion does
  not require audio.

### Updating an existing checkout

```powershell
git pull
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
docker compose pull
docker compose up -d
.\scripts\doctor.ps1
```

If the embedding model changes, rebuild Qdrant from canonical OKF after updating `.env`:

```powershell
.\.venv\Scripts\python.exe -m app.cli rebuild-index
```

### Data persistence and backup

- Original uploads, normalized Markdown, OKF, caches, and SQLite live under `data/`.
- Qdrant uses a Docker named volume (normally `ausm-rag_qdrant_storage`; the prefix follows the
  clone directory).
- `docker compose down` stops services without deleting the volume.
- Do not run `docker compose down -v` unless you intentionally want to delete the Qdrant index.
- Because OKF is canonical, a lost Qdrant volume can be recreated with `rebuild-index`.
- Back up `data/`, especially `data/okf` and `data/database`, according to your backup policy.

Structured logs include IDs, operation, duration, result count, and errors without full document
bodies. Normal runtime uses no hosted LLM, embedding, reranking, or vector API and works offline once
packages and Ollama models are downloaded.
