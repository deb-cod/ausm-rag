# AUSM Smart RAG: A Plain-English Guide

This guide explains the whole project for someone who does not need to know AI, Python, Docker,
databases, or APIs. It covers what the system does, what its parts are for, how to install it on a
new Windows computer, and how to upload documents and ask questions.

For deeper technical details and diagrams, see [architecture.md](architecture.md). For the shorter
developer reference, see [README.md](README.md).

## 1. What this project does

AUSM Smart RAG is a private document question-answering application.

You give it documents such as PDFs or Word files. It reads and organizes those documents. You can
then ask questions in normal language, and it searches the documents before writing an answer.

For example, you can upload an employee handbook and ask:

> How many days of annual leave does an employee receive?

The system finds the relevant part of the handbook, answers from that part, and returns the source
text it used. If the answer is not supported by the uploaded documents, the system is designed to
say that it does not have enough evidence instead of confidently inventing an answer.

The project runs on your computer. During normal use, it does not need to send documents to a
hosted AI provider. An internet connection is still needed during the first installation to
download software, Python packages, the Qdrant Docker image, and the Ollama models.

## 2. What “RAG” means

RAG stands for **retrieval-augmented generation**. The name sounds complicated, but the idea is
simple:

1. **Retrieval:** find the most relevant passages in your documents.
2. **Augmented:** give those passages to the AI as evidence.
3. **Generation:** write a readable answer based on that evidence.

This is different from asking a normal chatbot to answer from memory. The application first looks
inside your uploaded material and then answers.

Uploading a document does **not** retrain the AI model. It creates a searchable index of the
document so the right passages can be found quickly.

## 3. The main parts, explained with a library example

Imagine the application as a small private library:

- **FastAPI is the front desk.** It receives uploaded files and questions. The browser page at
  `http://127.0.0.1:8000/docs` is a simple way to use this front desk.
- **MarkItDown is the document reader.** Different file types have different internal formats.
  MarkItDown turns their readable content into one consistent Markdown text format.
- **OKF is the organized master copy.** The Open Knowledge Format stores cleaned knowledge,
  headings, links, origin information, and other details in files that people can inspect.
- **The chunker makes index cards.** A long document is divided into smaller, overlapping passages.
  These are called chunks. Smaller passages are easier to search accurately.
- **EmbeddingGemma creates meaning-based labels.** It turns each passage into numbers that
  represent its meaning. This lets the system match questions such as “holiday allowance” with a
  passage that says “annual leave,” even though the exact words differ.
- **The keyword search creates word-based labels.** It is useful for exact names, error codes,
  policy numbers, product codes, and other exact wording.
- **Qdrant is the fast card catalogue.** It stores both kinds of search labels and quickly returns
  the most relevant passages.
- **Gemma is the librarian and answer writer.** It helps understand the question and turns the
  retrieved evidence into a clear answer.
- **SQLite is the activity notebook.** It records uploaded-document details, conversations,
  questions, retrieval activity, sources, and useful statistics. It does not store the vector
  search index.
- **Docker is a ready-made container for Qdrant.** It runs Qdrant in a predictable environment
  without requiring a manual database installation.
- **`.venv` is this project's private Python toolbox.** It keeps the required Python packages
  separate from packages used by other projects on the computer.

## 4. What happens when you upload a document

The following work happens automatically:

1. The application checks the filename, file type, and size.
2. It rejects unsupported, suspicious, or excessively large files.
3. It calculates a fingerprint called a SHA-256 checksum. This identifies identical files.
4. It saves the accepted original file under `data/sources`.
5. MarkItDown extracts readable content and saves normalized Markdown under `data/markdown`.
6. The system builds its organized OKF knowledge copy under `data/okf`.
7. It divides the content into searchable passages while trying to preserve headings and context.
8. Ollama's embedding model creates meaning-based search representations.
9. The application also creates exact-word search representations.
10. Qdrant stores the searchable index.
11. SQLite records the document ID, filename, checksum, status, and number of passages.

If exactly the same file is uploaded again, the application recognizes the matching checksum and
returns the existing document instead of creating duplicate search entries.

If a changed file is uploaded with the same filename, the application treats it as an updated
version and replaces the old document's searchable information.

The default maximum file size is 50 MB. The default supported extensions are:

- PDF: `.pdf`
- Microsoft Word: `.docx`
- Microsoft PowerPoint: `.pptx`
- Microsoft Excel: `.xlsx`
- Web pages: `.html` and `.htm`
- Plain text: `.txt`
- Markdown: `.md`

Encrypted, damaged, incorrectly named, or unsupported files may not be readable.

## 5. What happens when you ask a question

The system follows these steps:

1. It reads your question and decides what kind of question it is.
2. If it is a follow-up, it uses recent messages from the same `session_id` to understand what
   words such as “it,” “that,” or “the second option” refer to.
3. It may divide a difficult question into several smaller searches.
4. It performs a meaning-based search and an exact-word search. The exact search also uses small
   character pieces, so it can still match words that a PDF reader accidentally glued together.
5. It combines the two result lists so both meaning and precise wording matter.
6. For comparison questions, it deliberately gathers evidence for each item being compared.
7. It can follow useful links between related OKF concepts.
8. It ranks the best passages, considering relevance, direct phrase matches, trust information, and
   freshness. A passage that closely repeats the question is preferred over broad background text.
9. It checks whether the evidence is strong enough and covers the whole question.
10. If needed, it makes one bounded retry with a refined search.
11. For a simple fact, the application gives Gemma only a few short excerpts centered on the query.
    Certain quoted sentence fragments can be answered directly from their matching sentence. More
    complex questions still use Gemma to write the supported answer.
12. The answer, supporting sources, timing, and retrieval trace are recorded in SQLite.

The system is “agentic” because it can adapt its search plan, not because it has unlimited control
of the computer. It cannot silently browse the web or treat instructions inside an uploaded
document as commands.

## 6. Where your information is stored

All important project data is under the local `data` directory:

```text
data/
  sources/    original accepted files
  markdown/   readable text produced from those files
  okf/        organized master knowledge files
  cache/      reusable results that make repeated work faster
  database/   the SQLite activity and document database
```

Qdrant's search index is stored in a Docker volume. Think of that index as a replaceable card
catalogue. The OKF files are the master knowledge copy. If the Qdrant catalogue is lost, it can be
rebuilt from OKF.

## 7. First-time setup on a new Windows computer

You only need to complete this whole section once per computer.

### Step 1: check the computer

The recommended starting point is:

- Windows 10 or Windows 11, 64-bit
- at least 16 GB of memory
- about 15 GB of free disk space
- virtualization/WSL 2 available for Docker Desktop
- an internet connection during installation

The main generation model is a large download, so the first setup can take time.

### Step 2: install the four required programs

Install:

1. **Git**, which downloads the project source code.
2. **Python 3.12**, which runs the application.
3. **Docker Desktop**, which runs the Qdrant search database.
4. **Ollama**, which runs the AI and embedding models locally.

They can be installed from their normal download pages, or from PowerShell with:

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id Docker.DockerDesktop -e
winget install --id Ollama.Ollama -e
```

After installing them, restart the computer or at least close and reopen PowerShell. This allows
Windows to recognize the newly installed commands.

### Step 3: start Docker Desktop and Ollama

Open Docker Desktop from the Start menu. Wait until it says that the Docker engine is running.

Open Ollama if it is not already running in the notification area. Ollama normally runs quietly in
the background.

### Step 4: download the project

Open PowerShell and choose the folder where you want the project. For example:

```powershell
Set-Location C:\Projects
git clone https://github.com/deb-cod/ausm-rag.git
Set-Location .\ausm-rag
```

If `C:\Projects` does not exist, create it first:

```powershell
New-Item -ItemType Directory -Path C:\Projects
Set-Location C:\Projects
```

`git clone` means “download a working copy of this project.” You only clone it once.

### Step 5: let the setup script prepare everything

From inside the `ausm-rag` folder, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

The script does the following for you:

- creates the `.venv` private Python environment;
- installs the required Python packages;
- creates `.env` from the supplied example configuration;
- downloads `gemma4:e4b` if it is missing;
- downloads `embeddinggemma` if it is missing;
- starts Qdrant in Docker; and
- waits until Qdrant is ready.

The model download is large. A long pause or download progress during the first run is normal. Do
not close the window unless an error is shown.

The setup script is safe to run again. It keeps the existing `.env` and `.venv`, avoids downloading
models that are already installed, and starts the existing Qdrant service.

### Step 6: run the automatic checkup

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\doctor.ps1 -RunTests
```

This is like a health check for the installation. It checks Python, the required packages, Ollama,
both models, Docker, Qdrant, code quality, and automated tests.

The ideal result is that every line starts with `[OK]` and the end says:

```text
All checks passed.
```

If something says `[FAIL]`, look for that item in the troubleshooting section below.

### Step 7: start the application

Run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Keep this PowerShell window open. It is the running application. A line similar to the following
means the application is listening:

```text
Uvicorn running on http://127.0.0.1:8000
```

Open these addresses in a browser:

- Interactive testing page: `http://127.0.0.1:8000/docs`
- Application health: `http://127.0.0.1:8000/health`
- Qdrant dashboard: `http://127.0.0.1:6333/dashboard`

`127.0.0.1` and `localhost` both mean “this computer.” These pages are not public internet pages.

## 8. Confirm that the application is ready

Open `http://127.0.0.1:8000/docs` in a browser.

1. Find **GET /health**.
2. Click the row to open it.
3. Click **Try it out**.
4. Click **Execute**.

The response code should be `200`. The response should show a top-level status of `ok`, with `ok`
for the API, SQLite, Qdrant, Ollama, generation model, and embedding model.

If the top-level status is `degraded`, the component list tells you what is missing or unavailable.
Fix that component before uploading documents.

## 9. Upload your first document using the browser

The browser testing page is the easiest method for a beginner:

1. Open `http://127.0.0.1:8000/docs`.
2. Find **POST /api/ingest**.
3. Click the row to open it.
4. Click **Try it out**.
5. Click **Choose File**.
6. Select a supported file from your computer.
7. Click **Execute** once.
8. Wait for the response. Large documents can take longer.

A successful upload returns response code `201` and information similar to:

```json
{
  "document_id": "bdca2181-7318-42c0-9d4f-af652824d2ad",
  "filename": "employee-handbook.pdf",
  "sha256": "a-long-file-fingerprint",
  "chunks": 14,
  "duplicate": false,
  "updated_document_id": null,
  "status": "ready"
}
```

In simple terms:

- `document_id` is the application's unique name for this document.
- `filename` is the original file name.
- `sha256` is the fingerprint used to recognize identical files.
- `chunks` is the number of searchable passages created.
- `duplicate: false` means this was a new file.
- `status: ready` means you can ask questions about it.

If `duplicate` is `true`, the same file was already present. This is not an error.

To confirm that the document is registered:

1. Open **GET /api/documents** on the same page.
2. Click **Try it out**.
3. Click **Execute**.

Your filename should appear in the response.

## 10. Ask your first question

On `http://127.0.0.1:8000/docs`:

1. Find **POST /api/query**.
2. Click the row to open it.
3. Click **Try it out**.
4. Replace the example request body with the JSON below.
5. Click **Execute**.

```json
{
  "session_id": "my_first_test",
  "query": "What are the main points in the document?"
}
```

The first question after starting Ollama can take longer because the model may be loading into
memory.

`session_id` is simply the name of the conversation. You choose it. It can contain letters,
numbers, hyphens, and underscores, but not spaces. Use the same session ID for related follow-up
questions.

For a stronger test, ask about a fact you know is present:

```json
{
  "session_id": "handbook_test",
  "query": "How many days of annual leave does the handbook provide?"
}
```

## 11. How to understand the answer

The response contains several fields:

- `answer` is the plain-language answer.
- `sources` contains the exact document passages used as evidence.
- `query_id` uniquely identifies this question and lets you inspect its trace later.
- `query_type` describes the detected kind of question, such as factual or comparison.
- `standalone_query` is the complete version of a follow-up question after conversation context is
  added.
- `comparison_targets` lists the things being compared, when applicable.
- `confidence` is the system's evidence confidence.
- `no_answer` is `true` when the documents do not provide enough support.
- `retrieval_rounds` shows how many search attempts were needed.
- `latency_ms` shows the total processing time in milliseconds.

Each item under `sources` includes details such as the source filename, heading, retrieved passage,
relevance score, and citation number. Use these passages to verify that the answer really came from
the uploaded material.

The answer may contain markers such as `[1]`. Marker `[1]` refers to the source whose `citation`
value is `1`.

## 12. Useful tests to prove that it works

### Test a known fact

Ask a question whose answer you can visibly find in the document. Confirm that the answer and
source passage agree with the file.

### Test exact wording

Ask about an exact code, policy number, person, or product name. This tests the keyword-search side.

```json
{
  "session_id": "exact_word_test",
  "query": "What does policy HR-104 say?"
}
```

You can also ask where a named topic appears:

```json
{
  "session_id": "exact_word_test",
  "query": "Third Generation Systems is in which section?"
}
```

For this kind of question, the application looks for an exact numbered heading and returns a short
answer such as `section 1.2.2 [1]`. It also recognizes PDF text where heading words were accidentally
joined together, such as `ThirdGenerationSystems`.

### Test similar meaning

Use different words from the document. For example, ask about “holiday allowance” when the
document says “annual leave.” This tests meaning-based search.

### Test a follow-up conversation

First ask:

```json
{
  "session_id": "leave_chat",
  "query": "What is the annual leave policy?"
}
```

Then use the same `session_id`:

```json
{
  "session_id": "leave_chat",
  "query": "Does it apply during probation?"
}
```

The system should understand what “it” refers to because both questions share a session.

### Test a comparison

Upload documents that describe two products, policies, or systems, then ask:

```json
{
  "session_id": "comparison_test",
  "query": "Compare the leave rules in the Employee Handbook and Contractor Handbook."
}
```

The application tries to collect evidence for both sides instead of letting the better-documented
side dominate the answer.

### Test that it refuses to guess

Ask something clearly absent from your documents:

```json
{
  "session_id": "no_answer_test",
  "query": "What is the company policy for working from the Moon?"
}
```

A safe result should have `no_answer: true`, or clearly explain that the documents do not contain
enough evidence. This is a successful safety test, not a failure.

## 13. See how an answer was found

Copy the `query_id` from a query response.

On the browser testing page:

1. Open **GET /api/trace/{query_id}**.
2. Click **Try it out**.
3. Paste the ID into the `query_id` box.
4. Click **Execute**.

The trace shows the searches performed, retrieval rounds, number of candidates, selected results,
and timings. It is useful when an answer is weak or unexpected.

Other useful read-only endpoints are:

- **GET /api/queries**: recent questions.
- **GET /api/queries/{query_id}**: full information about one question.
- **GET /api/stats**: document, chunk, question, comparison, and timing totals.
- **GET /api/analytics/questions**: commonly asked questions.
- **GET /api/analytics/comparisons**: commonly compared pairs.

## 14. Delete a document

First use **GET /api/documents** and copy the document's `document_id`.

Then:

1. Open **DELETE /api/documents/{document_id}**.
2. Click **Try it out**.
3. Paste the ID into the `document_id` field.
4. Click **Execute**.

Response code `204` with an empty response body means deletion succeeded. The application removes
the registered document, original source copy, Markdown, OKF files, and Qdrant search entries for
that document.

Deletion is permanent unless you still have the original file or a backup. Be careful to use the
correct document ID.

## 15. Everyday use after the first installation

You do not need to run the full setup every day.

Each time you want to use the project:

1. Start Docker Desktop and wait for its engine to run.
2. Make sure Ollama is running.
3. Open PowerShell in the project folder.
4. Start Qdrant if necessary:

   ```powershell
   docker compose up -d
   ```

5. Start the application:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
   ```

6. Keep that PowerShell window open.
7. Open `http://127.0.0.1:8000/docs`.

Your previously uploaded documents remain available because the data directories and Docker volume
are persistent.

## 16. How to stop the application safely

In the PowerShell window running Uvicorn, press `Ctrl+C`. That stops the API but does not delete
documents.

You may leave Qdrant running. To stop its Docker container without deleting its data, run:

```powershell
docker compose down
```

Do **not** add `-v` unless you intentionally want to delete the Qdrant storage volume:

```text
docker compose down -v    Dangerous for stored index data
```

Even though the index can be rebuilt from OKF, deleting data unnecessarily creates avoidable work.

## 17. Optional PowerShell method for upload and questions

The browser page is easiest, but the same operations can be automated from PowerShell.

Upload a PDF:

```powershell
$DocumentPath = 'C:\docs\employee-handbook.pdf'
$UploadJson = curl.exe -sS -X POST `
  -F "file=@$DocumentPath;type=application/pdf" `
  http://127.0.0.1:8000/api/ingest
$UploadJson
```

Ask a question:

```powershell
$Body = @{
  session_id = 'my_first_test'
  query = 'What are the main points in the document?'
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/query `
  -ContentType 'application/json' `
  -Body $Body | ConvertTo-Json -Depth 8
```

List uploaded documents:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/documents | ConvertTo-Json -Depth 6
```

## 18. Configuration without programming

The `.env` file in the project root contains the main settings. The setup script creates it from
`.env.example`.

Examples include:

- the Ollama and Qdrant addresses;
- model names;
- maximum upload size;
- accepted extensions;
- how many search candidates to consider;
- how many retrieval retries are allowed; and
- the minimum acceptable evidence score.

Most users should keep the defaults. If you edit `.env`, stop and restart Uvicorn so the
application loads the new settings.

Changing the embedding model may change the length of its numeric representations. If that occurs,
rebuild the search index after changing the model:

```powershell
.\.venv\Scripts\python.exe -m app.cli rebuild-index
```

## 19. Updating the project later

Stop the running API, open PowerShell in the project folder, and run:

```powershell
git pull
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
docker compose pull
docker compose up -d
.\scripts\doctor.ps1
```

`git pull` downloads newer project code. Reinstalling the Python package applies dependency
changes. The Docker commands update and restart Qdrant. The doctor verifies the result.

## 20. Backing up your knowledge

Back up the entire `data` folder, especially:

- `data/sources`, which contains accepted originals;
- `data/okf`, which contains the master organized knowledge; and
- `data/database`, which contains documents, conversations, traces, and analytics.

The Qdrant Docker volume can also be backed up, but it is less critical because its index can be
recreated from OKF with:

```powershell
.\.venv\Scripts\python.exe -m app.cli rebuild-index
```

This rebuild command replaces the configured Qdrant collection. It does not delete your source
files or SQLite analytics.

## 21. Common problems in plain language

### “PowerShell cannot run this script”

Use the bypass form:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

This changes the policy only for that setup process.

### “Python” or “py” is not recognized

Install 64-bit Python 3.12 with the Python launcher option enabled. Close and reopen PowerShell,
then check:

```powershell
py -3.12 --version
```

### “docker” is not recognized

Close and reopen PowerShell after installing Docker Desktop. If the current terminal still cannot
find it, run:

```powershell
$env:Path += ';C:\Program Files\Docker\Docker\resources\bin'
```

Then try:

```powershell
docker info
```

### Docker is installed, but the engine is unavailable

Open Docker Desktop and wait until it reports that the engine is running. Then run:

```powershell
docker compose up -d
```

### Qdrant is not healthy

Check its status and recent messages:

```powershell
docker compose ps
docker compose logs qdrant
```

Also check that another program is not already using ports 6333 or 6334.

### Ollama is unavailable

Start Ollama, then open `http://localhost:11434/api/tags` in a browser. If it is working, the page
returns information about installed models.

### A required model is missing

Run:

```powershell
ollama pull gemma4:e4b
ollama pull embeddinggemma
ollama list
```

### The browser testing page does not open

The API is probably not running. Return to the project folder and start it:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Keep that window open while using the browser page.

### Upload returns response code 400

The file is probably too large, unsupported, damaged, encrypted, or inconsistent with its file
extension. Try a normal PDF, DOCX, PPTX, XLSX, HTML, TXT, or Markdown file smaller than 50 MB.

### A question returns no answer

This usually means the application did not find strong enough evidence. Check that:

- the correct document appears under **GET /api/documents**;
- its status is `ready`;
- your question uses enough specific detail;
- the information actually appears in the uploaded document; and
- the retrieved `sources` are relevant.

You can also inspect **GET /api/trace/{query_id}** to see what was retrieved.

### A request returns response code 503

The API is running, but Ollama or Qdrant is probably unavailable. Run:

```powershell
.\scripts\doctor.ps1
```

Fix the item marked `[FAIL]` and try again.

### The first answer is very slow

This can be normal. Ollama may be loading a large model into memory. Later questions are usually
faster. Speed also depends on available memory, CPU, and GPU support.

### FFmpeg warning appears

Some optional MarkItDown audio features look for FFmpeg. Normal PDF, Word, PowerPoint, Excel, HTML,
text, and Markdown ingestion does not require audio support.

## 22. Important safety and privacy limits

- Documents are intended to stay on the local computer during normal operation.
- Uploaded documents are treated as untrusted information, not as instructions for the system.
- Files are read, not executed.
- The application checks type, size, name, and common file signatures before accepting uploads.
- The service has no user-login or permission system. It is suitable for local development but
  should not be exposed directly to the public internet.
- Anyone who can access the computer, the local API, or the `data` folder may be able to access the
  stored information. Use normal operating-system permissions and disk encryption for sensitive
  documents.
- AI answers can still be imperfect. Verify important answers against the returned sources.
- Do not treat this system as a substitute for professional legal, medical, financial, or safety
  review.

## 23. One-page everyday checklist

### Start

```powershell
Set-Location C:\Projects\ausm-rag
docker compose up -d
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Then open `http://127.0.0.1:8000/docs`.

### Use

1. Run **GET /health** and confirm `status: ok`.
2. Use **POST /api/ingest** to choose and upload a document.
3. Confirm the result says `status: ready`.
4. Use **POST /api/query** to ask a question.
5. Read `answer` and verify it against `sources`.
6. Reuse the same `session_id` for follow-up questions.

### Stop

Press `Ctrl+C` in the Uvicorn window. Optionally run:

```powershell
docker compose down
```

Your documents remain stored for the next session.

## 24. The simplest mental model to remember

The entire project can be remembered as this short story:

> You upload a file. The application safely reads it, organizes it, and makes a fast local search
> index. When you ask a question, it searches by both wording and meaning, checks whether the found
> passages are good enough, and asks a local AI model to explain only that evidence. It returns the
> answer with sources so you can verify it.
