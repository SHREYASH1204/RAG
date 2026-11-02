"""Phase 1 unit and integration tests: skeleton, config, schemas, fetch_corpus, and MANIFEST."""

import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.schemas import (
    AskRequest,
    AskResponse,
    Citation,
    ChunkMetadata,
    CorpusManifest,
    HealthResponse,
)
from scripts.fetch_corpus import extract_body


def compute_doc_id(rel_path: str) -> str:
    """Exact version-independent doc_id mapping rule."""
    normalized = rel_path.replace("\\", "/")
    if normalized.endswith(".md"):
        return normalized[:-3]
    return normalized


def test_config_defaults():
    """Verify default configurations adhere to assignment constraints."""
    cfg = Settings()
    assert cfg.PORT == 8080
    assert cfg.HOST == "0.0.0.0"
    assert cfg.OLLAMA_HOST == "http://localhost:11434"
    assert cfg.LLM_MODEL in ("qwen2.5:3b", "llama3.1:8b")
    assert cfg.EMBED_MODEL == "BAAI/bge-small-en-v1.5"
    assert cfg.INDEX_DIR == "index"
    assert cfg.CHUNKS_PATH == "index/chunks.jsonl"
    assert cfg.CORPUS_DIR == "corpus"
    assert cfg.TOP_K_DEFAULT == 5
    assert cfg.THRESHOLD_MIN == 0.45


def test_config_env_override(monkeypatch):
    """Verify settings respect environment variables without hardcoded paths."""
    monkeypatch.setenv("PORT", "9090")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("THRESHOLD_MIN", "0.55")

    cfg = Settings()
    assert cfg.PORT == 9090
    assert cfg.LLM_MODEL == "qwen2.5:7b"
    assert cfg.THRESHOLD_MIN == 0.55


def test_ask_request_validation():
    """Verify AskRequest validation and version normalization."""
    # Valid default
    req = AskRequest(question="What is a Pod?")
    assert req.top_k == 5
    assert req.version is None

    # Version normalization
    req2 = AskRequest(question="What is a Pod?", version="v1.31")
    assert req2.version == "1.31"

    req3 = AskRequest(question="What is a Pod?", version="1.27")
    assert req3.version == "1.27"

    # Invalid version
    with pytest.raises(ValidationError):
        AskRequest(question="What is a Pod?", version="v1.20")

    # top_k boundaries
    with pytest.raises(ValidationError):
        AskRequest(question="What is a Pod?", top_k=0)

    with pytest.raises(ValidationError):
        AskRequest(question="What is a Pod?", top_k=25)


def test_ask_response_schema():
    """Verify AskResponse matches exact required contract."""
    # Normal response with citation
    resp = AskResponse(
        answer="A Pod is the smallest execution unit in Kubernetes [v1.31:concepts/workloads/pods/pod-overview#c0].",
        refused=False,
        citations=[
            Citation(
                doc_id="concepts/workloads/pods/pod-overview",
                chunk_id="v1.31:concepts/workloads/pods/pod-overview#c0",
                version="1.31",
                quote="Pods are the smallest deployable units of computing that you can create and manage in Kubernetes.",
            )
        ],
        retrieved_chunk_ids=["v1.31:concepts/workloads/pods/pod-overview#c0"],
        latency_ms=142,
    )
    data = resp.model_dump()
    assert set(data.keys()) == {
        "answer",
        "refused",
        "citations",
        "retrieved_chunk_ids",
        "latency_ms",
    }
    assert resp.refused is False
    assert len(resp.citations) == 1

    # Refusal response
    refusal = AskResponse(
        answer="The documentation does not state the maximum pod count for non-standard clusters.",
        refused=True,
        citations=[],
        retrieved_chunk_ids=["v1.27:concepts/overview#c0"],
        latency_ms=45,
    )
    assert refusal.refused is True
    assert refusal.citations == []


def test_manifest_and_corpus_integrity():
    """Verify corpus files and manifest consistency."""
    manifest_path = Path("corpus/MANIFEST.json")
    assert manifest_path.exists(), "corpus/MANIFEST.json must exist"

    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = CorpusManifest.model_validate(raw_manifest)

    assert "1.27" in manifest.versions
    assert "1.31" in manifest.versions

    for version, vinfo in manifest.versions.items():
        assert 150 <= vinfo.page_count <= 400, f"Page count {vinfo.page_count} out of 150-400 bounds"
        assert len(vinfo.included_paths) == vinfo.page_count
        assert vinfo.commit_sha != ""
        assert vinfo.branch in ("release-1.27", "release-1.31")

        # Verify deterministic sorted paths
        assert vinfo.included_paths == sorted(vinfo.included_paths)

        # Spot-check that files exist on disk and meet character criteria
        target_dir = Path("corpus") / f"v{version}"
        assert target_dir.exists()

        for rel_path in vinfo.included_paths[:10]:
            file_path = target_dir / rel_path
            assert file_path.exists(), f"File {file_path} missing from corpus"
            content = file_path.read_text(encoding="utf-8")
            body = extract_body(content)
            assert len(body) >= 300, f"Body in {file_path} shorter than 300 chars"


def test_releases_and_version_skew_policy_present():
    """Verify that releases subtree and version-skew-policy.md exist in both versions."""
    for version in ("1.27", "1.31"):
        skew_file = Path("corpus") / f"v{version}" / "releases" / "version-skew-policy.md"
        assert skew_file.exists(), f"{skew_file} must exist in corpus"
        content = skew_file.read_text(encoding="utf-8")
        assert len(extract_body(content)) >= 300


def test_doc_id_computation():
    """Verify version-independent doc_id mapping rule."""
    docs_examples = [
        ("concepts/overview/_index.md", "concepts/overview/_index"),
        ("concepts/architecture/nodes.md", "concepts/architecture/nodes"),
        ("concepts/workloads/pods/pod-overview.md", "concepts/workloads/pods/pod-overview"),
        ("tasks/tools/install-kubectl-linux.md", "tasks/tools/install-kubectl-linux"),
        ("tasks/run-application/run-stateless-application-deployment.md", "tasks/run-application/run-stateless-application-deployment"),
    ]
    releases_examples = [
        ("releases/version-skew-policy.md", "releases/version-skew-policy"),
        ("releases/download.md", "releases/download"),
        ("releases/patch-releases.md", "releases/patch-releases"),
        ("releases/release-managers.md", "releases/release-managers"),
        ("releases/_index.md", "releases/_index"),
    ]

    for rel_path, expected in docs_examples + releases_examples:
        assert compute_doc_id(rel_path) == expected


def test_extract_body_strips_hugo_front_matter():
    """Test Hugo front matter stripping logic."""
    raw = """---
title: Test Title
weight: 10
---
This is the body content of the markdown file.
"""
    assert extract_body(raw) == "This is the body content of the markdown file."
