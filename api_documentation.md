# AUSM Smart RAG API Documentation

This document describes the HTTP API that is implemented in the current project. It is intended for
people testing the API in Swagger, developers calling it from another program, and operators trying
to understand a response or failure.

The API is provided by FastAPI. By default, it runs locally at:

```text
http://127.0.0.1:8000
```

Interactive documentation is available while the API is running:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Raw OpenAPI schema: `http://127.0.0.1:8000/openapi.json`

The complete Streamlit browser workspace is available at `http://127.0.0.1:8501` after running
`python -m streamlit run frontend/app.py`. It exposes the operations documented here through a
friendlier chat, library, operations, insights, and diagnostics interface.

> This version has no authentication or authorization. Do not expose port `8000` to an untrusted
> network or the public internet without adding authentication, authorization, TLS, rate limiting,
> and an appropriate reverse proxy.

## Contents

1. [Starting and checking the API](#1-starting-and-checking-the-api)
2. [API conventions](#2-api-conventions)
3. [Endpoint summary](#3-endpoint-summary)
4. [Health](#4-health)
5. [Document ingestion](#5-document-ingestion)
6. [Document management](#6-document-management)
7. [Rebuilding the Qdrant index](#7-rebuilding-the-qdrant-index)
8. [Asking questions](#8-asking-questions)
9. [Streaming answers with SSE](#9-streaming-answers-with-sse)
10. [Query history and diagnostics](#10-query-history-and-diagnostics)
11. [Analytics and statistics](#11-analytics-and-statistics)
12. [Common errors](#12-common-errors)
13. [Complete workflows](#13-complete-workflows)
14. [Calling the API from Python](#14-calling-the-api-from-python)
15. [Operational and security notes](#15-operational-and-security-notes)
16. [Current API limitations](#16-current-api-limitations)
17. [Implementation map](#17-implementation-map)

---

## 1. Starting and checking the API

Start Docker Desktop and Ollama first. From the project directory in PowerShell:

```powershell
docker compose up -d
ollama serve
```

If Ollama is already running, `ollama serve` may say that the address is already in use. That usually
means there is nothing else to do for Ollama.

Activate the virtual environment and start FastAPI:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Keep that terminal open. In a second PowerShell terminal, check the API:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 8
```

Then open `http://127.0.0.1:8000/docs` in a browser.

## 2. API conventions

### 2.1 Base URL

All examples use:

```text
http://127.0.0.1:8000
```

Most application routes begin with `/api`. The health route is the exception: it is `/health`, not
`/api/health`.

### 2.2 Content types

| Operation | Request content type | Response content type |
| --- | --- | --- |
| Upload a document | `multipart/form-data` | `application/json` |
| Ask a normal question | `application/json` | `application/json` |
| Ask a streaming question | `application/json` | `text/event-stream` |
| GET endpoints | No request body | `application/json` |
| Delete a document | No request body | Empty response |

When uploading with `curl`, do not manually add a `Content-Type: multipart/form-data` header. `curl`
must generate a boundary and will set the complete header automatically when `-F` is used.

### 2.3 Authentication

There is currently no API key, login, bearer token, user role, or permission check. Every caller that
can reach the API can upload, query, inspect analytics, rebuild Qdrant, and delete documents.

### 2.4 Dates and IDs

- Document and query IDs are UUID-like strings.
- Dates are returned as ISO 8601 strings.
- Keep the `document_id` returned by ingestion if you may later delete that document.
- Keep the `query_id` returned by a query if you want its details or retrieval trace.
- In query responses, `trace_id` currently has the same value as `query_id`.

### 2.5 Error format

Most handled errors use this JSON shape:

```json
{
  "detail": "Human-readable error message"
}
```

FastAPI request validation errors use a more detailed `detail` array and normally return HTTP `422`.
Unexpected non-streaming failures return HTTP `500` with:

```json
{
  "detail": "Internal server error"
}
```

The generic `500` response intentionally does not expose an internal traceback. Inspect the API
terminal logs for the underlying exception.

### 2.6 Status-code overview

| Code | Meaning in this API |
| --- | --- |
| `200 OK` | The request completed, including a query that safely returned no answer |
| `201 Created` | The ingestion request completed |
| `204 No Content` | The document was deleted; the response body is empty |
| `400 Bad Request` | The upload failed safety or conversion checks |
| `404 Not Found` | A requested document or query ID does not exist |
| `422 Unprocessable Entity` | Request JSON, path, query parameter, or form data is invalid |
| `500 Internal Server Error` | An unexpected server-side error occurred |
| `503 Service Unavailable` | Ollama or the retrieval service is unavailable |

An HTTP `200` query response does not necessarily mean the system found an answer. Check the
`no_answer` and `confidence` fields.

## 3. Endpoint summary

| Method | Path | Purpose | Success code |
| --- | --- | --- | --- |
| `GET` | `/health` | Check API, SQLite, Qdrant, Ollama, and model status | `200` |
| `POST` | `/api/ingest` | Upload and index one document | `201` |
| `GET` | `/api/documents` | List registered documents | `200` |
| `DELETE` | `/api/documents/{document_id}` | Delete a document everywhere | `204` |
| `POST` | `/api/reindex` | Recreate the configured Qdrant collection from OKF | `200` |
| `POST` | `/api/query` | Ask a question and receive one JSON response | `200` |
| `POST` | `/api/query/stream` | Ask a question using server-sent events | `200` |
| `GET` | `/api/queries` | List recent query records | `200` |
| `GET` | `/api/queries/{query_id}` | Get one saved query and its cited source records | `200` |
| `GET` | `/api/trace/{query_id}` | Inspect the saved query plan and retrieval rounds | `200` |
| `GET` | `/api/analytics/questions` | Show common, typed, and low-confidence questions | `200` |
| `GET` | `/api/analytics/comparisons` | Show frequently compared entity pairs | `200` |
| `GET` | `/api/stats` | Show overall document and query statistics | `200` |

## 4. Health

### `GET /health`

Checks the API process and its important dependencies.

#### Request

No parameters and no body.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 8
```

```bash
curl http://127.0.0.1:8000/health
```

#### Example healthy response

```json
{
  "status": "ok",
  "components": {
    "api": {
      "status": "ok"
    },
    "sqlite": {
      "status": "ok"
    },
    "qdrant": {
      "status": "ok",
      "url": "http://localhost:6333"
    },
    "ollama": {
      "status": "ok",
      "url": "http://localhost:11434"
    },
    "llm_model": {
      "status": "ok",
      "model": "gemma4:e4b"
    },
    "embedding_model": {
      "status": "ok",
      "model": "embeddinggemma"
    }
  }
}
```

#### How to read it

- `api`: FastAPI is running.
- `sqlite`: the local analytics and registry database accepted a test query.
- `qdrant`: the vector service responded.
- `ollama`: the Ollama service responded.
- `llm_model`: the configured answer-generation model is installed.
- `embedding_model`: the configured embedding model is installed.
- top-level `status`: `ok` only when every reported component has status `ok`; otherwise `degraded`.

The route currently returns HTTP `200` even when the body says `"status": "degraded"`. Monitoring
scripts must inspect the JSON body and should not rely only on the HTTP code.

## 5. Document ingestion

### `POST /api/ingest`

Uploads one document, validates it, converts it to Markdown, creates an OKF representation, chunks
the text, calculates embeddings, stores searchable points in Qdrant, and registers the document in
SQLite.

#### Request

Content type: `multipart/form-data`

| Form field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `file` | File | Yes | The document to upload |

Default allowed extensions:

```text
.pdf, .docx, .pptx, .xlsx, .html, .htm, .txt, .md
```

The default maximum upload size is 50 MB. Both settings can be changed in `.env` using
`ALLOWED_EXTENSIONS` and `MAX_UPLOAD_MB`.

#### Swagger UI steps

1. Open `http://127.0.0.1:8000/docs`.
2. Expand `POST /api/ingest` under **ingestion**.
3. Select **Try it out**.
4. Select **Choose File**.
5. Choose the document.
6. Select **Execute**.

#### PowerShell with curl.exe

```powershell
curl.exe -sS -X POST `
  -F "file=@C:\docs\employee-handbook.pdf;type=application/pdf" `
  http://127.0.0.1:8000/api/ingest
```

For a text file:

```powershell
curl.exe -sS -X POST `
  -F "file=@C:\docs\notes.txt;type=text/plain" `
  http://127.0.0.1:8000/api/ingest
```

#### Bash or Linux/macOS curl

```bash
curl -sS -X POST \
  -F "file=@/home/user/docs/employee-handbook.pdf;type=application/pdf" \
  http://127.0.0.1:8000/api/ingest
```

#### Successful response: HTTP `201`

```json
{
  "document_id": "21199365-9225-4a34-8ae7-38cb04b25cb7",
  "filename": "employee-handbook.pdf",
  "sha256": "d31dab3e5bacf35038ac5f5998e3da8488e4010ab9c96233917f5bc4abe2aba2",
  "chunks": 143,
  "duplicate": false,
  "updated_document_id": null,
  "status": "ready"
}
```

#### Response fields

| Field | Meaning |
| --- | --- |
| `document_id` | New or existing document identifier |
| `filename` | Original filename received by the API |
| `sha256` | Checksum of the exact uploaded bytes |
| `chunks` | Number of searchable chunks registered for the document |
| `duplicate` | `true` when these exact bytes were already registered |
| `updated_document_id` | ID of the older same-filename document that was replaced, otherwise `null` |
| `status` | Current registry status; a successful ingestion uses `ready` |

#### Duplicate and update behaviour

If the exact same bytes are uploaded again, SHA-256 duplicate detection returns the existing document:

```json
{
  "document_id": "existing-document-id",
  "duplicate": true,
  "updated_document_id": null,
  "status": "ready"
}
```

It does not create another copy or another set of Qdrant points.

If a different file is uploaded with the same original filename, the new version is completely
converted and indexed first. Only after that succeeds does the application delete the previous
version. The response contains the removed version's ID in `updated_document_id`.

#### Upload validation

The API rejects:

- missing, blank, or path-containing filenames;
- unsupported extensions;
- empty files;
- files larger than `MAX_UPLOAD_MB`;
- `.pdf` files that do not begin with the PDF signature `%PDF-`;
- `.docx`, `.pptx`, or `.xlsx` files that are not ZIP-based Office files;
- text-like files containing binary null bytes near the beginning; and
- documents that MarkItDown cannot convert into non-empty text.

Example HTTP `400` response:

```json
{
  "detail": "File extension and PDF content do not match"
}
```

Another possible HTTP `400` response:

```json
{
  "detail": "Document conversion produced no text: scan.pdf"
}
```

The second message usually means the PDF is image-only or scanned and needs OCR before upload.

## 6. Document management

### 6.1 `GET /api/documents`

Lists all documents currently registered in SQLite.

#### Request

No parameters and no body.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/documents |
  ConvertTo-Json -Depth 8
```

```bash
curl http://127.0.0.1:8000/api/documents
```

#### Example response: HTTP `200`

```json
[
  {
    "document_id": "21199365-9225-4a34-8ae7-38cb04b25cb7",
    "filename": "employee-handbook.pdf",
    "sha256": "d31dab3e5bacf35038ac5f5998e3da8488e4010ab9c96233917f5bc4abe2aba2",
    "source_type": "pdf",
    "status": "ready",
    "chunk_count": 143,
    "metadata": {
      "title": "employee-handbook",
      "source_type": "pdf"
    },
    "created_at": "2026-08-30T11:07:58.000000",
    "updated_at": "2026-08-30T11:07:58.000000"
  }
]
```

An empty knowledge base returns:

```json
[]
```

This endpoint reports the SQLite registry. It does not prove that the corresponding Qdrant points or
OKF files still exist if somebody manually altered storage outside the API.

### 6.2 `DELETE /api/documents/{document_id}`

Deletes one document through the supported lifecycle operation.

It removes:

- the document's Qdrant points;
- its OKF document directory and OKF reference copy;
- its normalized Markdown file;
- its stored original source directory; and
- its SQLite document record.

Embedding cache files are intentionally retained because they are content-addressed and may be
shared or useful during a future rebuild.

#### Path parameter

| Parameter | Required | Meaning |
| --- | --- | --- |
| `document_id` | Yes | ID returned by ingestion or document listing |

#### PowerShell

```powershell
$documentId = "21199365-9225-4a34-8ae7-38cb04b25cb7"
Invoke-RestMethod -Method Delete `
  -Uri "http://127.0.0.1:8000/api/documents/$documentId"
```

#### curl

```bash
curl -i -X DELETE \
  http://127.0.0.1:8000/api/documents/21199365-9225-4a34-8ae7-38cb04b25cb7
```

#### Successful response: HTTP `204`

There is no JSON response body. This is expected.

#### Unknown ID: HTTP `404`

```json
{
  "detail": "Document not found: 21199365-9225-4a34-8ae7-38cb04b25cb7"
}
```

Do not manually delete only an OKF file when the intention is to remove a document. Manual OKF
deletion does not immediately remove existing Qdrant points. Use this endpoint instead.

## 7. Rebuilding the Qdrant index

### `POST /api/reindex`

Recreates the configured Qdrant collection from canonical OKF concepts.

#### Request

No parameters and no body.

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/reindex |
  ConvertTo-Json -Depth 4
```

```bash
curl -X POST http://127.0.0.1:8000/api/reindex
```

#### Example response: HTTP `200`

```json
{
  "concepts": 1,
  "chunks": 697
}
```

#### What this operation does

1. Discovers non-reserved Markdown concepts under `data/okf`.
2. Parses each concept and chunks its body again.
3. Detects the configured embedding dimension.
4. Deletes the configured Qdrant collection if it exists.
5. Creates a fresh collection and its payload indexes.
6. Reuses cached chunk embeddings where possible.
7. Calculates missing embeddings through Ollama.
8. Uploads all rebuilt dense and sparse points.
9. Updates each registered document's chunk count in SQLite.

It does not delete original uploads, OKF, query history, or analytics.

> Reindex is a powerful, unauthenticated, collection-replacing operation. Do not run it concurrently
> with active ingestion or depend on uninterrupted query availability while it is replacing the
> collection.

Use reindex when:

- Qdrant storage was lost but OKF remains;
- OKF was intentionally edited or removed;
- the chunking or sparse-index implementation changed;
- the embedding model changed; or
- Qdrant and the SQLite/OKF view appear inconsistent.

The equivalent CLI command is:

```powershell
.\.venv\Scripts\python.exe -m app.cli rebuild-index
```

## 8. Asking questions

### `POST /api/query`

Analyzes a question, retrieves evidence, reranks it, checks evidence sufficiency, optionally performs
a second retrieval round, generates a grounded answer, stores analytics, and returns JSON.

#### Request

Content type: `application/json`

```json
{
  "session_id": "my_first_test",
  "query": "What is a Default EPS Bearer Context Request?"
}
```

#### Request fields

| Field | Type | Rules | Meaning |
| --- | --- | --- | --- |
| `session_id` | String | 1–128 characters; letters, numbers, `-`, `_` only | Identifies conversation history |
| `query` | String | 1–10,000 characters | The user's question |

Use the same `session_id` for follow-up questions that should share conversation context. Use a new
ID for an unrelated conversation.

Valid session IDs:

```text
my_first_test
customer-42
demo2026
```

Invalid session IDs include spaces, `/`, `\`, `.`, `@`, and other punctuation.

#### PowerShell

```powershell
$body = @{
  session_id = "my_first_test"
  query = "What is a Default EPS Bearer Context Request?"
} | ConvertTo-Json

$response = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/query `
  -ContentType "application/json" `
  -Body $body

$response | ConvertTo-Json -Depth 12
```

#### curl

```bash
curl -sS -X POST http://127.0.0.1:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "my_first_test",
    "query": "What is a Default EPS Bearer Context Request?"
  }'
```

#### Example answered response: HTTP `200`

```json
{
  "query_id": "2e628168-e82a-4016-8199-8b1a86378a5b",
  "trace_id": "2e628168-e82a-4016-8199-8b1a86378a5b",
  "session_id": "my_first_test",
  "answer": "A Default EPS Bearer Context Request is a network message used during LTE bearer establishment [1].",
  "query_type": "factual",
  "standalone_query": "What is a Default EPS Bearer Context Request?",
  "comparison_targets": [],
  "confidence": 0.86,
  "no_answer": false,
  "retrieval_rounds": 1,
  "latency_ms": 2674.91,
  "sources": [
    {
      "chunk_id": "3a36a1cc-84a0-4d17-b2ed-2aa06982ee2e",
      "document_id": "21199365-9225-4a34-8ae7-38cb04b25cb7",
      "concept_id": "documents/lte-21199365/lte",
      "content": "The default EPS bearer context request ...",
      "title": "An Introduction to LTE",
      "heading": "Default EPS bearer activation",
      "heading_path": [
        "An Introduction to LTE",
        "Default EPS bearer activation"
      ],
      "source_file": "module-5-lte.pdf",
      "source_sha256": "d31dab3e5bacf35038ac5f5998e3da8488e4010ab9c96233917f5bc4abe2aba2",
      "okf_type": "Reference",
      "status": "draft",
      "trust_tier": "unverified",
      "stale_after": null,
      "is_stale": false,
      "score": 0.84,
      "channels": ["dense", "sparse"],
      "channel_scores": {
        "dense": 0.79,
        "sparse": 0.88
      },
      "citation": 1,
      "payload": {
        "chunk_id": "3a36a1cc-84a0-4d17-b2ed-2aa06982ee2e",
        "document_id": "21199365-9225-4a34-8ae7-38cb04b25cb7",
        "chunk_index": 42,
        "source_type": "pdf"
      }
    }
  ]
}
```

Values above are illustrative. IDs, text, scores, fields inside `payload`, and timings depend on the
indexed document and current models.

#### Top-level response fields

| Field | Meaning |
| --- | --- |
| `query_id` | Saved query identifier used by detail and trace endpoints |
| `trace_id` | Diagnostic identifier; currently equal to `query_id` |
| `session_id` | Conversation ID supplied by the caller |
| `answer` | Generated or deterministic grounded answer |
| `query_type` | Analyzer classification such as factual, locator, comparison, or summarization |
| `standalone_query` | Context-resolved version used for retrieval |
| `comparison_targets` | Entities detected for a comparison request |
| `confidence` | Evidence sufficiency confidence, normally interpreted from `0` to `1` |
| `no_answer` | `true` when available evidence was not sufficient |
| `retrieval_rounds` | Number of retrieval attempts performed |
| `latency_ms` | Complete server-side query time in milliseconds |
| `sources` | Evidence returned and numbered for citation |

The current `query_type` values are `factual`, `locator`, `definition`, `how_to`, `comparison`,
`summarization`, `multi_hop`, `analytical`, `synthesis`, `document_specific`, `follow_up`,
`exploratory`, and `no_retrieval`.

#### Source fields

| Field | Meaning |
| --- | --- |
| `chunk_id` | Unique searchable chunk ID |
| `document_id` | Owning uploaded document ID |
| `concept_id` | Owning OKF concept ID |
| `content` | Retrieved evidence text |
| `title` | Document or top-level title |
| `heading` | Nearest heading, if available |
| `heading_path` | Heading hierarchy leading to the chunk |
| `source_file` | Original uploaded filename |
| `source_sha256` | Original source checksum |
| `okf_type` | OKF type, normally `Reference` for automatic uploads |
| `status` | OKF status, normally `draft` for automatic uploads |
| `trust_tier` | `unverified`, `machine-confirmed`, or `human-reviewed` |
| `stale_after` | Optional freshness boundary from OKF metadata |
| `is_stale` | Whether the evidence is past that boundary |
| `score` | Internal combined relevance score; compare results within a query, not across systems |
| `channels` | Retrieval routes that found the chunk, such as `dense`, `sparse`, or `okf_graph` |
| `channel_scores` | Per-channel scores when available |
| `citation` | Citation number used in the answer |
| `payload` | Additional Qdrant payload retained for diagnostics |

#### Safe no-answer response

A no-answer outcome is still HTTP `200` because the API successfully processed the question:

```json
{
  "query_id": "2e628168-e82a-4016-8199-8b1a86378a5b",
  "trace_id": "2e628168-e82a-4016-8199-8b1a86378a5b",
  "session_id": "my_first_test",
  "answer": "I don't have enough supported information in the indexed knowledge base to answer that.",
  "query_type": "factual",
  "standalone_query": "What is a Default EPS Bearer Context Request?",
  "comparison_targets": [],
  "confidence": 0.1,
  "no_answer": true,
  "retrieval_rounds": 2,
  "latency_ms": 2674.91,
  "sources": []
}
```

When `no_answer` is `true`, the API intentionally returns an empty `sources` list rather than
presenting insufficient evidence as support.

#### Validation-error example: HTTP `422`

This request is invalid because the session ID contains spaces:

```json
{
  "session_id": "my test",
  "query": "What is LTE?"
}
```

The response contains a FastAPI/Pydantic validation description. Applications should treat any
`422` as a caller-side request problem.

#### Service-unavailable response: HTTP `503`

When Ollama or Qdrant cannot be reached, a normal query returns a handled service error such as:

```json
{
  "detail": "Retrieval service unavailable: connection refused"
}
```

## 9. Streaming answers with SSE

### `POST /api/query/stream`

Runs the same RAG pipeline but returns server-sent events instead of one JSON body.

#### Request

It uses the same JSON schema and validation rules as `/api/query`:

```json
{
  "session_id": "my_first_test",
  "query": "Summarize the LTE attach procedure."
}
```

#### PowerShell using curl.exe

Use `-N` to prevent response buffering:

```powershell
$body = '{"session_id":"my_first_test","query":"Summarize the LTE attach procedure."}'
curl.exe -N -X POST `
  -H "Content-Type: application/json" `
  --data-binary $body `
  http://127.0.0.1:8000/api/query/stream
```

#### Bash curl

```bash
curl -N -X POST http://127.0.0.1:8000/api/query/stream \
  -H "Content-Type: application/json" \
  -d '{"session_id":"my_first_test","query":"Summarize the LTE attach procedure."}'
```

#### Event sequence

The current implementation emits events in this order:

```text
query_analyzed
retrieving
generating
token          repeated once per space-separated answer word
sources
done
```

Example stream:

```text
event: query_analyzed
data: {"status": "started"}

event: retrieving
data: {"status": "started"}

event: generating
data: {"status": "complete"}

event: token
data: {"text": "The "}

event: token
data: {"text": "procedure "}

event: sources
data: {"sources": [...]}

event: done
data: {"query_id":"...","answer":"The procedure ...","sources":[...]}

```

#### Important streaming behaviour

This is not direct Ollama token streaming. The application completes query analysis, retrieval,
evidence checking, and answer generation before it emits the `generating` and `token` events. It then
splits the completed answer on spaces and sends those words as token events.

Therefore:

- the connection and early status events can confirm that work started;
- answer words are delivered through SSE;
- time-to-first-answer-word is still roughly the complete RAG execution time; and
- a client should use the `done` event as the authoritative complete response.

#### Streaming errors

Once streaming begins, an exception is sent as an SSE event:

```text
event: error
data: {"detail": "error message"}

```

The HTTP status may already be `200` because headers were sent before the failure. SSE clients must
handle the `error` event and must not rely only on the initial HTTP status.

## 10. Query history and diagnostics

### 10.1 `GET /api/queries`

Returns recent saved queries in newest-first order.

#### Query parameter

| Parameter | Default | Minimum | Maximum | Meaning |
| --- | ---: | ---: | ---: | --- |
| `limit` | `100` | `1` | `500` | Maximum records to return |

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/queries?limit=20" |
  ConvertTo-Json -Depth 8
```

#### Example response

```json
[
  {
    "id": "2e628168-e82a-4016-8199-8b1a86378a5b",
    "session_id": "my_first_test",
    "original_query": "What is LTE?",
    "normalized_query": "what is lte",
    "standalone_query": "What is LTE?",
    "query_type": "factual",
    "answer": "LTE is ... [1].",
    "answer_confidence": 0.88,
    "no_answer": false,
    "latency_ms": 2140.3,
    "created_at": "2026-08-30T11:39:19.000000",
    "entities": ["LTE"],
    "comparison_targets": [],
    "comparison_dimensions": [],
    "subquestions": []
  }
]
```

There is currently no offset, cursor, date filter, session filter, or deletion endpoint for query
history.

### 10.2 `GET /api/queries/{query_id}`

Returns one saved query and the compact citation records stored for it.

```powershell
$queryId = "2e628168-e82a-4016-8199-8b1a86378a5b"
Invoke-RestMethod "http://127.0.0.1:8000/api/queries/$queryId" |
  ConvertTo-Json -Depth 10
```

#### Example response

```json
{
  "id": "2e628168-e82a-4016-8199-8b1a86378a5b",
  "session_id": "my_first_test",
  "original_query": "What is LTE?",
  "normalized_query": "what is lte",
  "standalone_query": "What is LTE?",
  "query_type": "factual",
  "answer": "LTE is ... [1].",
  "answer_confidence": 0.88,
  "no_answer": false,
  "latency_ms": 2140.3,
  "created_at": "2026-08-30T11:39:19.000000",
  "entities": ["LTE"],
  "comparison_targets": [],
  "comparison_dimensions": [],
  "subquestions": [],
  "sources": [
    {
      "id": "citation-record-id",
      "query_id": "2e628168-e82a-4016-8199-8b1a86378a5b",
      "chunk_id": "chunk-id",
      "document_id": "document-id",
      "citation_number": 1,
      "score": 0.84
    }
  ]
}
```

Unlike the immediate `/api/query` response, this endpoint's saved `sources` are compact database
records. They do not contain the complete chunk text or heading metadata.

Unknown query IDs return HTTP `404`:

```json
{
  "detail": "Query not found"
}
```

### 10.3 `GET /api/trace/{query_id}`

Returns the saved analysis plan, retrieval plan, and retrieval-run metrics for one query.

```powershell
$queryId = "2e628168-e82a-4016-8199-8b1a86378a5b"
Invoke-RestMethod "http://127.0.0.1:8000/api/trace/$queryId" |
  ConvertTo-Json -Depth 15
```

#### Example response

```json
{
  "query_id": "2e628168-e82a-4016-8199-8b1a86378a5b",
  "query_type": "factual",
  "standalone_query": "What is LTE?",
  "plan": {
    "query_analysis": {
      "original_query": "What is LTE?",
      "standalone_query": "What is LTE?",
      "query_type": "factual",
      "entities": ["LTE"],
      "comparison_targets": [],
      "comparison_dimensions": [],
      "exact_terms": ["LTE"],
      "temporal_constraints": null,
      "document_filters": [],
      "subquestions": [],
      "requires_decomposition": false,
      "requires_conversation_context": false,
      "retrieval_strategy": "standard"
    },
    "retrieval_plan": {
      "strategy": "standard",
      "queries": ["What is LTE?"],
      "entity_queries": {},
      "metadata_filters": {},
      "use_dense": true,
      "use_sparse": true,
      "expand_okf_links": true,
      "rerank": false
    }
  },
  "retrieval_rounds": [
    {
      "id": "retrieval-run-id",
      "query_id": "2e628168-e82a-4016-8199-8b1a86378a5b",
      "round_number": 1,
      "subquery": "What is LTE?",
      "strategy": "standard",
      "dense_candidates": 20,
      "sparse_candidates": 20,
      "fused_candidates": 15,
      "duration_ms": 112.5,
      "created_at": "2026-08-30T11:39:19.000000"
    }
  ],
  "latency_ms": 2140.3
}
```

The trace exposes structured planning and retrieval measurements. It does not expose hidden
chain-of-thought or private model reasoning.

Unknown query IDs return HTTP `404` with `{"detail":"Query not found"}`.

## 11. Analytics and statistics

### 11.1 `GET /api/analytics/questions`

Summarizes repeated questions, query types, low-confidence responses, and the total number of safe
no-answer outcomes.

#### Query parameter

| Parameter | Default | Minimum | Maximum |
| --- | ---: | ---: | ---: |
| `limit` | `20` | `1` | `100` |

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/analytics/questions?limit=20" |
  ConvertTo-Json -Depth 10
```

#### Example response

```json
{
  "most_common": [
    {
      "question": "what is lte",
      "count": 4
    }
  ],
  "by_type": {
    "factual": 8,
    "comparison": 2,
    "summarization": 1
  },
  "low_confidence": [
    {
      "id": "query-id",
      "session_id": "demo",
      "original_query": "An unsupported question",
      "normalized_query": "an unsupported question",
      "standalone_query": "An unsupported question",
      "query_type": "factual",
      "answer": "I don't have enough supported information ...",
      "answer_confidence": 0.1,
      "no_answer": true,
      "latency_ms": 1800.0,
      "created_at": "2026-08-30T11:39:19.000000",
      "entities": [],
      "comparison_targets": [],
      "comparison_dimensions": [],
      "subquestions": []
    }
  ],
  "no_answer_count": 1
}
```

`most_common.question` is normalized rather than necessarily preserving the user's exact
capitalization and punctuation.

### 11.2 `GET /api/analytics/comparisons`

Returns entity pairs discovered in comparison questions, ordered by how often they were asked about.

#### Query parameter

| Parameter | Default | Minimum | Maximum |
| --- | ---: | ---: | ---: |
| `limit` | `20` | `1` | `100` |

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/api/analytics/comparisons?limit=20" |
  ConvertTo-Json -Depth 8
```

#### Example response

```json
[
  {
    "id": "comparison-edge-id",
    "entity_a": "4G",
    "entity_b": "5G",
    "entity_a_key": "4g",
    "entity_b_key": "5g",
    "count": 3,
    "last_asked": "2026-08-30T11:39:19.000000"
  }
]
```

An empty comparison history returns `[]`.

### 11.3 `GET /api/stats`

Returns overall document, chunk, query, and latency statistics.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/stats |
  ConvertTo-Json -Depth 8
```

#### Example response

```json
{
  "documents_indexed": 1,
  "chunks_indexed": 697,
  "total_questions": 11,
  "comparison_queries": 2,
  "no_answer_count": 1,
  "average_query_latency_ms": 2451.32,
  "average_retrieval_latency_ms": 124.87,
  "queries_by_type": {
    "factual": 7,
    "locator": 1,
    "comparison": 2,
    "summarization": 1
  }
}
```

`documents_indexed` and `chunks_indexed` come from SQLite's document registry. They are operational
metadata and are not a live count of Qdrant points.

## 12. Common errors

### API is not reachable

Example:

```text
Failed to connect to 127.0.0.1 port 8000
```

Cause: Uvicorn is not running, stopped with an error, or is listening on another host/port.

Check the terminal where Uvicorn was started and run:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

### HTTP `400`: file extension and PDF content do not match

The filename ends in `.pdf`, but the uploaded bytes do not begin with the PDF signature. Renaming a
non-PDF file to `.pdf` does not convert it. Open the file in a PDF reader and export or print it as a
real PDF, or upload it using its real supported format.

### HTTP `400`: document conversion produced no text

The converter found no usable text. The usual causes are:

- an image-only scanned PDF;
- a protected or encrypted PDF;
- a corrupted file; or
- a document format that the converter cannot interpret.

Run OCR on scanned PDFs, remove encryption if authorized, and try a clean exported copy.

### HTTP `422`: validation error

The request shape is wrong. Common causes include:

- missing `file` in an ingestion form;
- missing `session_id` or `query`;
- an empty question;
- a session ID containing spaces or punctuation;
- a non-integer `limit`; or
- a limit outside the endpoint's permitted range.

### HTTP `503`: Ollama or retrieval unavailable

Check:

```powershell
ollama list
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 8
```

Confirm that the configured models in `.env` are installed and that Qdrant is healthy.

### Query is HTTP `200` but says it cannot answer

That is not an HTTP failure. It means `no_answer` is `true` because the evidence checker did not find
enough support. Check:

1. `GET /api/documents` to verify a document is registered.
2. `GET /api/stats` to verify registered chunk counts are non-zero.
3. `GET /api/trace/{query_id}` to inspect retrieval rounds.
4. Whether the answer really exists as extractable text in the uploaded document.
5. Whether Qdrant needs to be rebuilt from OKF using `POST /api/reindex`.

### Deleted OKF manually but Qdrant still answers from it

Manual filesystem deletion does not synchronize Qdrant. If the OKF deletion was intentional, run:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/reindex
```

For ordinary document removal, use `DELETE /api/documents/{document_id}` instead.

### Swagger shows “Undocumented” for an error

FastAPI can return handled runtime errors that were not separately declared in the route's OpenAPI
response table. The actual HTTP code and `detail` body are still meaningful. This document lists the
runtime errors implemented by the current code.

## 13. Complete workflows

### 13.1 First upload and question

```powershell
# 1. Check all services.
Invoke-RestMethod http://127.0.0.1:8000/health |
  ConvertTo-Json -Depth 8

# 2. Upload a document. Do not manually set multipart Content-Type.
curl.exe -sS -X POST `
  -F "file=@C:\docs\lte.pdf;type=application/pdf" `
  http://127.0.0.1:8000/api/ingest

# 3. Verify registration.
Invoke-RestMethod http://127.0.0.1:8000/api/documents |
  ConvertTo-Json -Depth 8

# 4. Ask a question.
$body = @{
  session_id = "lte_demo"
  query = "What is a Default EPS Bearer Context Request?"
} | ConvertTo-Json

$answer = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/query `
  -ContentType "application/json" `
  -Body $body

$answer | ConvertTo-Json -Depth 12

# 5. Inspect the trace using the returned ID.
Invoke-RestMethod "http://127.0.0.1:8000/api/trace/$($answer.query_id)" |
  ConvertTo-Json -Depth 15
```

### 13.2 Conversation follow-up

Use the same session ID:

```powershell
$first = @{
  session_id = "lte_conversation"
  query = "Explain the LTE attach procedure."
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/query `
  -ContentType "application/json" -Body $first

$followUp = @{
  session_id = "lte_conversation"
  query = "What happens immediately after that?"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/query `
  -ContentType "application/json" -Body $followUp |
  ConvertTo-Json -Depth 12
```

The analyzer receives up to the eight most recent messages from that session.

### 13.3 Properly delete a document

```powershell
$documents = Invoke-RestMethod http://127.0.0.1:8000/api/documents
$documents | Format-Table document_id, filename, status, chunk_count

$documentId = $documents[0].document_id
Invoke-RestMethod -Method Delete `
  -Uri "http://127.0.0.1:8000/api/documents/$documentId"

Invoke-RestMethod http://127.0.0.1:8000/api/documents |
  ConvertTo-Json -Depth 8
```

Review the selected ID before issuing the delete request. Deletion is not exposed as an undoable or
trash-based operation.

## 14. Calling the API from Python

The project already depends on `httpx`, so these examples work inside its virtual environment.

### 14.1 Health

```python
import httpx

base_url = "http://127.0.0.1:8000"

response = httpx.get(f"{base_url}/health", timeout=30)
response.raise_for_status()
print(response.json())
```

### 14.2 Upload

```python
from pathlib import Path

import httpx

base_url = "http://127.0.0.1:8000"
path = Path(r"C:\docs\lte.pdf")

with path.open("rb") as document:
    response = httpx.post(
        f"{base_url}/api/ingest",
        files={"file": (path.name, document, "application/pdf")},
        timeout=600,
    )

response.raise_for_status()
result = response.json()
print(result)
document_id = result["document_id"]
```

Use a generous timeout because conversion and embedding generation can take time, especially on the
first upload.

### 14.3 Query

```python
import httpx

base_url = "http://127.0.0.1:8000"

response = httpx.post(
    f"{base_url}/api/query",
    json={
        "session_id": "python_demo",
        "query": "What is a Default EPS Bearer Context Request?",
    },
    timeout=300,
)
response.raise_for_status()

result = response.json()
print("Answer:", result["answer"])
print("Confidence:", result["confidence"])
print("No answer:", result["no_answer"])
for source in result["sources"]:
    print(source["citation"], source["source_file"], source["heading"])
```

### 14.4 Delete

```python
import httpx

base_url = "http://127.0.0.1:8000"
document_id = "21199365-9225-4a34-8ae7-38cb04b25cb7"

response = httpx.delete(
    f"{base_url}/api/documents/{document_id}",
    timeout=120,
)
response.raise_for_status()
assert response.status_code == 204
```

### 14.5 Basic SSE consumption

```python
import httpx

base_url = "http://127.0.0.1:8000"

with httpx.stream(
    "POST",
    f"{base_url}/api/query/stream",
    json={
        "session_id": "python_stream_demo",
        "query": "Summarize the LTE attach procedure.",
    },
    timeout=300,
) as response:
    response.raise_for_status()
    for line in response.iter_lines():
        if line:
            print(line)
```

A production SSE client should parse `event:` and `data:` lines, combine events until the blank line,
decode each `data` value as JSON, handle the `error` event, and stop after `done`.

## 15. Operational and security notes

### 15.1 Local persistence

API restarts and computer restarts do not normally require re-uploading documents. Data persists in:

- `data/sources` for stored uploads;
- `data/markdown` for normalized conversion output;
- `data/okf` for canonical knowledge and provenance;
- `data/cache` for reusable calculations;
- `data/database/smart_rag.db` for registry, conversations, traces, and analytics; and
- the Docker Qdrant named volume for the active search index.

`docker compose down` keeps the named volume. `docker compose down -v` deletes it.

### 15.2 Timeouts

Ingestion and queries can take longer on the first use because Ollama may need to load a model and the
application may need to calculate uncached embeddings. Client timeouts should be much larger than a
typical web request timeout.

### 15.3 Concurrency

The current project is designed primarily for local use. Avoid concurrent reindex and ingestion
operations. A reindex deletes and recreates the configured Qdrant collection.

### 15.4 CORS

The application currently does not install CORS middleware. Swagger works because it is served from
the same FastAPI origin. A browser frontend hosted on another origin may be blocked by browser CORS
rules until explicit allowed origins are configured.

### 15.5 Sensitive data

Uploaded content, converted text, OKF, query text, answers, session messages, traces, and analytics are
stored locally. Local-first does not mean access-controlled. Protect the computer, project directory,
SQLite file, Docker volume, backups, and API port according to the sensitivity of the documents.

### 15.6 Destructive operations

- `DELETE /api/documents/{document_id}` permanently removes the document's managed artifacts and
  Qdrant points.
- `POST /api/reindex` replaces the configured Qdrant collection from whatever OKF exists at that
  moment.
- Neither endpoint currently requires confirmation or authentication.

## 16. Current API limitations

The current implementation does not provide:

- authentication or per-user authorization;
- API keys or bearer tokens;
- rate limiting or quotas;
- CORS configuration for a separate browser frontend;
- an endpoint to download original documents;
- an endpoint to retrieve one full document by ID;
- an endpoint to edit OKF metadata;
- a feedback submission endpoint, although feedback-ready schema/database structures exist;
- query-history deletion or session-history management endpoints;
- pagination beyond a simple `limit` on list endpoints;
- live Qdrant point counts in `/api/stats`;
- OCR for image-only PDFs;
- automatic synchronization when somebody manually edits or deletes OKF files;
- background job IDs or progress reporting for ingestion and reindex;
- direct model-token streaming; or
- a public stability/versioning guarantee beyond the current application version `0.1.0`.

These are implementation facts, not Swagger usage errors.

## 17. Implementation map

The API documentation above is based on these source files:

| Concern | Source file |
| --- | --- |
| FastAPI creation and global error handling | `app/main.py` |
| Request validation schemas | `app/api/schemas.py` |
| Health route | `app/api/health.py` |
| Ingestion and reindex routes | `app/api/ingest.py` |
| Document list and delete routes | `app/api/documents.py` |
| Query, stream, query detail, and trace routes | `app/api/query.py` |
| Analytics and stats routes | `app/api/analytics.py` |
| Document ingestion lifecycle | `app/ingestion/pipeline.py` |
| File validation | `app/ingestion/security.py` |
| Query response model | `app/rag/state.py` |
| Source/evidence response model | `app/retrieval/models.py` |
| Saved query and analytics response construction | `app/database/repository.py` |
| Environment defaults and limits | `app/config.py` |

When route code and this document ever disagree, route code is the current runtime authority. Swagger
at `/docs` and the OpenAPI document at `/openapi.json` are the quickest way to confirm request
validation, while this guide explains runtime behaviour and operational meaning that the generated
schema does not capture.
