"""Phase 4 / Step B and Step C unit tests: LLM parsing, citation enforcement, and refusal logic."""

import json
import re
from typing import Optional
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.api import app
from app.llm import (
    enforce_citations,
    parse_llm_json,
    repair_quote_to_sentence,
)
from app.retrieval import extract_identifier_tokens
from app.schemas import AskResponse, Chunk, ChunkMetadata


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def make_dummy_chunk(chunk_id: str, version: str, doc_id: str, text: str) -> Chunk:
    return Chunk(
        metadata=ChunkMetadata(
            doc_id=doc_id,
            version=version,
            chunk_id=chunk_id,
            title="Test Title",
            heading_path="Test > Heading",
            ordinal=0,
            source_path=f"corpus/{version}/{doc_id}.md",
        ),
        text=text,
        embedded_text=text,
    )


def test_parse_llm_json_clean_and_fenced():
    """Verify JSON parser strips code fences and handles raw JSON."""
    raw_dict = {"answer": "A pod is the smallest deployable unit.", "citations": [], "supported": True}
    raw_json = json.dumps(raw_dict)

    # 1. Direct JSON
    assert parse_llm_json(raw_json) == raw_dict

    # 2. Markdown fenced JSON
    fenced = f"```json\n{raw_json}\n```"
    assert parse_llm_json(fenced) == raw_dict

    # 3. Text with surrounding chatter
    surrounded = f"Here is your answer:\n```\n{raw_json}\n```\nHope this helps!"
    assert parse_llm_json(surrounded) == raw_dict

    # 4. Invalid JSON
    assert parse_llm_json("not valid json at all") is None


def test_repair_quote_to_sentence():
    """Verify 1-step repair maps slightly drifted quote to closest verbatim sentence."""
    chunk_text = (
        "Kubernetes pods are ephemeral by design. "
        "A kubelet may be up to two minor versions older than kube-apiserver. "
        "Controllers reconcile cluster state periodically."
    )

    # Exact match
    quote = "A kubelet may be up to two minor versions older than kube-apiserver."
    repaired = repair_quote_to_sentence(quote, chunk_text)
    assert repaired == quote

    # Slightly drifted quote (missing punctuation, lower case)
    drifted = "kubelet may be up to two minor versions older than kube apiserver"
    repaired = repair_quote_to_sentence(drifted, chunk_text)
    assert repaired == "A kubelet may be up to two minor versions older than kube-apiserver."

    # Completely unrelated quote -> None
    unrelated = "Docker containers run smoothly on Linux."
    assert repair_quote_to_sentence(unrelated, chunk_text) is None


def test_enforce_citations_happy_path():
    """Verify citations are verified, doc_id/version filled from metadata, and markers preserved."""
    chunk1 = make_dummy_chunk(
        chunk_id="chunk-1",
        version="1.27",
        doc_id="releases/version-skew-policy",
        text="In 1.27, kubelet may be up to two minor versions older than kube-apiserver.",
    )
    chunk2 = make_dummy_chunk(
        chunk_id="chunk-2",
        version="1.31",
        doc_id="releases/version-skew-policy",
        text="In 1.31, kubelet may be up to three minor versions older than kube-apiserver.",
    )

    raw_answer = (
        "In 1.27, kubelet supports two versions skew [chunk-1]. "
        "In 1.31, it supports three versions skew [chunk-2]."
    )
    raw_citations = [
        {"chunk_id": "chunk-1", "quote": "In 1.27, kubelet may be up to two minor versions older than kube-apiserver."},
        {"chunk_id": "chunk-2", "quote": "In 1.31, kubelet may be up to three minor versions older than kube-apiserver."},
    ]

    answer, citations, is_supported = enforce_citations(raw_answer, raw_citations, [chunk1, chunk2])
    assert is_supported is True
    assert len(citations) == 2
    assert citations[0].doc_id == "releases/version-skew-policy"
    assert citations[0].version == "1.27"
    assert citations[1].version == "1.31"
    assert "[chunk-1]" in answer
    assert "[chunk-2]" in answer


def test_enforce_citations_drops_hallucinated_and_unretrieved():
    """Verify hallucinated chunk_ids and sentences without valid citations are dropped."""
    chunk1 = make_dummy_chunk(
        chunk_id="chunk-1",
        version="1.27",
        doc_id="concepts/workloads/pods",
        text="Pods are the smallest deployable units of computing in Kubernetes.",
    )

    raw_answer = (
        "Pods are the smallest deployable units [chunk-1]. "
        "Pods can also fly into outer space [unretrieved-chunk]."
    )
    raw_citations = [
        {"chunk_id": "chunk-1", "quote": "Pods are the smallest deployable units of computing in Kubernetes."},
        {"chunk_id": "unretrieved-chunk", "quote": "Pods can also fly into outer space."},
    ]

    answer, citations, is_supported = enforce_citations(raw_answer, raw_citations, [chunk1])
    assert is_supported is True
    assert len(citations) == 1
    assert citations[0].chunk_id == "chunk-1"
    # Sentence with invalid marker is pruned
    assert "outer space" not in answer
    assert "[chunk-1]" in answer


def test_enforce_citations_refusal_when_no_valid_citations():
    """Verify refusal if all citations fail verification."""
    chunk1 = make_dummy_chunk(
        chunk_id="chunk-1",
        version="1.27",
        doc_id="concepts/workloads/pods",
        text="Pods run containers.",
    )

    raw_answer = "Kubernetes was created in the 19th century [chunk-1]."
    raw_citations = [
        {"chunk_id": "chunk-1", "quote": "Completely hallucinated quote not in text."}
    ]

    answer, citations, is_supported = enforce_citations(raw_answer, raw_citations, [chunk1])
    assert is_supported is False
    assert citations == []
    assert "sufficient verified citations" in answer.lower()


def test_false_premise_refusal_on_nonexistent_flag(client):
    """Verify question naming a nonexistent flag is refused with refused=True and citations=[]."""
    resp = client.post("/ask", json={"question": "How do I configure --nonexistent-hypothetical-flag-xyz in kubelet?"})
    assert resp.status_code == 200
    data = resp.json()
    validated = AskResponse.model_validate(data)
    assert validated.refused is True
    assert validated.citations == []
    assert "--nonexistent-hypothetical-flag-xyz" in validated.answer




def test_ollama_404_or_connection_error_preserves_retrieved_chunks(client):
    """Verify when Ollama returns 404 or connection error, /ask returns HTTP 200, exact 5-field schema,
    refused=True, citations=[], and retrieved_chunk_ids still lists the retrieved chunks."""
    for error_msg in [
        "Client error '404 Not Found' for url 'http://localhost:11434/api/generate'",
        "Connection refused to 11434",
    ]:
        with patch("app.api.get_llm_client") as mock_get:
            mock_client = MagicMock()
            mock_client.generate.side_effect = RuntimeError(error_msg)
            mock_get.return_value = mock_client

            resp = client.post("/ask", json={"question": "What is a Pod in Kubernetes?", "top_k": 3})
            assert resp.status_code == 200
            data = resp.json()
            # Exact 5-field schema
            assert set(data.keys()) == {"answer", "refused", "citations", "retrieved_chunk_ids", "latency_ms"}
            validated = AskResponse.model_validate(data)
            assert validated.refused is True
            assert validated.citations == []
            # retrieved_chunk_ids still lists the retrieved chunks
            assert len(validated.retrieved_chunk_ids) > 0
            assert any(cid.startswith("v1.") for cid in validated.retrieved_chunk_ids)
            assert "unavailable" in validated.answer.lower()


def test_false_premise_must_not_fire_on_legitimate_questions(client):
    """Verify false_premise does NOT fire on legitimate queries:
    - 'kubectl get pods'
    - 'What is a Pod?'
    - 'kube-proxy iptables mode'
    - 'How many minor versions may the kubelet lag behind kube-apiserver?'
    - enforce-mountable-secrets questions
    """
    legit_questions = [
        "kubectl get pods",
        "What is a Pod?",
        "kube-proxy iptables mode",
        "How many minor versions may the kubelet lag behind kube-apiserver?",
        "What does the kubernetes.io/enforce-mountable-secrets annotation do on a ServiceAccount?",
        "Which Secrets references must be listed in a ServiceAccount's secrets field when enforce-mountable-secrets is true?",
        "Does enforce-mountable-secrets also restrict Secrets used in projected volumes?",
    ]

    for q in legit_questions:
        resp = client.post("/ask", json={"question": q, "top_k": 3})
        assert resp.status_code == 200
        data = resp.json()
        assert resp.headers.get("X-Refusal-Reason") != "false_premise", f"Failed for question: {q}"
        if data.get("refused"):
            assert "false_premise" not in data.get("answer", "").lower()


def test_false_premise_fires_on_absent_identifiers(client):
    """Verify false_premise fires on absent identifiers and names version and missing term."""
    # 1. Annotation completely absent from corpus
    resp1 = client.post("/ask", json={"question": "How do I set the kubernetes.io/enforce-mountable-configmaps annotation?"})
    assert resp1.status_code == 200
    assert resp1.headers.get("X-Refusal-Reason") == "false_premise"
    data1 = resp1.json()
    assert data1["refused"] is True
    assert data1["citations"] == []
    assert "kubernetes.io/enforce-mountable-configmaps" in data1["answer"]
    assert "1.27 or 1.31" in data1["answer"]

    # 2. Annotation absent from pinned version 1.27
    resp2 = client.post("/ask", json={
        "question": "What does the kubernetes.io/enforce-mountable-secrets annotation do on a ServiceAccount?",
        "version": "1.27"
    })
    assert resp2.status_code == 200
    assert resp2.headers.get("X-Refusal-Reason") == "false_premise"
    data2 = resp2.json()
    assert data2["refused"] is True
    assert data2["citations"] == []
    assert "kubernetes.io/enforce-mountable-secrets" in data2["answer"]
    assert "1.27" in data2["answer"]


def test_sentence_no_marker_attributed_to_right_chunk():
    """Verify sentence with no marker is attributed to the right chunk."""
    chunk1 = make_dummy_chunk("c1", "1.27", "skew", "In 1.27, kubelet may be up to two minor versions older than kube-apiserver.")
    chunk2 = make_dummy_chunk("c2", "1.31", "pods", "Pods are the smallest deployable units of computing in Kubernetes.")

    raw_answer = "Pods are the smallest deployable units of computing in Kubernetes."
    ans, cits, supported = enforce_citations(raw_answer, [chunk1, chunk2])
    assert supported is True
    assert "[c2]" in ans
    assert len(cits) == 1
    assert cits[0].chunk_id == "c2"


def test_sentence_wrong_marker_repointed():
    """Verify sentence with a wrong marker is re-pointed to best chunk."""
    chunk1 = make_dummy_chunk("c1", "1.27", "skew", "In 1.27, kubelet may be up to two minor versions older than kube-apiserver.")
    chunk2 = make_dummy_chunk("c2", "1.31", "pods", "Pods are the smallest deployable units of computing in Kubernetes.")

    raw_answer = "Pods are the smallest deployable units of computing [c1]."
    ans, cits, supported = enforce_citations(raw_answer, [chunk1, chunk2])
    assert supported is True
    assert "[c2]" in ans
    assert "[c1]" not in ans
    assert len(cits) == 1
    assert cits[0].chunk_id == "c2"


def test_unsupported_sentence_projected_volumes_pruned():
    """Verify an unsupported sentence ('projected volumes' claim) is pruned."""
    chunk = make_dummy_chunk(
        "c-secrets",
        "1.31",
        "service-accounts",
        "Kubernetes provides an annotation called kubernetes.io/enforce-mountable-secrets that you can add to your ServiceAccounts. The name of each Secret that is mounted as a volume in a Pod must appear in the secrets field of the Pod's ServiceAccount."
    )

    raw_answer = "The enforce-mountable-secrets annotation restricts Secrets used in projected volumes."
    ans, cits, supported = enforce_citations(raw_answer, [chunk])
    assert supported is False
    assert cits == []


def test_markers_in_final_answer_match_citations():
    """Verify markers in the final answer match citations list."""
    chunk1 = make_dummy_chunk("c1", "1.27", "skew", "In 1.27, kubelet may be up to two minor versions older than kube-apiserver.")
    chunk2 = make_dummy_chunk("c2", "1.31", "pods", "Pods are the smallest deployable units of computing in Kubernetes.")

    raw_answer = "Pods are deployable units. In 1.27, kubelet may be two versions older."
    ans, cits, supported = enforce_citations(raw_answer, [chunk1, chunk2])
    assert supported is True
    assert len(cits) == 2
    import re
    markers = set(re.findall(r"\[([a-zA-Z0-9_\-\.:/#]+)\]", ans))
    cit_ids = {c.chunk_id for c in cits}
    assert markers == cit_ids


def test_identical_support_picks_earlier_chunk():
    """Verify two chunks with identical support pick the earlier one in prompt order."""
    chunk_a = make_dummy_chunk("chunk-a", "1.31", "sa", "Service accounts provide an identity for processes that run in a Pod.")
    chunk_b = make_dummy_chunk("chunk-b", "1.31", "sa", "Service accounts provide an identity for processes that run in a Pod.")

    raw_answer = "Service accounts provide identity for processes in a Pod."
    ans, cits, supported = enforce_citations(raw_answer, [chunk_a, chunk_b])
    assert supported is True
    assert "[chunk-a]" in ans
    assert "[chunk-b]" not in ans
    assert len(cits) == 1
    assert cits[0].chunk_id == "chunk-a"


def test_stemming_and_synonyms():
    """Verify light_stem handles common plural and derivational suffixes."""
    from app.retrieval import light_stem
    assert light_stem("restricts") == "restrict"
    assert light_stem("restriction") == "restrict"
    assert light_stem("restrictions") == "restrict"
    assert light_stem("restricted") == "restrict"
    assert light_stem("references") == "referenc"
    assert light_stem("referenced") == "referenc"
    assert light_stem("volumes") == "volum"
    assert light_stem("secrets") == "secret"


def test_generic_words_do_not_count():
    """Verify generic question words are excluded from content terms."""
    from app.retrieval import extract_question_relevance_terms
    q = "What is the maximum supported component upgrade order for kubelet relative to kube-apiserver in a cluster?"
    identifiers, content_stems = extract_question_relevance_terms(q)
    assert "kube-apiserver" in content_stems
    assert "kubelet" in content_stems
    assert "upgrade" in content_stems
    # Generic question words must be excluded
    for generic in ["maximum", "supported", "component", "order", "relative", "cluster", "what"]:
        assert generic not in content_stems


def test_heading_path_included_vconf006():
    """Verify heading path is checked in relevance and enables vconf-006 to achieve high coverage."""
    from app.retrieval import ChromaDenseRetriever
    retriever = ChromaDenseRetriever()
    q = "What is the supported component upgrade order for kubelet relative to kube-apiserver?"
    # Find chunk v1.27:releases/version-skew-policy#c10
    chunk = retriever.chunks_by_id.get("v1.27:releases/version-skew-policy#c10")
    if chunk:
        cov, missing, ids_present = retriever.compute_chunk_relevance(q, chunk)
        assert ids_present is True
        assert cov >= 0.5


def test_garbled_json_in_string_never_emitted():
    """Verify nested dictionary JSON in string is cleanly parsed into plain sentences."""
    raw = json.dumps({
        "answer": json.dumps({"v1.27": "kubelet up to two versions older.", "v1.31": "kubelet up to three versions older."}),
        "supported": True
    })
    parsed = parse_llm_json(raw)
    assert parsed is not None
    assert not parsed["answer"].startswith("{")
    assert "In Kubernetes 1.27" in parsed["answer"]
    assert "In Kubernetes 1.31" in parsed["answer"]


def test_irrelevant_evidence_refusal_when_identifier_missing_from_cited_chunk(client):
    """Verify request is refused with irrelevant_evidence when cited chunk lacks required question identifiers."""
    from app.api import set_llm_client
    from app.llm import BaseLLMClient

    class MissedIdModel(BaseLLMClient):
        def generate(self, prompt: str, system: Optional[str] = None) -> str:
            # Find the first chunk in prompt (which will be a kubelet version skew chunk)
            match = re.search(r"### Kubernetes (?:1\.27|1\.31) \| ([a-zA-Z0-9_\-\.:/#]+) \|", prompt)
            cid = match.group(1) if match else "unknown"
            return json.dumps({
                "answer": f"Kubelet version skew policy allows minor version differences [{cid}].",
                "supported": True
            })

    set_llm_client(MissedIdModel())
    # Question combines kubelet skew with the secrets annotation identifier.
    # The identifier exists in corpus (so false premise does not trigger), but kubelet skew chunks do not have it.
    resp = client.post("/ask", json={"question": "What is the version skew for kubelet with kubernetes.io/enforce-mountable-secrets?"})
    assert resp.status_code == 200
    assert resp.headers.get("X-Refusal-Reason") == "irrelevant_evidence"
    data = resp.json()
    assert data["refused"] is True
    assert data["citations"] == []
    assert "relevant evidence" in data["answer"].lower()



