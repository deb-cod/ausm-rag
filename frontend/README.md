# AUSM Knowledge Studio

This folder contains the Streamlit user interface for AUSM Smart RAG. It is a client of the existing
FastAPI application: it does not read SQLite, OKF, or Qdrant directly.

## What the UI can do

- Ask normal or server-sent-event (SSE) questions.
- Maintain a local conversation view and reuse API session IDs for follow-ups.
- Display confidence, query type, latency, retrieval rounds, citations, and evidence text.
- Upload one or many supported documents.
- List registered documents and delete them through the complete lifecycle API.
- Check FastAPI, SQLite, Qdrant, Ollama, and model health.
- Rebuild Qdrant from canonical OKF with explicit confirmation.
- Display document/query statistics and question/comparison analytics.
- Inspect saved query details, plans, citation records, and retrieval traces.

## Start it on Windows

The FastAPI server must be running first. From the repository root, use two PowerShell terminals.

Terminal 1:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Terminal 2:

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py `
  --server.address 127.0.0.1 `
  --server.port 8501
```

Open `http://127.0.0.1:8501`.

If Streamlit is missing because the virtual environment was created before the UI was added, run:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Linux or macOS

```bash
python -m uvicorn app.main:app --reload
```

In another terminal:

```bash
python -m streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501
```

## Use another API address

The default API URL is `http://localhost:8000`. It can be changed in the UI sidebar or supplied when
Streamlit starts:

```powershell
$env:RAG_API_URL = "http://192.168.1.20:8000"
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py
```

`RAG_API_URL` affects only the Streamlit client. It is separate from the application's `.env` file.

## Architecture

```text
Browser
  -> Streamlit at 127.0.0.1:8501
      -> FastAPI at localhost:8000
          -> Ollama
          -> Qdrant
          -> SQLite
          -> data/okf and other local files
```

The browser communicates with Streamlit. Streamlit's Python process calls FastAPI using `httpx`, so
a separate-browser-origin CORS configuration is not needed for this UI.

## Troubleshooting

- **UI says API is offline:** start Uvicorn and verify `http://localhost:8000/health`.
- **Services are degraded:** open Operations and inspect each health component.
- **Upload takes time:** initial document embeddings may need to be calculated locally.
- **Question takes time:** Ollama may be loading a model; watch the API and Ollama terminals.
- **SSE appears to pause:** the backend currently finishes generation before emitting answer words.
- **Another machine cannot connect:** both Uvicorn and Streamlit default to loopback for safety. Only
  bind to a network interface after adding appropriate authentication and network protection.
