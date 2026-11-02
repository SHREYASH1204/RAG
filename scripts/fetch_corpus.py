#!/usr/bin/env python3
"""Fetch and filter Kubernetes documentation corpus for versions 1.27 and 1.31.

Fetches markdown documentation directly from https://github.com/kubernetes/website:
  - content/en/docs/concepts/
  - content/en/docs/tasks/
  - content/en/releases/

Extracts markdown files, filters out stubs (<300 characters of body text excluding
Hugo front matter), saves them to corpus/v1.27/ and corpus/v1.31/, and generates
corpus/MANIFEST.json.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Pinned commit SHAs from kubernetes/website branches
DEFAULT_VERSIONS = {
    "1.27": {
        "branch": "release-1.27",
        "commit_sha": "f173f35615f0e87a49d963f28908cf25ebc538af",
    },
    "1.31": {
        "branch": "release-1.31",
        "commit_sha": "11f92a075a2a6b97448d8bb586ad7eac14871e04",
    },
}

REPO_URL = "https://github.com/kubernetes/website.git"
ARCHIVE_URL_TEMPLATE = "https://github.com/kubernetes/website/archive/{commit_sha}.tar.gz"
MIN_BODY_CHARS = 300
MAX_PAGES_PER_VERSION = 400


def extract_body(content: str) -> str:
    """Extract markdown body by stripping Hugo front matter delimited by ---."""
    stripped = content.strip()
    if stripped.startswith("---"):
        parts = stripped.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return stripped


def scan_source_directory(source_root: Path) -> List[Tuple[str, str]]:
    """Scan extracted kubernetes/website source directory for valid markdown pages.
    
    Returns a list of (target_rel_path, file_content) pairs where:
      - content/en/docs/concepts/ -> concepts/...
      - content/en/docs/tasks/    -> tasks/...
      - content/en/releases/      -> releases/...
    """
    valid_pages: List[Tuple[str, str]] = []

    # 1. concepts/ and tasks/ under content/en/docs/
    docs_base = source_root / "content" / "en" / "docs"
    if docs_base.exists():
        for subtree in ("concepts", "tasks"):
            sub_dir = docs_base / subtree
            if not sub_dir.exists():
                continue
            for path in sub_dir.rglob("*.md"):
                rel_path = path.relative_to(docs_base).as_posix()
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                body = extract_body(content)
                if len(body) >= MIN_BODY_CHARS:
                    valid_pages.append((rel_path, content))

    # 2. releases/ under content/en/releases/ (rel_path relative to content/en/)
    en_base = source_root / "content" / "en"
    releases_dir = en_base / "releases"
    if releases_dir.exists():
        for path in releases_dir.rglob("*.md"):
            rel_path = path.relative_to(en_base).as_posix()
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            body = extract_body(content)
            if len(body) >= MIN_BODY_CHARS:
                valid_pages.append((rel_path, content))

    valid_pages.sort(key=lambda x: x[0])
    return valid_pages[:MAX_PAGES_PER_VERSION]


def fetch_via_git(commit_sha: str, temp_dir: Path) -> bool:
    """Perform a shallow git fetch for the exact commit SHA into temp_dir."""
    try:
        subprocess.run(["git", "init", str(temp_dir)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(temp_dir), "remote", "add", "origin", REPO_URL],
            check=True,
            capture_output=True,
        )
        print(f"Fetching commit {commit_sha} from {REPO_URL} via git ...")
        subprocess.run(
            ["git", "-C", str(temp_dir), "fetch", "--depth", "1", "origin", commit_sha],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(temp_dir), "checkout", "FETCH_HEAD"],
            check=True,
            capture_output=True,
        )
        return True
    except Exception as e:
        print(f"Git shallow fetch failed ({e}); falling back to HTTP archive download...", file=sys.stderr)
        return False


def fetch_via_archive(commit_sha: str) -> List[Tuple[str, str]]:
    """Download tarball from GitHub and extract relevant docs files in memory."""
    url = ARCHIVE_URL_TEMPLATE.format(commit_sha=commit_sha)
    print(f"Downloading archive from {url} ...")
    req = urllib.request.Request(url, headers={"User-Agent": "Aion-RAG-Fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        tar_bytes = resp.read()

    valid_pages: List[Tuple[str, str]] = []
    docs_prefix = "content/en/docs/"
    releases_prefix = "content/en/releases/"

    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.endswith(".md"):
                continue

            target_rel_path: Optional[str] = None

            # Check if in content/en/docs/concepts/ or content/en/docs/tasks/
            idx_docs = member.name.find(docs_prefix)
            if idx_docs != -1:
                rel = member.name[idx_docs + len(docs_prefix):]
                if any(rel.startswith(f"{sub}/") for sub in ("concepts", "tasks")):
                    target_rel_path = rel

            # Check if in content/en/releases/
            idx_rel = member.name.find(releases_prefix)
            if idx_rel != -1:
                rel = member.name[idx_rel + len("content/en/"):]
                target_rel_path = rel

            if target_rel_path is None:
                continue

            f = tar.extractfile(member)
            if f is None:
                continue
            content = f.read().decode("utf-8", errors="ignore")
            body = extract_body(content)
            if len(body) >= MIN_BODY_CHARS:
                valid_pages.append((target_rel_path, content))

    valid_pages.sort(key=lambda x: x[0])
    return valid_pages[:MAX_PAGES_PER_VERSION]


def fetch_version_pages(commit_sha: str) -> List[Tuple[str, str]]:
    """Clone or download repository and extract filtered documentation pages."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        temp_path = Path(tmp_dir)
        git_success = fetch_via_git(commit_sha, temp_path)
        if git_success:
            pages = scan_source_directory(temp_path)
            if pages:
                return pages

    # Fallback to GitHub archive download
    return fetch_via_archive(commit_sha)


def get_commit_shas_from_manifest(manifest_path: Path) -> Dict[str, Dict[str, str]]:
    """Load commit SHAs from existing MANIFEST.json if available, else use defaults."""
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            versions = {}
            for v_key, v_info in data.get("versions", {}).items():
                versions[v_key] = {
                    "branch": v_info.get("branch", DEFAULT_VERSIONS[v_key]["branch"]),
                    "commit_sha": v_info.get("commit_sha", DEFAULT_VERSIONS[v_key]["commit_sha"]),
                }
            if len(versions) == 2:
                print(f"Using pinned commit SHAs from existing {manifest_path}")
                return versions
        except Exception as e:
            print(f"Could not parse existing manifest ({e}); using default pinned SHAs.")
    return DEFAULT_VERSIONS


def main() -> None:
    corpus_root = Path("corpus")
    corpus_root.mkdir(parents=True, exist_ok=True)
    manifest_file = corpus_root / "MANIFEST.json"

    versions_to_fetch = get_commit_shas_from_manifest(manifest_file)
    manifest_versions = {}
    fetch_time = datetime.now(timezone.utc).isoformat()

    for version, cfg in versions_to_fetch.items():
        print(f"\n========================================")
        print(f"Fetching corpus for version {version} ({cfg['branch']} @ {cfg['commit_sha'][:8]}) ...")
        print(f"========================================")
        pages = fetch_version_pages(cfg["commit_sha"])
        target_dir = corpus_root / f"v{version}"

        # Clean existing target directory for deterministic rebuild
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        included_paths: List[str] = []
        for rel_path, content in pages:
            dest_file = target_dir / rel_path
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            dest_file.write_text(content, encoding="utf-8")
            included_paths.append(rel_path)

        manifest_versions[version] = {
            "branch": cfg["branch"],
            "commit_sha": cfg["commit_sha"],
            "page_count": len(included_paths),
            "included_paths": included_paths,
        }
        print(f"[{version}] Copied {len(included_paths)} markdown pages to {target_dir}")

    manifest_data = {
        "repository": "https://github.com/kubernetes/website",
        "selection_criteria": (
            f"Markdown files (.md) in content/en/docs/concepts/, content/en/docs/tasks/, "
            f"and content/en/releases/ with body text >= {MIN_BODY_CHARS} characters "
            f"(excluding Hugo front matter), sorted lexicographically, capped at {MAX_PAGES_PER_VERSION} pages."
        ),
        "fetch_date": fetch_time,
        "versions": manifest_versions,
    }

    manifest_file.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    print(f"\nWrote corpus manifest to {manifest_file}")


if __name__ == "__main__":
    main()
