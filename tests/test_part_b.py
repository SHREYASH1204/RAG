"""Unit tests for Part B: Evaluation infrastructure (validator, stratified split, and eval runner)."""

import json
from pathlib import Path
import pytest

from scripts.validate_eval_set import validate_eval_set
from scripts.generate_split import create_stratified_split
from app.eval import run_evaluation, verify_citation_independently, percentile
from app.llm import BaseLLMClient
from app.schemas import Chunk, ChunkMetadata


def test_validate_eval_set_catches_violations(tmp_path):
    """Test that validate_eval_set detects duplicate qids, invalid types, missing gold_docs in version_conflict, and low counts."""
    # Create invalid question set
    invalid_lines = [
        {"qid": "q1", "question": "What is a Pod?", "type": "factual"},
        {"qid": "q1", "question": "Duplicate qid", "type": "factual"},
        {"qid": "q2", "question": "Invalid type question", "type": ""},
        {"qid": "q3", "question": "Version conflict without gold docs", "type": "version_conflict", "gold_docs": []},
        {"qid": "q4", "question": "Version conflict with non-existent doc", "type": "version_conflict", "gold_docs": ["nonexistent/doc"]},
    ]
    test_file = tmp_path / "test_invalid.jsonl"
    with open(test_file, "w", encoding="utf-8") as f:
        for item in invalid_lines:
            f.write(json.dumps(item) + "\n")

    # Run without smoke (checks minimums + schemas)
    errors = validate_eval_set(test_file, smoke=False)
    err_text = " ".join(errors)

    assert "Duplicate qid 'q1'" in err_text
    assert "'type' must be a non-empty string" in err_text
    assert "non-empty 'gold_docs'" in err_text
    assert "missing in corpus version" in err_text
    assert "Set count violation" in err_text


def test_validate_eval_set_smoke_flag_bypasses_counts(tmp_path):
    """Test that --smoke bypasses count minimums on valid questions."""
    valid_lines = [
        {"qid": "vconf-test", "question": "Version skew?", "type": "version_conflict", "gold_docs": ["releases/version-skew-policy"]},
        {"qid": "fact-test", "question": "What is a Pod?", "type": "factual", "gold_docs": ["concepts/workloads/pods/_index"]},
    ]
    test_file = tmp_path / "test_smoke.jsonl"
    with open(test_file, "w", encoding="utf-8") as f:
        for item in valid_lines:
            f.write(json.dumps(item) + "\n")

    errors = validate_eval_set(test_file, smoke=True)
    assert len(errors) == 0


def test_stratified_split_proportions(tmp_path):
    """Test that create_stratified_split creates 60/40 proportions per type."""
    items = []
    types = ["factual", "version_conflict", "unanswerable", "false_premise"]
    for t in types:
        for i in range(10):
            items.append({"qid": f"{t}-{i}", "question": f"Question {i}", "type": t})

    input_file = tmp_path / "all_questions.jsonl"
    with open(input_file, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it) + "\n")

    split_res = create_stratified_split(input_file, seed=42, dev_ratio=0.6)
    dev_qids = split_res["dev"]
    test_qids = split_res["test"]

    assert len(dev_qids) == 24  # 4 types * 6 = 24
    assert len(test_qids) == 16  # 4 types * 4 = 16
    assert set(dev_qids).isdisjoint(set(test_qids))

    # Verify per-type 6/4 breakdown
    dev_items = split_res["dev_items"]
    test_items = split_res["test_items"]
    for t in types:
        dev_count = sum(1 for x in dev_items if x["type"] == t)
        test_count = sum(1 for x in test_items if x["type"] == t)
        assert dev_count == 6
        assert test_count == 4


def test_independent_citation_verification():
    """Verify that verify_citation_independently checks chunk existence, quote verbatim match, doc_id and version."""
    chunk = Chunk(
        metadata=ChunkMetadata(
            doc_id="concepts/overview",
            version="1.31",
            chunk_id="v1.31:concepts/overview#c1",
            title="Overview",
            heading_path="Overview",
            ordinal=1,
            source_path="content/en/docs/concepts/overview.md",
        ),
        text="Kubernetes is an open-source system for automating deployment.",
        embedded_text="Kubernetes is an open-source system for automating deployment.",
    )
    chunks_map = {chunk.metadata.chunk_id: chunk}

    # 1. Valid citation
    cit_valid = {
        "chunk_id": "v1.31:concepts/overview#c1",
        "doc_id": "concepts/overview",
        "version": "1.31",
        "quote": "Kubernetes is an open-source system for automating deployment.",
    }
    is_v, err = verify_citation_independently(cit_valid, chunks_map)
    assert is_v is True
    assert err is None

    # 2. Quote mismatch
    cit_bad_quote = dict(cit_valid, quote="Kubernetes is a closed-source proprietary tool.")
    is_v, err = verify_citation_independently(cit_bad_quote, chunks_map)
    assert is_v is False
    assert "quote does not match" in err

    # 3. Version mismatch
    cit_bad_v = dict(cit_valid, version="1.27")
    is_v, err = verify_citation_independently(cit_bad_v, chunks_map)
    assert is_v is False
    assert "version mismatch" in err


def test_eval_runner_synthetic_run(tmp_path):
    """Test that run_evaluation computes Recall@k, MRR, citation validity, and per-type accuracy on synthetic questions."""
    q_data = [
        {
            "qid": "eval-fact-1",
            "question": "What is a Pod in Kubernetes?",
            "type": "factual",
            "gold_docs": ["concepts/workloads/pods/_index"],
        },
        {
            "qid": "eval-unans-1",
            "question": "What is the stock price of Apple in 1990?",
            "type": "unanswerable",
            "gold_docs": [],
        },
    ]
    eval_file = tmp_path / "synthetic_eval.jsonl"
    with open(eval_file, "w", encoding="utf-8") as f:
        for it in q_data:
            f.write(json.dumps(it) + "\n")

    class SyntheticFakeModel(BaseLLMClient):
        def generate(self, prompt: str, system: str = None) -> str:
            if "Apple" in prompt:
                return json.dumps({
                    "answer": "Stock prices are not documented in Kubernetes documentation.",
                    "supported": False,
                })
            return json.dumps({
                "answer": "A Pod is the smallest deployable unit of computing that you can create and manage in Kubernetes [v1.27:concepts/workloads/pods/_index#c0].",
                "supported": True,
            })

    report_file = tmp_path / "report.json"
    report = run_evaluation(
        eval_set_path=eval_file,
        out_path=report_file,
        top_k=3,
        llm_client=SyntheticFakeModel(),
    )

    assert report_file.exists()
    metrics = report["metrics"]
    assert metrics["retrieval"]["recall@5_pct"] == 100.0
    assert metrics["retrieval"]["mrr"] > 0.0
    assert "factual" in metrics["accuracy_per_type"]
    assert "unanswerable" in metrics["accuracy_per_type"]
    assert metrics["citation_verification_rate_pct"] == 100.0


def test_identifier_plural_singular_and_case_insensitive():
    """Unit test for Bug 1: Identifier matching must be plural/singular and case-insensitive."""
    from app.retrieval import get_identifier_variants, ChromaDenseRetriever

    # 1. Test get_identifier_variants
    v_pdb = get_identifier_variants("PodDisruptionBudgets")
    assert "poddisruptionbudget" in v_pdb
    assert "poddisruptionbudgets" in v_pdb

    v_policy = get_identifier_variants("UnhealthyPodEvictionPolicy")
    assert "unhealthypodevictionpolicy" in v_policy
    assert "unhealthypodevictionpolicies" in v_policy

    # 2. Test chunk relevance matching
    chunk = Chunk(
        metadata=ChunkMetadata(
            doc_id="tasks/run-application/configure-pdb",
            version="1.31",
            chunk_id="v1.31:tasks/run-application/configure-pdb#c10",
            title="Configure PodDisruptionBudget",
            heading_path="Unhealthy Pod Eviction Policy",
            ordinal=10,
            source_path="content/en/docs/tasks/run-application/configure-pdb.md",
        ),
        text=(
            "The UnhealthyPodEvictionPolicy field allows you to specify when unhealthy pods "
            "are considered for eviction under a PodDisruptionBudget (PDB)."
        ),
        embedded_text="...",
    )

    retriever = ChromaDenseRetriever()
    question = "What is the feature state of the UnhealthyPodEvictionPolicy for PodDisruptionBudgets?"
    cov, missing_terms, all_identifiers_present = retriever.compute_chunk_relevance(question, chunk)

    assert all_identifiers_present is True, f"Expected identifiers to be present, but got missing: {missing_terms}"
    assert "PodDisruptionBudgets" not in missing_terms
    assert "UnhealthyPodEvictionPolicy" not in missing_terms
    assert cov >= 0.40


def test_fenced_code_block_attribution_liveness_probe():
    """Unit test for Bug 2: Fenced code blocks in answer are preserved, attributed to matching chunk, and use code lines as verbatim quotes."""
    from app.llm import enforce_citations

    chunk_yaml = (
        "Another kind of liveness probe uses an HTTP GET request. Here is the configuration file:\n\n"
        "```yaml\n"
        "apiVersion: v1\n"
        "kind: Pod\n"
        "metadata:\n"
        "  labels:\n"
        "    test: liveness\n"
        "  name: liveness-http\n"
        "spec:\n"
        "  containers:\n"
        "  - name: liveness\n"
        "    image: registry.k8s.io/liveness:2.40\n"
        "    args:\n"
        "    - /server\n"
        "    livenessProbe:\n"
        "      httpGet:\n"
        "        path: /healthz\n"
        "        port: 8080\n"
        "      initialDelaySeconds: 3\n"
        "      periodSeconds: 3\n"
        "```"
    )
    chunk = Chunk(
        metadata=ChunkMetadata(
            doc_id="tasks/configure-pod-container/configure-liveness-readiness-startup-probes",
            version="1.31",
            chunk_id="v1.31:tasks/configure-pod-container/configure-liveness-readiness-startup-probes#c3",
            title="Configure Liveness, Readiness and Startup Probes",
            heading_path="Define an HTTP liveness probe",
            ordinal=3,
            source_path="content/en/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes.md",
        ),
        text=chunk_yaml,
        embedded_text="...",
    )

    answer_with_code = (
        "To configure an HTTP liveness probe for a container, you can use the following configuration:\n\n"
        "```yaml\n"
        "apiVersion: v1\n"
        "kind: Pod\n"
        "metadata:\n"
        "  name: liveness-http\n"
        "spec:\n"
        "  containers:\n"
        "  - name: liveness\n"
        "    image: registry.k8s.io/liveness:2.40\n"
        "    livenessProbe:\n"
        "      httpGet:\n"
        "        path: /healthz\n"
        "        port: 8080\n"
        "```"
    )

    clean_answer, citations, is_supported = enforce_citations(
        raw_answer=answer_with_code,
        retrieved_chunks_or_raw_citations=[chunk],
    )

    assert is_supported is True
    assert len(citations) >= 1
    # Check that code block is preserved intact
    assert "```yaml" in clean_answer
    assert "livenessProbe:" in clean_answer
    assert "httpGet:" in clean_answer
    # Check that code block citation quote is a verbatim substring of chunk.text
    code_cits = [c for c in citations if "apiVersion" in c.quote or "livenessProbe" in c.quote]
    assert len(code_cits) >= 1
    cit = code_cits[0]
    assert cit.chunk_id == chunk.metadata.chunk_id
    assert cit.quote in chunk.text
    assert len(cit.quote) <= 300
    assert "livenessProbe" in cit.quote or "httpGet" in cit.quote


def test_version_aware_attribution_sentence_127_never_cites_131():
    """Unit test for Fix 1: a sentence about 1.27 must never cite a v1.31 chunk."""
    from app.llm import enforce_citations

    chunk_127 = Chunk(
        metadata=ChunkMetadata(
            doc_id="releases/version-skew-policy",
            version="1.27",
            chunk_id="v1.27:releases/version-skew-policy#c3",
            title="Skew Policy",
            heading_path="Kubelet",
            ordinal=3,
            source_path="content/en/docs/releases/version-skew-policy.md",
        ),
        text="kubelet may be up to two minor versions older than kube-apiserver.",
        embedded_text="...",
    )
    chunk_131 = Chunk(
        metadata=ChunkMetadata(
            doc_id="releases/version-skew-policy",
            version="1.31",
            chunk_id="v1.31:releases/version-skew-policy#c3",
            title="Skew Policy",
            heading_path="Kubelet",
            ordinal=3,
            source_path="content/en/docs/releases/version-skew-policy.md",
        ),
        text="kubelet may be up to three minor versions older than kube-apiserver.",
        embedded_text="...",
    )

    # Answer where 1.27 sentence mistakenly cites v1.31 chunk
    answer = (
        "In Kubernetes 1.27, kubelet may be up to two minor versions older than kube-apiserver [v1.31:releases/version-skew-policy#c3]. "
        "In Kubernetes 1.31, kubelet may be up to three minor versions older than kube-apiserver [v1.31:releases/version-skew-policy#c3]."
    )

    clean_ans, citations, is_supported = enforce_citations(
        raw_answer=answer,
        retrieved_chunks_or_raw_citations=[chunk_131, chunk_127],
    )

    assert is_supported is True
    # Verify that the 1.27 sentence does NOT cite chunk_131
    for sent in clean_ans.split(". "):
        if "1.27" in sent:
            assert "v1.31:" not in sent, f"Sentence about 1.27 cited a 1.31 chunk: {sent}"
            assert "v1.27:releases/version-skew-policy#c3" in sent

    # When only 1.31 chunk is retrieved, the 1.27 sentence must be pruned
    clean_ans_pruned, citations_pruned, is_sup_pruned = enforce_citations(
        raw_answer="In Kubernetes 1.27, kubelet may be up to two minor versions older than kube-apiserver.",
        retrieved_chunks_or_raw_citations=[chunk_131],
    )
    assert "In Kubernetes 1.27" not in clean_ans_pruned


def test_non_answer_rule_refuses_when_documentation_does_not_specify():
    """Unit test for Fix 2: one non-answer case that refuses, and one normal answer with 'does not' that must NOT refuse."""
    from app.api import find_non_answer_sentence

    # Case A: Non-answer case saying documentation/Kubernetes does not specify/recommend/provide -> MUST REFUSE
    non_answer = "Kubernetes does not recommend a specific Linux distribution for control plane nodes [v1.31:concepts/architecture/_index#c18]."
    stmt = find_non_answer_sentence(non_answer)
    assert stmt is not None
    assert "does not recommend" in stmt

    non_answer_2 = "The documentation does not specify the maximum number of custom profiles."
    stmt_2 = find_non_answer_sentence(non_answer_2)
    assert stmt_2 is not None
    assert "does not specify" in stmt_2

    # Case B: Normal answer containing 'does not' about a feature's behavior -> MUST NOT REFUSE
    normal_answer_1 = "The kubelet does not restart pods that exit successfully."
    assert find_non_answer_sentence(normal_answer_1) is None

    normal_answer_2 = "A Deployment does not trigger a rollout when scaled."
    assert find_non_answer_sentence(normal_answer_2) is None

    normal_answer_3 = "Kubernetes does not restart containers in Completed state automatically."
    assert find_non_answer_sentence(normal_answer_3) is None


def test_ollama_retry_on_500_followed_by_success():
    """Test OllamaClient retries on HTTP 500 error up to 2 times and succeeds."""
    from unittest.mock import patch, MagicMock
    import httpx
    from app.llm import OllamaClient

    llm = OllamaClient()

    # Mock 1: 500 Server Error
    mock_resp_500 = MagicMock()
    mock_resp_500.status_code = 500
    mock_resp_500.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server error '500 Internal Server Error'",
        request=MagicMock(),
        response=mock_resp_500,
    )

    # Mock 2: 200 OK with response payload
    mock_resp_200 = MagicMock()
    mock_resp_200.status_code = 200
    mock_resp_200.json.return_value = {"response": '{"answer": "Recovered successfully [chunk_id]", "supported": true}'}

    with patch("httpx.Client.post", side_effect=[mock_resp_500, mock_resp_200]) as mock_post:
        result = llm.generate(prompt="What is Kubernetes?")
        assert 'Recovered successfully' in result
        assert mock_post.call_count == 2


def test_marker_cleanup_preserves_alpha_beta_stable_and_drops_short_sentences():
    """Unit test for Item 1:
    - Marker cleanup removes ONLY chunk-shaped markers: [v1.31:path#cN], [chunk_id N], [kubernetes 1.27], bare [1.27].
    - Other bracketed text such as [alpha], [beta], [stable] must survive.
    - After cleanup no bracket marker may remain unless it is a chunk_id present in citations[].
    - Drop sentences that are only a version prefix or have fewer than 4 words left.
    """
    from app.llm import strip_chunk_markers, enforce_citations
    from app.schemas import Chunk, ChunkMetadata

    # 1. strip_chunk_markers unit test
    raw = "In 1.27, [kubernetes 1.27] [1.27] the feature [alpha] is beta [chunk_id 1] [v1.27:foo#c1] [stable]."
    stripped = strip_chunk_markers(raw)
    assert "[alpha]" in stripped
    assert "[stable]" in stripped
    assert "[kubernetes 1.27]" not in stripped
    assert "[1.27]" not in stripped
    assert "[chunk_id 1]" not in stripped
    assert "[v1.27:foo#c1]" not in stripped

    # 2. enforce_citations unit test with brackets, version prefix sentence, and short sentence
    chunk_127 = Chunk(
        metadata=ChunkMetadata(
            chunk_id="v1.27:concepts/workloads#c1",
            doc_id="concepts/workloads",
            version="1.27",
            heading_path="Workloads > Pods",
            section="Pods Overview",
            tokens=50,
            has_code=False,
            has_table=False,
            char_len=200,
            title="Workloads",
            ordinal=1,
            source_path="content/en/docs/concepts/workloads.md",
        ),
        text="In Kubernetes 1.27, Pod scheduling readiness is an alpha feature supporting gating mechanism for Pods.",
        embedded_text="In Kubernetes 1.27, Pod scheduling readiness is an alpha feature supporting gating mechanism for Pods.",
    )

    answer_text = (
        "In Kubernetes 1.27,\n"  # Only a version prefix -> must be dropped
        "Pods exist.\n"          # Fewer than 4 words -> must be dropped
        "In Kubernetes 1.27, Pod scheduling readiness is [alpha] and supported with gates [chunk_id 1] [kubernetes 1.27] [1.27] [unverified#c9]."
    )

    clean_ans, citations, is_supported = enforce_citations(
        raw_answer=answer_text,
        retrieved_chunks_or_raw_citations=[chunk_127],
    )

    assert is_supported is True
    # Verify [alpha] survived
    assert "[alpha]" in clean_ans
    # Verify junk markers were removed
    assert "[chunk_id 1]" not in clean_ans
    assert "[kubernetes 1.27]" not in clean_ans
    assert "[1.27]" not in clean_ans
    assert "[unverified#c9]" not in clean_ans
    # Verify valid citation is present
    assert "[v1.27:concepts/workloads#c1]" in clean_ans
    # Verify citations[] contains the cited chunk
    assert len(citations) == 1
    assert citations[0].chunk_id == "v1.27:concepts/workloads#c1"
    # Verify version prefix and short sentence were dropped
    assert "In Kubernetes 1.27,\n" not in clean_ans
    assert "Pods exist" not in clean_ans





