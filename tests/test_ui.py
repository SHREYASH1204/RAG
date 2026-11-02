"""Tests for the minimal static web UI and version-pinned /ask requests."""

import pytest
from fastapi.testclient import TestClient

from app.api import app, set_llm_client
from app.llm import FakeLLMClient


@pytest.fixture(scope="module")
def client():
    # Inject fake LLM client so tests run deterministically and fast
    fake_client = FakeLLMClient()
    set_llm_client(fake_client)
    with TestClient(app) as test_client:
        yield test_client
    set_llm_client(None)


def test_get_root_returns_html(client):
    """GET / must return HTTP 200 with text/html content."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    html = resp.text
    assert "<!DOCTYPE html>" in html or "<html" in html
    assert "Kubernetes Dual-Version RAG Assistant" in html
    assert "question-input" in html
    assert "version-select" in html
    assert "ask-btn" in html


def test_ask_schema_unpinned(client):
    """POST /ask without version field must return the exact 5-field schema."""
    payload = {"question": "What is a Pod in Kubernetes?", "top_k": 5}
    resp = client.post("/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    expected_fields = {"answer", "refused", "citations", "retrieved_chunk_ids", "latency_ms"}
    assert set(data.keys()) == expected_fields
    assert isinstance(data["answer"], str)
    assert isinstance(data["refused"], bool)
    assert isinstance(data["citations"], list)
    assert isinstance(data["retrieved_chunk_ids"], list)
    assert isinstance(data["latency_ms"], int)


def test_ask_schema_pinned_127(client):
    """POST /ask with version: '1.27' must return the exact 5-field schema."""
    payload = {"question": "What is a Pod in Kubernetes 1.27?", "top_k": 5, "version": "1.27"}
    resp = client.post("/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    expected_fields = {"answer", "refused", "citations", "retrieved_chunk_ids", "latency_ms"}
    assert set(data.keys()) == expected_fields
    assert isinstance(data["answer"], str)
    assert isinstance(data["refused"], bool)
    assert isinstance(data["citations"], list)
    assert isinstance(data["retrieved_chunk_ids"], list)
    assert isinstance(data["latency_ms"], int)


def test_ask_schema_pinned_131(client):
    """POST /ask with version: '1.31' must return the exact 5-field schema."""
    payload = {"question": "What is a Pod in Kubernetes 1.31?", "top_k": 5, "version": "1.31"}
    resp = client.post("/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    expected_fields = {"answer", "refused", "citations", "retrieved_chunk_ids", "latency_ms"}
    assert set(data.keys()) == expected_fields
    assert isinstance(data["answer"], str)
    assert isinstance(data["refused"], bool)
    assert isinstance(data["citations"], list)
    assert isinstance(data["retrieved_chunk_ids"], list)
    assert isinstance(data["latency_ms"], int)

