"""Live integration tests requiring a running Ollama service with qwen2.5:3b."""

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.schemas import AskResponse


@pytest.mark.live
def test_live_ollama_query_version_skew():
    """Verify end-to-end query execution against real live Ollama instance."""
    with TestClient(app) as client:
        resp = client.post(
            "/ask",
            json={
                "question": "How many minor versions older than kube-apiserver can a kubelet be supported at?",
                "top_k": 3,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        validated = AskResponse.model_validate(data)
        assert validated.refused is False
        assert len(validated.citations) > 0
        assert len(validated.retrieved_chunk_ids) > 0
        assert validated.latency_ms > 0
        assert any(c.version == "1.27" for c in validated.citations) or any(c.version == "1.31" for c in validated.citations)
