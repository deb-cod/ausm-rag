import os
from typing import Any
from uuid import uuid4

import streamlit as st

from frontend.api_client import APIError, SmartRAGClient
from frontend.styles import apply_styles, page_intro

st.set_page_config(
    page_title="AUSM Knowledge Studio",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_styles()


PAGES = ("Ask", "Library", "Operations", "Insights", "Diagnostics")
EXAMPLE_QUESTIONS = (
    "Summarize the main ideas in the indexed documents.",
    "What are the most important definitions in the document?",
    "Compare the two main approaches discussed in the documents.",
)


def initialize_state() -> None:
    defaults: dict[str, Any] = {
        "api_url": os.getenv("RAG_API_URL", "http://127.0.0.1:8000"),
        "session_id": new_session_id(),
        "chat_messages": [],
        "loaded_chat_session": "",
        "last_query_id": "",
        "last_upload_results": [],
        "delete_candidate": None,
        "last_reindex_result": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def new_session_id() -> str:
    return f"ui_{uuid4().hex[:12]}"


@st.cache_data(ttl=8, show_spinner=False)
def cached_health(base_url: str) -> dict[str, Any]:
    return SmartRAGClient(base_url).health()


def show_error(exc: APIError, *, context: str = "Request failed") -> None:
    st.error(f"{context}: {exc}")
    if exc.status_code == 400:
        st.caption("Check the selected file and the detailed message returned by the API.")
    elif exc.status_code == 422:
        st.caption(
            "Check required fields and make sure the session ID uses only letters, numbers, "
            "- and _."
        )
    elif exc.status_code == 503 or exc.status_code is None:
        st.caption(
            "Start Uvicorn, Ollama, and Qdrant, then open the Operations page for health details."
        )


def sidebar() -> tuple[str, SmartRAGClient]:
    with st.sidebar:
        st.markdown("## ◈ AUSM")
        st.caption("Local Knowledge Studio")
        st.text_input(
            "FastAPI URL",
            key="api_url",
            help="The Streamlit server calls this URL. No browser CORS setup is required.",
        )
        base_url = st.session_state.api_url.strip().rstrip("/")
        client = SmartRAGClient(base_url)

        try:
            health = cached_health(base_url)
            healthy = health.get("status") == "ok"
            if healthy:
                st.success("API and services ready")
            else:
                st.warning("Services are degraded")
        except APIError:
            st.error("API is offline")

        page = st.radio("Workspace", PAGES, label_visibility="collapsed")
        st.divider()
        st.text_input(
            "Conversation session",
            key="session_id",
            max_chars=128,
            help=(
                "Use the same ID for follow-up questions. Valid characters: letters, numbers, "
                "- and _."
            ),
        )
        if st.button("New conversation", width="stretch"):
            st.session_state.session_id = new_session_id()
            st.session_state.chat_messages = []
            st.session_state.loaded_chat_session = ""
            st.session_state.last_query_id = ""
            st.rerun()

        st.divider()
        st.markdown(f"[FastAPI Swagger ↗]({base_url}/docs)")
        st.markdown("[Qdrant dashboard ↗](http://127.0.0.1:6333/dashboard)")
        st.caption("Documents and conversations remain local to this installation.")
    return page, client


def metric_value(value: Any, fallback: str = "—") -> str:
    return fallback if value is None else str(value)


def score_text(value: Any) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "—"


def render_response_details(response: dict[str, Any], *, expanded_sources: bool = False) -> None:
    columns = st.columns(5)
    columns[0].metric("Confidence", score_text(response.get("confidence")))
    columns[1].metric("Query type", metric_value(response.get("query_type")))
    columns[2].metric("Rounds", metric_value(response.get("retrieval_rounds")))
    columns[3].metric("Sources", len(response.get("sources") or []))
    latency = response.get("latency_ms")
    latency_label = f"{float(latency):.0f} ms" if isinstance(latency, int | float) else "—"
    columns[4].metric("Latency", latency_label)

    if response.get("no_answer"):
        st.warning(
            "The evidence checker did not find enough support. The API intentionally returned "
            "no citations."
        )
    standalone = response.get("standalone_query")
    original = response.get("original_query")
    if standalone and standalone != original:
        st.caption(f"Search form: {standalone}")

    sources = response.get("sources") or []
    if not sources:
        return
    with st.expander(f"Evidence and citations ({len(sources)})", expanded=expanded_sources):
        for position, source in enumerate(sources, 1):
            citation = source.get("citation") or position
            title = source.get("title") or source.get("source_file") or "Untitled source"
            heading_path = " › ".join(source.get("heading_path") or [])
            heading = heading_path or source.get("heading") or "No extracted heading"
            st.markdown(f"#### [{citation}] {title}")
            st.caption(
                f"{heading} · score {score_text(source.get('score'))} · "
                f"{', '.join(source.get('channels') or ['unknown channel'])}"
            )
            if source.get("is_stale"):
                st.warning("This source is marked stale by its OKF metadata.")
            content = str(source.get("content") or "No evidence text returned.")
            st.markdown(content)
            st.caption(
                f"Document {source.get('document_id', '—')} · "
                f"Chunk {source.get('chunk_id', '—')} · "
                f"Trust {source.get('trust_tier', 'unverified')}"
            )
            if position < len(sources):
                st.divider()


def render_chat_message(message: dict[str, Any]) -> None:
    role = message.get("role", "assistant")
    # Let Streamlit choose its built-in user/assistant avatar. Decorative text symbols such as
    # `●` and `◈` are not emoji and newer Streamlit versions reject them as image inputs.
    with st.chat_message(role):
        st.markdown(message.get("content", ""))
        response = message.get("response")
        if isinstance(response, dict):
            render_response_details(response)


def load_conversation_history(client: SmartRAGClient) -> None:
    """Load saved messages when the user opens or changes a conversation ID."""
    session_id = st.session_state.session_id.strip()
    if not session_id or st.session_state.loaded_chat_session == session_id:
        return
    try:
        saved_messages = client.conversation_messages(session_id)
    except APIError:
        # The sidebar already reports API availability. Keep any browser-local messages and retry
        # on a later rerun instead of replacing the conversation with an error screen.
        return
    st.session_state.chat_messages = [
        {
            "role": message.get("role", "assistant"),
            "content": str(message.get("content") or ""),
        }
        for message in saved_messages
        if message.get("role") in {"user", "assistant"}
    ]
    st.session_state.loaded_chat_session = session_id


def run_standard_query(client: SmartRAGClient, prompt: str) -> dict[str, Any]:
    with st.spinner("Analyzing, retrieving evidence, and writing a grounded answer…"):
        response = client.query(st.session_state.session_id, prompt)
    st.markdown(response.get("answer") or "No answer text was returned.")
    render_response_details(response, expanded_sources=True)
    return response


def run_streaming_query(client: SmartRAGClient, prompt: str) -> dict[str, Any]:
    answer_box = st.empty()
    answer_text = ""
    final_response: dict[str, Any] | None = None
    streamed_sources: list[dict[str, Any]] = []
    with st.status("Starting query…", expanded=True) as status:
        for event, data in client.query_stream(st.session_state.session_id, prompt):
            if event == "query_analyzed":
                status.write("Question accepted and analysis started.")
            elif event == "retrieving":
                status.update(label="Searching the knowledge base…")
            elif event == "generating":
                status.update(label="Evidence checked; preparing the answer…")
            elif event == "token" and isinstance(data, dict):
                answer_text += str(data.get("text", ""))
                answer_box.markdown(answer_text + "▌")
            elif event == "sources" and isinstance(data, dict):
                streamed_sources = list(data.get("sources") or [])
            elif event == "done" and isinstance(data, dict):
                final_response = data
            elif event == "error":
                detail = data.get("detail") if isinstance(data, dict) else data
                status.update(label="Query failed", state="error")
                raise APIError(str(detail or "The streaming query failed."))
        status.update(label="Answer complete", state="complete", expanded=False)

    if final_response is None:
        final_response = {
            "answer": answer_text.strip(),
            "sources": streamed_sources,
            "no_answer": not bool(answer_text.strip()),
        }
    answer_text = str(final_response.get("answer") or answer_text).strip()
    answer_box.markdown(answer_text or "No answer text was returned.")
    render_response_details(final_response, expanded_sources=True)
    return final_response


def ask_page(client: SmartRAGClient) -> None:
    load_conversation_history(client)
    page_intro(
        "Grounded conversation",
        "Ask your knowledge base",
        "Get an evidence-checked answer with visible citations and retrieval details.",
    )
    controls = st.columns([1, 1, 2])
    stream = controls[0].toggle(
        "SSE response",
        value=True,
        help="Uses /api/query/stream. The current backend emits words after generation finishes.",
    )
    show_examples = controls[1].toggle("Example prompts", value=not st.session_state.chat_messages)
    controls[2].caption(f"Conversation: `{st.session_state.session_id}`")

    selected_prompt: str | None = None
    if show_examples:
        example_columns = st.columns(3)
        for index, question in enumerate(EXAMPLE_QUESTIONS):
            if example_columns[index].button(question, key=f"example_{index}", width="stretch"):
                selected_prompt = question

    if not st.session_state.chat_messages:
        st.info(
            "Upload a document from **Library** first, then ask a specific question about "
            "its content."
        )
    for message in st.session_state.chat_messages:
        render_chat_message(message)
    if st.session_state.chat_messages:
        st.caption(
            "Ask your next question below. Earlier messages in this conversation will be used "
            "as follow-up context."
        )

    typed_prompt = st.chat_input("Ask a question about your indexed documents")
    prompt = selected_prompt or typed_prompt
    if not prompt:
        return
    prompt = prompt.strip()
    if not prompt:
        return

    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        try:
            response = (
                run_streaming_query(client, prompt)
                if stream
                else run_standard_query(client, prompt)
            )
        except APIError as exc:
            show_error(exc, context="Could not answer")
            st.session_state.chat_messages.append(
                {
                    "role": "assistant",
                    "content": f"I could not answer that question: {exc}",
                }
            )
            return
    answer = str(response.get("answer") or "No answer text was returned.")
    st.session_state.chat_messages.append(
        {"role": "assistant", "content": answer, "response": response}
    )
    st.session_state.last_query_id = str(response.get("query_id") or "")


def document_summary(document: dict[str, Any]) -> str:
    metadata = document.get("metadata") or {}
    title = metadata.get("title") if isinstance(metadata, dict) else None
    return str(title or document.get("filename") or "Untitled document")


def library_page(client: SmartRAGClient) -> None:
    page_intro(
        "Knowledge management",
        "Document library",
        "Upload supported files, inspect their registry information, and remove them safely.",
    )
    upload_tab, documents_tab = st.tabs(["Upload", "Indexed documents"])

    with upload_tab:
        st.subheader("Add documents")
        st.caption(
            "Supported: PDF, DOCX, PPTX, XLSX, HTML, TXT, and Markdown. Default limit: 50 MB each."
        )
        uploads = st.file_uploader(
            "Choose one or more files",
            type=["pdf", "docx", "pptx", "xlsx", "html", "htm", "txt", "md"],
            accept_multiple_files=True,
        )
        if st.button("Upload and index", type="primary", disabled=not uploads):
            results: list[dict[str, Any]] = []
            progress = st.progress(0, text="Preparing uploads…")
            for index, upload in enumerate(uploads or [], 1):
                progress.progress(
                    (index - 1) / len(uploads),
                    text=f"Indexing {upload.name} ({index}/{len(uploads)})…",
                )
                try:
                    result = client.ingest(upload.name, upload.getvalue(), upload.type)
                    results.append({"filename": upload.name, "ok": True, "result": result})
                except APIError as exc:
                    results.append({"filename": upload.name, "ok": False, "error": str(exc)})
            progress.progress(1.0, text="Upload batch complete.")
            st.session_state.last_upload_results = results
            cached_health.clear()

        for item in st.session_state.last_upload_results:
            if item.get("ok"):
                result = item["result"]
                if result.get("duplicate"):
                    st.info(
                        f"{item['filename']} was already indexed; the existing record was reused."
                    )
                else:
                    st.success(
                        f"{item['filename']} is ready with {result.get('chunks', 0)} "
                        "searchable chunks."
                    )
                with st.expander(f"Upload details · {item['filename']}"):
                    st.json(result)
            else:
                st.error(f"{item['filename']}: {item.get('error', 'Upload failed')}")

    with documents_tab:
        top = st.columns([3, 1])
        top[0].subheader("Registered documents")
        if top[1].button("Refresh", key="refresh_documents", width="stretch"):
            st.rerun()
        try:
            documents = client.documents()
        except APIError as exc:
            show_error(exc, context="Could not load documents")
            return
        if not documents:
            st.info("No documents are registered. Use the Upload tab to build the knowledge base.")
            return

        total_chunks = sum(int(item.get("chunk_count") or 0) for item in documents)
        summary = st.columns(2)
        summary[0].metric("Documents", len(documents))
        summary[1].metric("Registered chunks", total_chunks)

        for document in documents:
            document_id = str(document.get("document_id"))
            title = document_summary(document)
            with st.expander(f"{title} · {document.get('chunk_count', 0)} chunks"):
                detail_columns = st.columns([2, 1, 1])
                detail_columns[0].markdown(f"**Filename**  \n{document.get('filename', '—')}")
                detail_columns[1].markdown(f"**Type**  \n{document.get('source_type', '—')}")
                detail_columns[2].markdown(f"**Status**  \n{document.get('status', '—')}")
                st.caption(f"Document ID: {document_id}")
                st.caption(f"SHA-256: {document.get('sha256', '—')}")
                dates = st.columns(2)
                dates[0].caption(f"Created: {document.get('created_at', '—')}")
                dates[1].caption(f"Updated: {document.get('updated_at', '—')}")
                metadata = document.get("metadata") or {}
                if metadata:
                    st.markdown("**Conversion metadata**")
                    st.json(metadata)
                if st.button("Delete document", key=f"delete_{document_id}", type="secondary"):
                    st.session_state.delete_candidate = document_id

        candidate = st.session_state.delete_candidate
        if candidate:
            selected = next(
                (item for item in documents if item.get("document_id") == candidate), None
            )
            name = selected.get("filename") if selected else candidate
            st.warning(
                f"Delete **{name}**? This removes its source, Markdown, OKF, SQLite record, "
                "and Qdrant points."
            )
            confirm, cancel, _ = st.columns([1, 1, 3])
            if confirm.button("Confirm delete", type="primary", width="stretch"):
                try:
                    client.delete_document(candidate)
                    st.session_state.delete_candidate = None
                    cached_health.clear()
                    st.toast(f"Deleted {name}", icon="✅")
                    st.rerun()
                except APIError as exc:
                    show_error(exc, context="Deletion failed")
            if cancel.button("Cancel", width="stretch"):
                st.session_state.delete_candidate = None
                st.rerun()


def service_card(component: str, details: dict[str, Any]) -> None:
    status = str(details.get("status", "unknown"))
    symbol = "●" if status == "ok" else "◆" if status == "missing" else "○"
    st.markdown(
        f"""
        <div class="rag-service">
          <div class="rag-service-name">{component.replace("_", " ")}</div>
          <div class="rag-service-status">{symbol} {status}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if details.get("model"):
        st.caption(str(details["model"]))
    elif details.get("url"):
        st.caption(str(details["url"]))


def operations_page(client: SmartRAGClient) -> None:
    page_intro(
        "System control",
        "Operations",
        "Inspect service readiness and perform deliberate maintenance operations.",
    )
    refresh, _ = st.columns([1, 5])
    if refresh.button("Refresh health", width="stretch"):
        cached_health.clear()
        st.rerun()
    try:
        health = cached_health(client.base_url)
    except APIError as exc:
        show_error(exc, context="Health check failed")
        return

    overall = health.get("status", "unknown")
    if overall == "ok":
        st.success("All configured services are ready.")
    else:
        st.warning("At least one configured service is missing or unavailable.")
    components = health.get("components") or {}
    ordered_names = ("api", "sqlite", "qdrant", "ollama", "llm_model", "embedding_model")
    columns = st.columns(3)
    for index, name in enumerate(ordered_names):
        with columns[index % 3]:
            service_card(name, components.get(name, {"status": "unknown"}))

    with st.expander("Raw health response"):
        st.json(health)

    st.divider()
    st.subheader("Rebuild Qdrant from OKF")
    st.write(
        "Use this when the Qdrant index is missing, the embedding/chunking implementation changed, "
        "or OKF was deliberately edited. The configured Qdrant collection is deleted and recreated."
    )
    st.warning(
        "Queries may fail while the collection is being replaced. Avoid uploading documents "
        "at the same time."
    )
    understood = st.checkbox(
        "I understand that this replaces the configured Qdrant collection",
        key="reindex_confirmation",
    )
    if st.button("Rebuild search index", type="primary", disabled=not understood):
        try:
            with st.spinner("Reading OKF, chunking concepts, and rebuilding Qdrant…"):
                result = client.reindex()
            st.session_state.last_reindex_result = result
            cached_health.clear()
            st.success(
                f"Rebuild complete: {result.get('concepts', 0)} concepts and "
                f"{result.get('chunks', 0)} chunks."
            )
        except APIError as exc:
            show_error(exc, context="Reindex failed")
    if st.session_state.last_reindex_result:
        st.json(st.session_state.last_reindex_result)


def insights_page(client: SmartRAGClient) -> None:
    page_intro(
        "Usage intelligence",
        "Insights",
        "Review knowledge-base size, question patterns, confidence, and comparison activity.",
    )
    limit = st.slider("Analytics result limit", min_value=1, max_value=100, value=20)
    try:
        stats = client.stats()
        questions = client.question_analytics(limit)
        comparisons = client.comparison_analytics(limit)
    except APIError as exc:
        show_error(exc, context="Could not load analytics")
        return

    metrics = st.columns(6)
    metrics[0].metric("Documents", metric_value(stats.get("documents_indexed"), "0"))
    metrics[1].metric("Chunks", metric_value(stats.get("chunks_indexed"), "0"))
    metrics[2].metric("Questions", metric_value(stats.get("total_questions"), "0"))
    metrics[3].metric("Comparisons", metric_value(stats.get("comparison_queries"), "0"))
    metrics[4].metric("No answers", metric_value(stats.get("no_answer_count"), "0"))
    average = stats.get("average_query_latency_ms")
    metrics[5].metric("Avg latency", f"{float(average or 0):.0f} ms")

    type_counts = stats.get("queries_by_type") or {}
    if type_counts:
        st.subheader("Questions by type")
        st.bar_chart(
            [{"query_type": name, "count": count} for name, count in type_counts.items()],
            x="query_type",
            y="count",
        )

    left, right = st.columns(2)
    with left:
        st.subheader("Most common questions")
        common = questions.get("most_common") or []
        if common:
            st.dataframe(common, width="stretch", hide_index=True)
        else:
            st.info("No question history yet.")
    with right:
        st.subheader("Comparison pairs")
        comparison_rows = [
            {
                "First": item.get("entity_a"),
                "Second": item.get("entity_b"),
                "Count": item.get("count"),
                "Last asked": item.get("last_asked"),
            }
            for item in comparisons
        ]
        if comparison_rows:
            st.dataframe(comparison_rows, width="stretch", hide_index=True)
        else:
            st.info("No comparison questions recorded.")

    st.subheader("Lowest-confidence answers")
    low_confidence = questions.get("low_confidence") or []
    if low_confidence:
        st.dataframe(
            [
                {
                    "Question": item.get("original_query"),
                    "Type": item.get("query_type"),
                    "Confidence": item.get("answer_confidence"),
                    "No answer": item.get("no_answer"),
                    "Created": item.get("created_at"),
                    "Query ID": item.get("id"),
                }
                for item in low_confidence
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No completed query confidence records are available.")

    with st.expander("Raw statistics"):
        st.json(stats)


def diagnostics_page(client: SmartRAGClient) -> None:
    page_intro(
        "Retrieval observability",
        "Diagnostics",
        "Inspect saved queries, their analysis plans, citation records, and retrieval-round "
        "measurements.",
    )
    query_limit = st.slider("Recent query limit", min_value=1, max_value=500, value=50)
    try:
        queries = client.queries(query_limit)
    except APIError as exc:
        show_error(exc, context="Could not load query history")
        return

    query_ids = [str(item.get("id")) for item in queries if item.get("id")]
    default_id = st.session_state.last_query_id
    if default_id and default_id not in query_ids:
        query_ids.insert(0, default_id)

    if query_ids:
        by_id = {str(item.get("id")): item for item in queries}

        def format_query(query_id: str) -> str:
            item = by_id.get(query_id, {})
            question = str(item.get("original_query") or "Query details")
            if len(question) > 80:
                question = question[:77] + "…"
            return f"{question} · {query_id[:8]}"

        selected_id = st.selectbox("Saved query", query_ids, format_func=format_query)
    else:
        st.info("No saved queries exist yet. Ask a question first or enter a known query ID below.")
        selected_id = ""

    manual_id = st.text_input(
        "Or paste another query ID",
        value="",
        placeholder="Paste a query_id returned by /api/query",
    ).strip()
    target_id = manual_id or selected_id
    if not target_id:
        return

    try:
        detail = client.query_detail(target_id)
        trace = client.trace(target_id)
    except APIError as exc:
        show_error(exc, context="Could not load query diagnostics")
        return

    overview_tab, plan_tab, retrieval_tab, raw_tab = st.tabs(
        ["Overview", "Plan", "Retrieval rounds", "Raw JSON"]
    )
    with overview_tab:
        st.markdown(f"### {detail.get('original_query', 'Saved query')}")
        st.write(detail.get("answer") or "No saved answer text.")
        retrieval_runs = trace.get("retrieval_rounds") or []
        round_count = len(
            {
                item.get("round_number")
                for item in retrieval_runs
                if item.get("round_number") is not None
            }
        )
        overview = st.columns(5)
        overview[0].metric("Type", metric_value(detail.get("query_type")))
        overview[1].metric("Confidence", score_text(detail.get("answer_confidence")))
        overview[2].metric("No answer", "Yes" if detail.get("no_answer") else "No")
        overview[3].metric("Rounds", round_count)
        latency = detail.get("latency_ms")
        overview[4].metric("Latency", f"{float(latency or 0):.0f} ms")
        st.caption(
            f"Session: {detail.get('session_id', '—')} · Created: {detail.get('created_at', '—')}"
        )
        sources = detail.get("sources") or []
        if sources:
            st.subheader("Saved citation records")
            st.dataframe(sources, width="stretch", hide_index=True)
        else:
            st.info("No citations were saved for this query.")

    with plan_tab:
        plan = trace.get("plan")
        if plan:
            st.json(plan)
        else:
            st.info("No saved plan exists for this query.")

    with retrieval_tab:
        rounds = trace.get("retrieval_rounds") or []
        if rounds:
            st.dataframe(rounds, width="stretch", hide_index=True)
            duration = sum(float(item.get("duration_ms") or 0) for item in rounds)
            st.caption(
                f"Recorded retrieval work: {duration:.1f} ms across {len(rounds)} run record(s)."
            )
        else:
            st.info("No retrieval rounds were saved.")

    with raw_tab:
        st.markdown("**Query detail**")
        st.json(detail)
        st.markdown("**Trace**")
        st.json(trace)


initialize_state()
selected_page, api_client = sidebar()

if selected_page == "Ask":
    ask_page(api_client)
elif selected_page == "Library":
    library_page(api_client)
elif selected_page == "Operations":
    operations_page(api_client)
elif selected_page == "Insights":
    insights_page(api_client)
else:
    diagnostics_page(api_client)
