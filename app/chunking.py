"""Deterministic markdown chunking engine.

Implements:
- Hugo front matter parsing (title, weight)
- Hugo shortcode resolution with shortcode engine
- Markdown heading hierarchy (H2/H3) splitting
- Code block and table preservation (never split mid-block)
- Inline markdown stripping (backticks, bold, italic, links -> plain text)
- Whitespace collapsing into single spaces for stored text and exact quote verification
- Document aliasing (from corpus/doc_aliases.json)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.schemas import Chunk, ChunkMetadata
from app.shortcodes import resolve_shortcodes_in_markdown

# Target chunk sizing
TARGET_WORDS = 350
MAX_WORDS = 500
OVERLAP_WORDS = 40


def parse_front_matter(content: str) -> Tuple[Dict[str, str], str]:
    """Parse YAML front matter delimited by --- at start of document."""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---"):
        return {}, normalized.strip()

    parts = normalized.split("---", 2)
    if len(parts) < 3:
        return {}, normalized.strip()

    fm_raw = parts[1]
    body = parts[2].strip()

    metadata: Dict[str, str] = {}
    title_match = re.search(r'^title:\s*["\']?(.*?)["\']?\s*$', fm_raw, re.MULTILINE)
    if title_match:
        metadata["title"] = title_match.group(1).strip()

    weight_match = re.search(r"^weight:\s*(\d+)", fm_raw, re.MULTILINE)
    if weight_match:
        metadata["weight"] = weight_match.group(1).strip()

    return metadata, body


def strip_inline_markdown(text: str) -> str:
    """Strip inline markdown (backticks, bold, italic, links) while keeping fenced code blocks and tables intact."""
    # 1. Protect fenced code blocks (```...``` or ~~~...~~~) using linear O(N) scan
    lines = text.split("\n")
    out: List[str] = []
    in_code = False
    current_code: List[str] = []
    code_blocks: List[str] = []

    for line in lines:
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            if in_code:
                current_code.append(line)
                idx = len(code_blocks)
                code_blocks.append("\n".join(current_code))
                out.append(f"\x00FENCEDCODEBLOCK{idx}\x00")
                current_code = []
                in_code = False
            else:
                in_code = True
                current_code.append(line)
        elif in_code:
            current_code.append(line)
        else:
            out.append(line)

    if current_code:
        idx = len(code_blocks)
        code_blocks.append("\n".join(current_code))
        out.append(f"\x00FENCEDCODEBLOCK{idx}\x00")

    # 2. Protect markdown tables (| ... |) using linear O(N) scan
    lines_after_code = out
    out = []
    table_lines: List[str] = []
    table_blocks: List[str] = []

    for line in lines_after_code:
        s = line.strip()
        if s.startswith("|") and s.endswith("|"):
            table_lines.append(line)
        else:
            if table_lines:
                idx = len(table_blocks)
                table_blocks.append("\n".join(table_lines))
                out.append(f"\x00MARKDOWNTABLE{idx}\x00")
                table_lines = []
            out.append(line)

    if table_lines:
        idx = len(table_blocks)
        table_blocks.append("\n".join(table_lines))
        out.append(f"\x00MARKDOWNTABLE{idx}\x00")

    text = "\n".join(out)

    # 3. Strip inline markdown syntax in surrounding prose
    # Links: [anchor text](url) -> anchor text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Images: ![alt text](url) -> alt text
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    # Bold / Italic
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    # Inline backticks: `code` -> code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # Strikethrough: ~~text~~ -> text
    text = re.sub(r"~~([^~]+)~~", r"\1", text)
    # HTML tags: <tag> -> ""
    text = re.sub(r"<[^>]+>", "", text)

    # Split by block placeholders so prose is cleanly single-spaced while code blocks & tables remain intact
    token_pattern = re.compile(r"(\x00(?:FENCEDCODEBLOCK|MARKDOWNTABLE)\d+\x00)")
    parts = token_pattern.split(text)
    processed_parts: List[str] = []
    for part in parts:
        if token_pattern.match(part):
            processed_parts.append(part)
        else:
            prose = re.sub(r"\s+", " ", part).strip()
            if prose:
                processed_parts.append(prose)

    result = "\n\n".join(processed_parts)
    for i, cb in enumerate(code_blocks):
        result = result.replace(f"\x00FENCEDCODEBLOCK{i}\x00", cb)
    for i, tb in enumerate(table_blocks):
        result = result.replace(f"\x00MARKDOWNTABLE{i}\x00", tb)

    return result.strip()


class Section:
    def __init__(self, heading: str, level: int, breadcrumbs: List[str]):
        self.heading = heading
        self.level = level
        self.breadcrumbs = list(breadcrumbs)
        self.paragraphs: List[str] = []

    @property
    def heading_path(self) -> str:
        return " > ".join(self.breadcrumbs) if self.breadcrumbs else self.heading


def split_into_sections(body: str, top_title: str) -> List[Section]:
    """Split markdown body into structural sections by heading hierarchy (H1..H4)."""
    lines = body.split("\n")
    sections: List[Section] = []
    current_crumbs: List[str] = [top_title]
    current_section = Section(top_title, 1, current_crumbs)
    sections.append(current_section)

    heading_re = re.compile(r"^(#{1,6})\s+(.*)$")
    in_code_block = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code_block = not in_code_block
            current_section.paragraphs.append(line)
            continue

        if in_code_block:
            current_section.paragraphs.append(line)
            continue

        h_match = heading_re.match(stripped)
        if h_match:
            level = len(h_match.group(1))
            heading_title = h_match.group(2).strip()
            # Clean heading title (remove trailing anchor or formatting)
            heading_title = re.sub(r"\{#.*?\}", "", heading_title).strip()
            heading_title = re.sub(r"`([^`]+)`", r"\1", heading_title)

            # Adjust breadcrumbs hierarchy
            while len(current_crumbs) >= level:
                current_crumbs.pop()
            current_crumbs.append(heading_title)

            current_section = Section(heading_title, level, current_crumbs)
            sections.append(current_section)
        else:
            current_section.paragraphs.append(line)

    return [s for s in sections if s.paragraphs or s.level > 1]


def split_large_text(text: str, target_words: int = TARGET_WORDS, overlap: int = OVERLAP_WORDS) -> List[str]:
    """Split text exceeding target size by word boundary with small overlap."""
    # If text contains fenced code blocks or tables, avoid breaking them
    if "```" in text or "~~~" in text or "| " in text:
        return [text]

    words = text.split(" ")
    if len(words) <= MAX_WORDS:
        return [text]

    chunks: List[str] = []
    idx = 0
    while idx < len(words):
        end = min(idx + target_words, len(words))
        chunk_words = words[idx:end]
        chunks.append(" ".join(chunk_words))
        if end >= len(words):
            break
        idx = max(0, end - overlap)
    return chunks


def chunk_document(
    file_path: Path,
    version: str,
    doc_aliases: Optional[Dict[str, str]] = None,
) -> Tuple[List[Chunk], Dict[str, int], bool]:
    """Chunk a single markdown file into validated Chunk models.
    
    Returns:
      (chunks_list, unresolved_shortcodes_map, was_remapped_bool)
    """
    raw_content = file_path.read_text(encoding="utf-8", errors="ignore")
    # Normalize newlines
    content = raw_content.replace("\r\n", "\n").replace("\r", "\n")

    # Determine original doc_id from relative path
    # e.g. corpus/v1.27/releases/version-skew-policy.md -> releases/version-skew-policy
    parts = file_path.as_posix().split(f"corpus/v{version}/")
    rel_in_corpus = parts[1] if len(parts) > 1 else file_path.name
    orig_doc_id = rel_in_corpus[:-3] if rel_in_corpus.endswith(".md") else rel_in_corpus

    # Apply alias mapping if present (deterministic alias lookup)
    remapped = False
    doc_id = orig_doc_id
    if doc_aliases and orig_doc_id in doc_aliases:
        doc_id = doc_aliases[orig_doc_id]
        remapped = True

    # 1. Parse front matter
    fm, body = parse_front_matter(content)
    title = fm.get("title", "")
    if not title:
        # Fallback to first heading or filename
        first_h = re.search(r"^#+\s+(.*)$", body, re.MULTILINE)
        title = first_h.group(1).strip() if first_h else orig_doc_id.split("/")[-1].replace("-", " ").title()

    # 2. Resolve shortcodes
    resolved_body, unresolved = resolve_shortcodes_in_markdown(body, version, doc_path=file_path)

    # 3. Structural heading split
    sections = split_into_sections(resolved_body, title)

    chunks: List[Chunk] = []
    ordinal = 0

    for sec in sections:
        sec_raw_text = "\n".join(sec.paragraphs).strip()
        if not sec_raw_text:
            continue

        # Strip inline markdown and preserve code blocks & tables
        cleaned_text = strip_inline_markdown(sec_raw_text)
        if not cleaned_text:
            continue

        # Check size and subdivide if necessary
        text_slices = split_large_text(cleaned_text)
        heading_path = sec.heading_path

        for slice_text in text_slices:
            if len(slice_text.split()) < 5:  # skip trivial stubs
                continue

            chunk_id = f"v{version}:{doc_id}#c{ordinal}"
            embedded_text = f"{title} > {heading_path}: {slice_text}"

            # source_path remains the original file path on disk
            metadata = ChunkMetadata(
                doc_id=doc_id,
                version=version,
                chunk_id=chunk_id,
                title=title,
                heading_path=heading_path,
                ordinal=ordinal,
                source_path=file_path.as_posix(),
            )

            chunks.append(
                Chunk(
                    metadata=metadata,
                    text=slice_text,
                    embedded_text=embedded_text,
                )
            )
            ordinal += 1

    return chunks, unresolved, remapped
