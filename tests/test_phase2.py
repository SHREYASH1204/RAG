"""Phase 2 unit and integration tests: shortcode resolution, chunking, and deterministic ingestion."""

import json
from pathlib import Path
import pytest

from app.chunking import chunk_document, strip_inline_markdown
from app.shortcodes import (
    resolve_feature_state,
    resolve_shortcodes_in_markdown,
    resolve_skew,
)


def test_resolve_skew():
    """Verify skew.html logic matches upstream Hugo behavior at the pinned commits."""
    # v1.27 tests (upstream skew.html strips 'v')
    assert resolve_skew("currentVersion", "1.27") == "1.27"
    assert resolve_skew("latestVersion", "1.27") == "1.31"
    assert resolve_skew("currentVersionAddMinor -1", "1.27") == "1.26"
    assert resolve_skew("currentVersionAddMinor -2", "1.27") == "1.25"
    assert resolve_skew("prevMinorVersion", "1.27") == "1.26"
    assert resolve_skew("oldestMinorVersion", "1.27") == "1.25"

    # v1.31 tests
    assert resolve_skew("currentVersion", "1.31") == "1.31"
    assert resolve_skew("latestVersion", "1.31") == "1.35"
    assert resolve_skew("currentVersionAddMinor -1", "1.31") == "1.30"
    assert resolve_skew("currentVersionAddMinor -2", "1.31") == "1.29"
    assert resolve_skew("currentVersionAddMinor -3", "1.31") == "1.28"


def test_resolve_feature_state():
    """Verify feature-state.html logic for both version and gate forms."""
    # Version form
    res, ok = resolve_feature_state('for_k8s_version="v1.24" state="stable"', "1.27")
    assert ok is True
    assert res == "FEATURE STATE: Kubernetes v1.24 [stable]"

    # Feature gate name form in 1.31
    res_gate, ok_gate = resolve_feature_state('feature_gate_name="ImageVolume"', "1.31")
    assert ok_gate is True
    assert res_gate == "FEATURE STATE: Kubernetes v1.31 [alpha]"

    # Bare state form (resolves with Page param version)
    res_bare, ok_bare = resolve_feature_state('state="stable"', "1.27")
    assert ok_bare is True
    assert res_bare == "FEATURE STATE: Kubernetes v1.27 [stable]"


def test_resolve_shortcodes_in_markdown():
    """Verify complete markdown shortcode resolution."""
    raw = (
        'Here is a {{< glossary_tooltip text="cluster node" term_id="node" >}}.\n'
        '{{< heading "whatsnext" >}}\n'
        "{{< note >}}\n"
        "This is a note with {{< param \"version\" >}}.\n"
        "{{< /note >}}\n"
        "{{< warning >}}\n"
        "Warning message.\n"
        "{{</ warning >}}\n"
    )
    resolved, unres = resolve_shortcodes_in_markdown(raw, "1.27")
    assert unres == {}
    assert "cluster node" in resolved
    assert "What's next" in resolved
    assert "Note: This is a note with v1.27." in resolved
    assert "Warning: Warning message." in resolved


def test_strip_inline_markdown_prose():
    """Verify inline markdown is stripped and whitespace is collapsed to single spaces."""
    raw = (
        "Here is `kubectl` running on **Linux** and *macOS*.\n"
        "See [documentation](https://kubernetes.io) for more.\n"
        "And `kubelet` is supported at **v1.27**."
    )
    cleaned = strip_inline_markdown(raw)
    assert cleaned == (
        "Here is kubectl running on Linux and macOS. "
        "See documentation for more. "
        "And kubelet is supported at v1.27."
    )


def test_strip_inline_markdown_preserves_code_and_tables():
    """Verify fenced code blocks and tables remain intact."""
    raw = (
        "Config file:\n"
        "```yaml\n"
        "apiVersion: v1\n"
        "kind: Pod\n"
        "```\n"
        "Table overview:\n"
        "| Component | Version |\n"
        "|---|---|\n"
        "| kubelet | 1.31 |\n"
        "End of section."
    )
    cleaned = strip_inline_markdown(raw)
    assert "```yaml" in cleaned
    assert "apiVersion: v1" in cleaned
    assert "| Component | Version |" in cleaned
    assert "| kubelet | 1.31 |" in cleaned


def test_skew_policy_kubelet_sentences_exist():
    """Verify ground truth skew policy kubelet sentence appears in stored chunks."""
    p_127 = Path("corpus/v1.27/releases/version-skew-policy.md")
    p_131 = Path("corpus/v1.31/releases/version-skew-policy.md")

    chunks_127, _, _ = chunk_document(p_127, "1.27")
    chunks_131, _, _ = chunk_document(p_131, "1.31")

    target_127 = "kubelet must not be newer than kube-apiserver, and may be up to two minor versions older."
    target_131 = "kubelet may be up to three minor versions older than kube-apiserver"

    assert any(target_127 in c.text for c in chunks_127), f"Expected sentence missing from 1.27 chunks: '{target_127}'"
    assert any(target_131 in c.text for c in chunks_131), f"Expected sentence missing from 1.31 chunks: '{target_131}'"


def test_doc_aliases_remapping_and_source_path():
    """Verify doc_aliases remaps doc_id and chunk_id while retaining original source_path."""
    p_127 = Path("corpus/v1.27/releases/version-skew-policy.md")
    aliases = {"releases/version-skew-policy": "releases/skew-canonical"}

    chunks, _, was_remapped = chunk_document(p_127, "1.27", doc_aliases=aliases)
    assert was_remapped is True
    assert len(chunks) > 0

    first = chunks[0]
    assert first.metadata.doc_id == "releases/skew-canonical"
    assert first.metadata.chunk_id.startswith("v1.27:releases/skew-canonical#c")
    assert first.metadata.source_path == p_127.as_posix()


def test_deterministic_chunking_reproducibility():
    """Verify chunking twice produces identical chunk_id sets and texts."""
    test_files = [
        ("1.27", Path("corpus/v1.27/releases/version-skew-policy.md")),
        ("1.31", Path("corpus/v1.31/releases/version-skew-policy.md")),
        ("1.27", Path("corpus/v1.27/concepts/overview/_index.md")),
        ("1.31", Path("corpus/v1.31/concepts/overview/_index.md")),
    ]

    for version, p in test_files:
        run1_chunks, _, _ = chunk_document(p, version)
        run2_chunks, _, _ = chunk_document(p, version)

        assert len(run1_chunks) == len(run2_chunks)
        for c1, c2 in zip(run1_chunks, run2_chunks):
            assert c1.metadata.chunk_id == c2.metadata.chunk_id
            assert c1.text == c2.text
            assert c1.embedded_text == c2.embedded_text
