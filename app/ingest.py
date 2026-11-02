"""Deterministic ingestion pipeline for Kubernetes documentation.

Usage:
    python -m app.ingest [--rebuild]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set

import chromadb
from sentence_transformers import SentenceTransformer

from app.chunking import chunk_document
from app.config import get_settings
from app.schemas import Chunk


def load_doc_aliases(aliases_path: Path) -> Dict[str, str]:
    """Load doc_id alias mappings (e.g. 1.27 doc_id -> canonical 1.31 doc_id)."""
    if aliases_path.exists():
        try:
            raw = aliases_path.read_text(encoding="utf-8")
            return json.loads(raw)
        except Exception as e:
            print(f"Warning: Failed to parse {aliases_path} ({e}); continuing without aliases.", file=sys.stderr)
    return {}


def run_ingest(rebuild: bool = True) -> None:
    settings = get_settings()
    corpus_dir = Path(settings.CORPUS_DIR)
    index_dir = Path(settings.INDEX_DIR)
    chunks_file = Path(settings.CHUNKS_PATH)
    aliases_file = corpus_dir / "doc_aliases.json"

    print("=" * 60)
    print("STARTING DETERMINISTIC CORPUS INGESTION")
    print(f"Corpus directory: {corpus_dir}")
    print(f"Index directory:  {index_dir}")
    print(f"Chunks sidecar:   {chunks_file}")
    print(f"Embedding model:  {settings.EMBED_MODEL}")
    print(f"Rebuild mode:     {rebuild}")
    print("=" * 60)

    # 1. Load document aliases
    doc_aliases = load_doc_aliases(aliases_file)
    if doc_aliases:
        print(f"Loaded {len(doc_aliases)} document aliases from {aliases_file}:")
        for src, dst in doc_aliases.items():
            print(f"  - '{src}' -> '{dst}'")
    else:
        print(f"No document aliases active in {aliases_file}.")

    # 2. Reset index directory if rebuild is requested
    if rebuild:
        if index_dir.exists():
            print(f"Cleaning existing index directory at {index_dir} ...")
            shutil.rmtree(index_dir)
        index_dir.mkdir(parents=True, exist_ok=True)
    else:
        index_dir.mkdir(parents=True, exist_ok=True)

    # 3. Discover and chunk documents deterministically
    all_chunks: List[Chunk] = []
    chunk_ids_seen: Set[str] = set()
    docs_by_version: Dict[str, Set[str]] = {"1.27": set(), "1.31": set()}
    chunks_by_version: Dict[str, int] = {"1.27": 0, "1.31": 0}
    remapped_chunks: List[str] = []
    total_unresolved: Dict[str, Counter] = {"1.27": Counter(), "1.31": Counter()}

    for version in ("1.27", "1.31"):
        version_dir = corpus_dir / f"v{version}"
        if not version_dir.exists():
            print(f"Error: Version directory {version_dir} missing! Run make fetch first.", file=sys.stderr)
            sys.exit(1)

        # Deterministic lexicographical sorting of files
        md_files = sorted(
            [
                p for p in version_dir.rglob("*.md")
                if not any(x in p.as_posix() for x in ("includes", "glossary", "examples"))
            ],
            key=lambda p: p.as_posix(),
        )
        print(f"\nProcessing version {version} ({len(md_files)} files) ...")

        for file_path in md_files:
            chunks, unresolved, was_remapped = chunk_document(file_path, version, doc_aliases)
            if was_remapped:
                for c in chunks:
                    remapped_chunks.append(
                        f"Chunk {c.metadata.chunk_id} -> doc_id='{c.metadata.doc_id}' (source_path='{c.metadata.source_path}')"
                    )

            for sc_name, sc_count in unresolved.items():
                total_unresolved[version][sc_name] += sc_count

            for chunk in chunks:
                cid = chunk.metadata.chunk_id
                if cid in chunk_ids_seen:
                    raise ValueError(f"DUPLICATE chunk_id detected: {cid}! Chunk IDs must be strictly unique.")
                chunk_ids_seen.add(cid)
                all_chunks.append(chunk)
                docs_by_version[version].add(chunk.metadata.doc_id)
                chunks_by_version[version] += 1

    print(f"\nTotal chunks generated: {len(all_chunks)} across {len(chunk_ids_seen)} unique IDs.")

    # Print remapped chunks if any
    if remapped_chunks:
        print(f"\nRemapped Chunks via {aliases_file} ({len(remapped_chunks)} total):")
        for rc in remapped_chunks:
            print(f"  - {rc}")

    # 4. Write exact chunks JSONL sidecar
    chunks_file.parent.mkdir(parents=True, exist_ok=True)
    with chunks_file.open("w", encoding="utf-8") as fp:
        for chunk in all_chunks:
            row = {
                "chunk_id": chunk.metadata.chunk_id,
                "doc_id": chunk.metadata.doc_id,
                "version": chunk.metadata.version,
                "title": chunk.metadata.title,
                "heading_path": chunk.metadata.heading_path,
                "ordinal": chunk.metadata.ordinal,
                "source_path": chunk.metadata.source_path,
                "text": chunk.text,
                "embedded_text": chunk.embedded_text,
            }
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote exact raw chunk sidecar to {chunks_file} ({chunks_file.stat().st_size} bytes)")

    # 5. Initialize Chroma persistent client and embedding model
    print(f"\nInitializing embedding model ({settings.EMBED_MODEL}) ...")
    embed_model = SentenceTransformer(settings.EMBED_MODEL)

    chroma_dir = index_dir / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))

    # Recreate collection
    try:
        chroma_client.delete_collection("k8s_docs")
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name="k8s_docs",
        metadata={"hnsw:space": "cosine"},
    )

    # 6. Embed and ingest chunks in batches
    batch_size = 128
    print(f"Embedding and inserting {len(all_chunks)} chunks in batches of {batch_size} ...")

    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i : i + batch_size]
        texts_to_embed = [c.embedded_text for c in batch]
        embeddings = embed_model.encode(texts_to_embed, batch_size=batch_size, show_progress_bar=False, normalize_embeddings=True)

        ids = [c.metadata.chunk_id for c in batch]
        documents = [c.text for c in batch]
        metadatas = [
            {
                "doc_id": c.metadata.doc_id,
                "version": c.metadata.version,
                "chunk_id": c.metadata.chunk_id,
                "title": c.metadata.title,
                "heading_path": c.metadata.heading_path,
                "ordinal": c.metadata.ordinal,
                "source_path": c.metadata.source_path,
            }
            for c in batch
        ]

        collection.upsert(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=documents,
            metadatas=metadatas,
        )
        if (i // batch_size) % 5 == 0 or (i + batch_size >= len(all_chunks)):
            print(f"  Inserted {min(i + batch_size, len(all_chunks))}/{len(all_chunks)} chunks ...")

    # 7. Print ingestion statistics and unresolved shortcodes report
    docs_127 = docs_by_version["1.27"]
    docs_131 = docs_by_version["1.31"]
    common_docs = docs_127 & docs_131
    only_127 = docs_127 - docs_131
    only_131 = docs_131 - docs_127

    print("\n" + "=" * 60)
    print("INGESTION SUMMARY & STATISTICS")
    print("=" * 60)
    print("Chunks per version:")
    print(f"  - v1.27: {chunks_by_version['1.27']} chunks")
    print(f"  - v1.31: {chunks_by_version['1.31']} chunks")
    print(f"  - Total: {len(all_chunks)} chunks")
    print("\nDocs per version:")
    print(f"  - v1.27: {len(docs_127)} docs")
    print(f"  - v1.31: {len(docs_131)} docs")
    print(f"  - In both versions: {len(common_docs)} docs")
    print(f"  - Only in v1.27:   {len(only_127)} docs")
    print(f"  - Only in v1.31:   {len(only_131)} docs")

    print(f"\nRemapped chunks (via {aliases_file}): {len(remapped_chunks)}")

    print("\nUnresolved Shortcode Report:")
    for v in ("1.27", "1.31"):
        unres = total_unresolved[v]
        if unres:
            print(f"  v{v} unresolved ({sum(unres.values())} total):")
            for name, count in unres.most_common():
                print(f"    - {name}: {count}")
        else:
            print(f"  v{v}: 0 unresolved shortcodes (100% resolved)")

    print("=" * 60)
    print("INGESTION COMPLETED SUCCESSFULLY")
    print("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Kubernetes documentation corpus into vector store.")
    parser.add_argument("--rebuild", action="store_true", default=True, help="Rebuild the index from scratch.")
    args = parser.parse_args()
    run_ingest(rebuild=args.rebuild)


if __name__ == "__main__":
    main()
