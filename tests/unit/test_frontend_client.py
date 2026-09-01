import json

import httpx
import pytest

from frontend.api_client import APIError, SmartRAGClient


def test_client_covers_health_documents_query_and_analytics():
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        responses = {
            "/health": {"status": "ok", "components": {}},
            "/api/documents": [],
            "/api/query": {"query_id": "q1", "answer": "Grounded answer"},
            "/api/queries": [],
            "/api/sessions/session_1/messages": [
                {"role": "user", "content": "Question?"},
                {"role": "assistant", "content": "Grounded answer"},
            ],
            "/api/queries/q1": {"id": "q1"},
            "/api/trace/q1": {"query_id": "q1"},
            "/api/analytics/questions": {"most_common": []},
            "/api/analytics/comparisons": [],
            "/api/stats": {"documents_indexed": 0},
            "/api/reindex": {"concepts": 1, "chunks": 2},
        }
        if request.url.path == "/api/documents/d1":
            return httpx.Response(204)
        return httpx.Response(200, json=responses[request.url.path])

    client = SmartRAGClient("http://test", transport=httpx.MockTransport(handler))
    assert client.health()["status"] == "ok"
    assert client.documents() == []
    assert client.query("session_1", "Question?")["query_id"] == "q1"
    assert client.queries(10) == []
    assert len(client.conversation_messages("session_1")) == 2
    assert client.query_detail("q1")["id"] == "q1"
    assert client.trace("q1")["query_id"] == "q1"
    assert client.question_analytics(5)["most_common"] == []
    assert client.comparison_analytics(5) == []
    assert client.stats()["documents_indexed"] == 0
    assert client.reindex() == {"concepts": 1, "chunks": 2}
    assert client.delete_document("d1") is None
    assert ("DELETE", "/api/documents/d1") in seen


def test_client_sends_multipart_upload():
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        assert request.method == "POST"
        assert request.url.path == "/api/ingest"
        assert b'filename="notes.txt"' in body
        assert b"hello knowledge base" in body
        return httpx.Response(201, json={"document_id": "d1", "chunks": 1})

    client = SmartRAGClient("http://test", transport=httpx.MockTransport(handler))
    result = client.ingest("notes.txt", b"hello knowledge base", "text/plain")
    assert result == {"document_id": "d1", "chunks": 1}


def test_client_preserves_api_error_detail():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"detail": "Document conversion produced no text"})

    client = SmartRAGClient("http://test", transport=httpx.MockTransport(handler))
    with pytest.raises(APIError) as caught:
        client.documents()
    assert caught.value.status_code == 400
    assert caught.value.message == "Document conversion produced no text"


def test_client_parses_server_sent_events():
    complete = {
        "query_id": "q1",
        "answer": "Hello world",
        "sources": [],
    }
    body = (
        'event: query_analyzed\ndata: {"status":"started"}\n\n'
        'event: token\ndata: {"text":"Hello "}\n\n'
        f"event: done\ndata: {json.dumps(complete)}\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/query/stream"
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    client = SmartRAGClient("http://test", transport=httpx.MockTransport(handler))
    events = list(client.query_stream("session_1", "Question?"))
    assert events[0] == ("query_analyzed", {"status": "started"})
    assert events[1] == ("token", {"text": "Hello "})
    assert events[2] == ("done", complete)


def test_client_reports_connection_failures_without_internal_exception_text():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private network detail", request=request)

    client = SmartRAGClient("http://test", transport=httpx.MockTransport(handler))
    with pytest.raises(APIError, match="Could not communicate with FastAPI"):
        client.health()
