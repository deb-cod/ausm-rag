import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class APIError(RuntimeError):
    """A safe, display-ready error returned by the Smart RAG API."""

    message: str
    status_code: int | None = None

    def __str__(self) -> str:
        if self.status_code is None:
            return self.message
        return f"API returned HTTP {self.status_code}: {self.message}"


class SmartRAGClient:
    """Small synchronous client used by Streamlit and its tests."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 300,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.timeout = timeout
        self.transport = transport

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health", timeout=20)

    def ingest(self, filename: str, content: bytes, content_type: str | None) -> dict[str, Any]:
        media_type = content_type or "application/octet-stream"
        return self._request(
            "POST",
            "/api/ingest",
            files={"file": (filename, content, media_type)},
            timeout=900,
        )

    def documents(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/documents", timeout=30)

    def delete_document(self, document_id: str) -> None:
        self._request("DELETE", f"/api/documents/{document_id}", timeout=180)

    def reindex(self) -> dict[str, int]:
        return self._request("POST", "/api/reindex", timeout=1800)

    def query(self, session_id: str, question: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/query",
            json={"session_id": session_id, "query": question},
            timeout=600,
        )

    def query_stream(self, session_id: str, question: str) -> Iterator[tuple[str, Any]]:
        payload = {"session_id": session_id, "query": question}
        try:
            with self._client(timeout=600).stream(
                "POST", "/api/query/stream", json=payload
            ) as response:
                self._raise_for_status(response)
                event_name = "message"
                data_lines: list[str] = []
                for line in response.iter_lines():
                    if line == "":
                        if data_lines:
                            yield event_name, self._decode_event_data("\n".join(data_lines))
                        event_name = "message"
                        data_lines = []
                        continue
                    if line.startswith(":"):
                        continue
                    field, separator, value = line.partition(":")
                    if not separator:
                        continue
                    value = value[1:] if value.startswith(" ") else value
                    if field == "event":
                        event_name = value
                    elif field == "data":
                        data_lines.append(value)
                if data_lines:
                    yield event_name, self._decode_event_data("\n".join(data_lines))
        except APIError:
            raise
        except httpx.HTTPError as exc:
            raise APIError(self._connection_message(exc)) from exc

    def queries(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._request("GET", "/api/queries", params={"limit": limit}, timeout=30)

    def conversation_messages(
        self, session_id: str, limit: int = 200
    ) -> list[dict[str, Any]]:
        return self._request(
            "GET",
            f"/api/sessions/{session_id}/messages",
            params={"limit": limit},
            timeout=30,
        )

    def query_detail(self, query_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/queries/{query_id}", timeout=30)

    def trace(self, query_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/trace/{query_id}", timeout=30)

    def question_analytics(self, limit: int = 20) -> dict[str, Any]:
        return self._request("GET", "/api/analytics/questions", params={"limit": limit}, timeout=30)

    def comparison_analytics(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._request(
            "GET", "/api/analytics/comparisons", params={"limit": limit}, timeout=30
        )

    def stats(self) -> dict[str, Any]:
        return self._request("GET", "/api/stats", timeout=30)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        timeout = kwargs.pop("timeout", self.timeout)
        try:
            with self._client(timeout=timeout) as client:
                response = client.request(method, path, **kwargs)
                self._raise_for_status(response)
                if response.status_code == 204 or not response.content:
                    return None
                return response.json()
        except APIError:
            raise
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise APIError("The API returned a response that was not valid JSON.") from exc
        except httpx.HTTPError as exc:
            raise APIError(self._connection_message(exc)) from exc

    def _client(self, *, timeout: float) -> httpx.Client:
        if not self.base_url:
            raise APIError("Enter the FastAPI base URL in the sidebar.")
        return httpx.Client(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout),
            transport=self.transport,
            follow_redirects=True,
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if not response.is_error:
            return
        detail: Any = None
        try:
            # Streaming responses are not preloaded. Error bodies are small and must be read before
            # JSON decoding so callers still receive the API's useful `detail` message.
            if not response.is_closed:
                response.read()
            payload = response.json()
            detail = payload.get("detail") if isinstance(payload, dict) else payload
        except (httpx.HTTPError, json.JSONDecodeError, UnicodeDecodeError):
            detail = response.text.strip()
        if isinstance(detail, list):
            messages = [
                str(item.get("msg", item)) if isinstance(item, dict) else str(item)
                for item in detail
            ]
            detail = "; ".join(messages)
        message = str(detail or response.reason_phrase or "Request failed")
        raise APIError(message=message, status_code=response.status_code)

    @staticmethod
    def _decode_event_data(data: str) -> Any:
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return data

    def _connection_message(self, exc: httpx.HTTPError) -> str:
        if isinstance(exc, httpx.TimeoutException):
            return (
                "The request timed out. The local model may still be working; check the API "
                "terminal before retrying."
            )
        return (
            f"Could not communicate with FastAPI at {self.base_url}. "
            "Make sure Uvicorn is running, then check /health."
        )
