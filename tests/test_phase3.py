import json
import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.retrieval import ChromaDenseRetriever, detect_version_in_text
from app.schemas import AskResponse, HealthResponse


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_detect_version_in_text():
    """Verify version detection only pins to 1.27 or 1.31 and ignores other versions."""
    assert detect_version_in_text("What is new in 1.27?") == "1.27"
    assert detect_version_in_text("What is new in v1.31?") == "1.31"
    assert detect_version_in_text("What is new in release-1.31?") == "1.31"
    assert detect_version_in_text("What is new in release-1.27?") == "1.27"
    # Other versions must NOT pin
    assert detect_version_in_text("What was introduced in 1.25?") is None
    assert detect_version_in_text("kubelet < 1.25") is None
    assert detect_version_in_text("supported since v1.25") is None
    assert detect_version_in_text("kubelet v1.30") is None
    # Both versions present must search both (return None)
    assert detect_version_in_text("Difference between 1.27 and 1.31") is None
    assert detect_version_in_text("Compare v1.27 with release-1.31") is None
    assert detect_version_in_text("What is a Pod?") is None


def test_retriever_version_balance_kubelet_skew():
    """Verify guaranteed version balance: kubelet skew query retrieves version-skew-policy from both 1.27 and 1.31."""
    retriever = ChromaDenseRetriever()
    results = retriever.retrieve("kubelet version skew policy", version=None, top_k=5)
    assert len(results) >= 4

    chunks_127 = [c for c, _ in results if c.metadata.version == "1.27"]
    chunks_131 = [c for c, _ in results if c.metadata.version == "1.31"]
    assert len(chunks_127) >= 2
    assert len(chunks_131) >= 2

    # Verify releases/version-skew-policy chunk is present for both versions
    doc_ids_127 = {c.metadata.doc_id for c in chunks_127}
    doc_ids_131 = {c.metadata.doc_id for c in chunks_131}
    assert "releases/version-skew-policy" in doc_ids_127
    assert "releases/version-skew-policy" in doc_ids_131


def test_retriever_targeted_version_search():
    """Verify retriever searches only targeted version when requested."""
    retriever = ChromaDenseRetriever()
    results_127 = retriever.retrieve("kubelet version skew policy", version="1.27", top_k=4)
    assert all(c.metadata.version == "1.27" for c, _ in results_127)

    results_131 = retriever.retrieve("kubelet version skew policy", version="1.31", top_k=4)
    assert all(c.metadata.version == "1.31" for c, _ in results_131)


def test_healthz_endpoint(client):
    """Verify /healthz returns 200 with valid HealthResponse schema."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.json()
    validated = HealthResponse.model_validate(data)
    assert validated.status == "ok"
    assert validated.index_ready is True


def test_ask_valid_query(client):
    """Verify /ask returns 200 with exact AskResponse schema and retrieved chunk IDs."""
    payload = {"question": "What is the version skew policy for kubelet?", "top_k": 3}
    resp = client.post("/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    validated = AskResponse.model_validate(data)
    assert set(data.keys()) == {"answer", "refused", "citations", "retrieved_chunk_ids", "latency_ms"}
    assert validated.refused is False
    assert len(validated.retrieved_chunk_ids) > 0


def test_ask_edge_case_empty_and_whitespace(client):
    """Verify empty and whitespace queries return HTTP 200 refusal without crashing."""
    for empty_val in ["", "   ", "\n\t  "]:
        resp = client.post("/ask", json={"question": empty_val})
        assert resp.status_code == 200
        data = resp.json()
        validated = AskResponse.model_validate(data)
        assert validated.refused is True
        assert validated.citations == []
        assert "empty" in validated.answer.lower()


def test_ask_edge_case_long_question(client):
    """Verify 4000+ char question is handled safely without crashing."""
    long_q = "What is a Pod in Kubernetes? " + ("word " * 1000)
    assert len(long_q) > 4000
    resp = client.post("/ask", json={"question": long_q, "top_k": 2})
    assert resp.status_code == 200
    data = resp.json()
    validated = AskResponse.model_validate(data)
    assert len(validated.retrieved_chunk_ids) > 0


def test_ask_edge_case_non_english(client):
    """Verify non-English questions return HTTP 200 refusal."""
    # Hindi
    resp_hi = client.post("/ask", json={"question": "कुबेरनेट्स क्या है?"})
    assert resp_hi.status_code == 200
    data_hi = resp_hi.json()
    val_hi = AskResponse.model_validate(data_hi)
    assert val_hi.refused is True
    assert val_hi.citations == []

    # French
    resp_fr = client.post("/ask", json={"question": "Qu'est-ce qu'un pod dans Kubernetes?"})
    assert resp_fr.status_code == 200
    data_fr = resp_fr.json()
    val_fr = AskResponse.model_validate(data_fr)
    assert val_fr.refused is True


def test_ask_technical_english_queries_not_refused(client):
    """Verify short technical English questions are NOT refused as non-English."""
    queries = [
        "kubectl get pods",
        "What is a Pod?",
        "kube-proxy iptables mode",
    ]
    for q in queries:
        resp = client.post("/ask", json={"question": q, "top_k": 3})
        assert resp.status_code == 200
        val = AskResponse.model_validate(resp.json())
        # Should not be refused for language reasons
        if val.refused:
            assert "non-english" not in val.answer.lower()
        assert len(val.retrieved_chunk_ids) > 0


def test_ask_edge_case_bad_top_k(client):
    """Verify bad top_k values (-1, 999) are safely clamped without error."""
    for bad_k in [-1, 0, 999]:
        resp = client.post("/ask", json={"question": "What is a Deployment?", "top_k": bad_k})
        assert resp.status_code == 200
        validated = AskResponse.model_validate(resp.json())
        assert validated.refused is False
        assert 1 <= len(validated.retrieved_chunk_ids) <= 40


def test_ask_edge_case_malformed_json_and_missing_fields(client):
    """Verify malformed JSON and missing fields return HTTP 200 with refusal schema."""
    # Malformed JSON string
    resp_raw = client.post("/ask", content="not valid json {", headers={"Content-Type": "application/json"})
    assert resp_raw.status_code == 200
    val_raw = AskResponse.model_validate(resp_raw.json())
    assert val_raw.refused is True

    # Missing question field
    resp_missing = client.post("/ask", json={"top_k": 5})
    assert resp_missing.status_code == 200
    val_missing = AskResponse.model_validate(resp_missing.json())
    assert val_missing.refused is True
