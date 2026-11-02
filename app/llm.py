"""LLM client for Ollama with structured generation and strict citation enforcement."""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

from app.config import Settings, get_settings
from app.schemas import Citation, Chunk

from abc import ABC, abstractmethod

logger = logging.getLogger("rag-llm")


def extract_sentences(text: str) -> List[str]:
    """Split text into sentences and list items cleanly handling newlines and list lines."""
    items = []
    lines = text.strip().splitlines()
    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
        if re.match(r"^(\*|-|\+|\d+\.)\s+", line_clean):
            items.append(line_clean)
        else:
            sents = re.split(r"(?<=[.!?])\s+", line_clean)
            for s in sents:
                s_strip = s.strip()
                if s_strip:
                    items.append(s_strip)
    return items


class BaseLLMClient(ABC):
    """Abstract interface for LLM text generation."""

    @abstractmethod
    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text from prompt."""
        pass


class FakeLLMClient(BaseLLMClient):
    """Deterministic fake LLM client for fast, offline unit testing.
    
    Extracts the first retrieved chunk from the prompt and returns a valid
    JSON answer citing that chunk with grounded text from the chunk.
    """

    def __init__(self, answer_prefix: Optional[str] = None):
        self.answer_prefix = answer_prefix

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        # Find chunk block in prompt (supports both formats)
        block_match = re.search(r"### Kubernetes [^|\n]+\|\s*([a-zA-Z0-9_\-\.:/#]+)\s*\|[^\n]*\n(.*?)(?=\n### Kubernetes |\nQuestion:|$)", prompt, re.DOTALL)
        if not block_match:
            block_match = re.search(r"### \[([a-zA-Z0-9_\-\.:/#]+)\][^\n]*\n(.*?)(?=\n### \[|\nQuestion:|$)", prompt, re.DOTALL)
        if not block_match:
            return json.dumps({
                "answer": "No documentation chunk found in prompt.",
                "supported": False,
            })

        chunk_id = block_match.group(1)
        chunk_body = block_match.group(2).strip()
        sentences = extract_sentences(chunk_body)
        first_sent = sentences[0] if sentences else "Valid documentation sentence."
        
        if self.answer_prefix:
            first_sent = f"{self.answer_prefix}: {first_sent}"

        return json.dumps({
            "answer": f"{first_sent} [{chunk_id}].",
            "supported": True,
        })


class OllamaClient(BaseLLMClient):
    """Minimal Ollama client configured for low-resource environments (qwen2.5:3b, num_ctx 4096)."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.host = self.settings.OLLAMA_HOST.rstrip("/")
        self.model = self.settings.LLM_MODEL
        self.timeout = self.settings.OLLAMA_TIMEOUT_SECONDS
        self.num_ctx = self.settings.NUM_CTX
        self.num_predict = self.settings.NUM_PREDICT
        self.keep_alive = self.settings.KEEP_ALIVE

    def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Execute generation request to Ollama with temperature 0."""
        url = f"{self.host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0.0,
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict,
            },
        }
        if system:
            payload["system"] = system

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    return data.get("response", "")
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500 and attempt < max_retries:
                    logger.warning(
                        f"Ollama HTTP {exc.response.status_code} error (attempt {attempt + 1}/{max_retries + 1}), retrying..."
                    )
                    time.sleep(0.5 * (attempt + 1))
                    continue
                logger.error(f"Ollama generation failed or timed out: {exc}")
                raise RuntimeError(f"Ollama generation failed: {exc}") from exc
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                if attempt < max_retries:
                    logger.warning(
                        f"Ollama connection/request error (attempt {attempt + 1}/{max_retries + 1}): {exc}, retrying..."
                    )
                    time.sleep(0.5 * (attempt + 1))
                    continue
                logger.error(f"Ollama generation failed or timed out: {exc}")
                raise RuntimeError(f"Ollama generation failed: {exc}") from exc
            except Exception as exc:
                logger.error(f"Ollama generation failed or timed out: {exc}")
                raise RuntimeError(f"Ollama generation failed: {exc}") from exc


def build_system_prompt() -> str:
    """System prompt demanding grounded answers, version distinctions, and strict JSON output without model quotes."""
    return (
        "You are an expert Kubernetes documentation assistant for versions 1.27 and 1.31.\n"
        "Your duty is to answer strictly and only from the provided documentation chunks.\n"
        "Rules:\n"
        "1. Answer ONLY using the facts stated in the provided chunks. Do NOT assume, extrapolate, or hallucinate.\n"
        "2. Put the citation marker [chunk_id] at the end of every single factual sentence.\n"
        "3. Provide plain sentences in the 'answer' field. Never output JSON, code fences, or a dictionary inside the 'answer' string.\n"
        "4. For questions involving version comparison, limits, numbers, or conditions, provide one plain sentence per version, starting with 'In Kubernetes 1.27,' and 'In Kubernetes 1.31,'.\n"
        "5. Set supported to false only if none of the chunks addresses the question.\n"
        "6. Output ONLY a valid JSON object with exact keys: 'answer' (string with [chunk_id] citation markers) and 'supported' (boolean).\n"
        "Do not include any quotes list, reasoning, or markdown fences outside the JSON object."
    )


def build_user_prompt(question: str, retrieved_chunks: List[Chunk], max_context_chars: int = 12000) -> str:
    """Format user prompt with retrieved chunk texts, capped to respect context limits."""
    chunks_text_blocks = []
    current_len = 0

    for chunk in retrieved_chunks:
        header = f"### Kubernetes {chunk.metadata.version} | {chunk.metadata.chunk_id} | {chunk.metadata.heading_path}"
        words = chunk.text.strip().split()
        if len(words) > 250:
            body = " ".join(words[:250]) + "..."
        else:
            body = chunk.text.strip()
        block = f"{header}\n{body}\n"

        if current_len + len(block) > max_context_chars and chunks_text_blocks:
            break
        chunks_text_blocks.append(block)
        current_len += len(block)

    context_str = "\n".join(chunks_text_blocks)
    return (
        f"Documentation Chunks:\n\n{context_str}\n\n"
        f"Question: {question}\n\n"
        "JSON Response:"
    )


def build_retry_prompt(question: str, top_chunks: List[Chunk]) -> str:
    """Shorter plain-text prompt using only top 2-3 chunks without JSON requirement."""
    blocks = []
    for chunk in top_chunks[:3]:
        header = f"### Kubernetes {chunk.metadata.version} | {chunk.metadata.chunk_id} | {chunk.metadata.heading_path}"
        words = chunk.text.strip().split()
        if len(words) > 250:
            body = " ".join(words[:250]) + "..."
        else:
            body = chunk.text.strip()
        blocks.append(f"{header}\n{body}\n")
    context = "\n".join(blocks)
    return (
        f"Documentation Chunks:\n\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer the question directly and concisely in 1-2 plain sentences using only the documentation chunks above. "
        "Cite the relevant chunk_id like [chunk_id] for each statement. "
        "If comparing versions, state what applies to Kubernetes 1.27 and Kubernetes 1.31 separately."
    )


def clean_json_escapes(s: str) -> str:
    """Clean invalid JSON backslash escapes like \\[ or \\] before json.loads."""
    return re.sub(r'\\(?![/"\\bfnrtu])', '', s)


def split_answer_into_units(text: str) -> List[Tuple[str, str]]:
    """Split text into units: ('prose', sentence_or_list_item) or ('code_block', code_fence_block).
    
    Fenced code blocks (```...``` or ~~~...~~~) are preserved intact as units.
    Prose sections are split cleanly using extract_sentences().
    """
    text_norm = text.replace("\r\n", "\n").replace("\r", "\n")
    pattern = re.compile(r"(```[a-zA-Z0-9_-]*\s*\n[\s\S]*?\n\s*```|~~~[a-zA-Z0-9_-]*\s*\n[\s\S]*?\n\s*~~~)")
    units: List[Tuple[str, str]] = []

    pos = 0
    for match in pattern.finditer(text_norm):
        start, end = match.span()
        prose_before = text_norm[pos:start]
        if prose_before.strip():
            for s in extract_sentences(prose_before):
                units.append(("prose", s))
        units.append(("code_block", match.group(0).strip()))
        pos = end

    prose_after = text_norm[pos:]
    if prose_after.strip():
        for s in extract_sentences(prose_after):
            units.append(("prose", s))

    if not units and text_norm.strip():
        for s in extract_sentences(text_norm):
            units.append(("prose", s))

    return units


def parse_llm_json(raw_response: str, client: Optional[OllamaClient] = None) -> Optional[Dict[str, Any]]:
    """Parse JSON robustly, stripping markdown fences, invalid escapes, and retrying once if needed."""
    cleaned = raw_response.strip()

    # Strip markdown code fences if present around the JSON object
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    elif cleaned.startswith("```json") or cleaned.startswith("```"):
        f_match = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, re.DOTALL)
        if f_match:
            cleaned = f_match.group(1).strip()

    # Direct JSON parse attempt (clean invalid escapes, allow literal control chars)
    cleaned_escapes = clean_json_escapes(cleaned)
    for candidate_str in (cleaned, cleaned_escapes):
        try:
            data = json.loads(candidate_str, strict=False)
            if isinstance(data, dict) and "answer" in data:
                ans = str(data["answer"]).strip()
                if ans.startswith("{") and ans.endswith("}"):
                    try:
                        inner = json.loads(ans, strict=False)
                        if isinstance(inner, dict):
                            parts = []
                            for k, v in inner.items():
                                parts.append(f"In Kubernetes {k.lstrip('v')}, {v}")
                            data["answer"] = " ".join(parts)
                    except Exception:
                        pass
                return data
        except Exception:
            pass

    # Regex substring extraction attempt
    brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if brace_match:
        cand = brace_match.group(0)
        for c_str in (cand, clean_json_escapes(cand)):
            try:
                data = json.loads(c_str, strict=False)
                if isinstance(data, dict) and "answer" in data:
                    return data
            except Exception:
                pass

    # One retry with Ollama if client provided
    if client:
        try:
            retry_prompt = f"Fix the following output into valid JSON with keys 'answer' and 'supported':\n\n{cleaned}"
            retry_raw = client.generate(retry_prompt)
            retry_fence = re.search(r"```(?:json)?\s*(.*?)\s*```", retry_raw, re.DOTALL)
            retry_text = retry_fence.group(1).strip() if retry_fence else retry_raw.strip()
            data = json.loads(clean_json_escapes(retry_text), strict=False)
            if isinstance(data, dict) and "answer" in data:
                return data
        except Exception as retry_exc:
            logger.warning(f"Ollama JSON repair retry failed: {retry_exc}")

    return None


STOP_WORDS: Set[str] = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "up", "about", "into", "over", "after", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "but", "if", "then", "else", "when", "where",
    "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "can", "will", "just",
    "should", "now", "it", "its", "this", "that", "these", "those", "as", "you", "your"
}


def is_identifier(token: str) -> bool:
    """Check if token is an identifier that should be kept as a content word."""
    if any(c in token for c in "-_./:"):
        return True
    if token.startswith("--"):
        return True
    # CamelCase with 2+ humps (e.g. ServiceAccount, PodDisruptionBudget)
    if re.match(r"^[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+$", token):
        return True
    return False


def extract_candidate_spans(chunk_text: str) -> List[str]:
    """Extract candidate verbatim spans (sentences, list items, code lines) from stored chunk text."""
    spans: List[str] = []
    lines = chunk_text.split("\n")
    in_code = False

    for line in lines:
        s = line.strip()
        if not s:
            continue
        if s.startswith("```") or s.startswith("~~~"):
            in_code = not in_code
            continue

        if in_code:
            if len(s) >= 5 and s in chunk_text:
                spans.append(s[:300])
        elif s.startswith("|") and s.endswith("|"):
            if len(s) >= 5 and s in chunk_text:
                spans.append(s[:300])
        else:
            list_match = re.match(r"^(\d+\.|\*|\-)\s+(.*)$", s)
            if list_match:
                item_text = list_match.group(2).strip()
                if item_text and item_text in chunk_text:
                    spans.append(item_text[:300])
                if s in chunk_text:
                    spans.append(s[:300])

            sentences = re.split(r"(?<=[.!?])\s+", s)
            for sent in sentences:
                sent_clean = sent.strip()
                if len(sent_clean) >= 10 and sent_clean in chunk_text:
                    spans.append(sent_clean[:300])

    seen = set()
    unique_spans = []
    for sp in spans:
        if sp not in seen and len(sp.strip()) > 0:
            seen.add(sp)
            unique_spans.append(sp)

    if not unique_spans and chunk_text.strip():
        unique_spans.append(chunk_text.strip()[:300])

    return unique_spans


def pick_best_quote(answer_sentence: str, chunk_text: str) -> str:
    """Pick verbatim span from stored chunk text with highest word overlap (max 300 chars)."""
    spans = extract_candidate_spans(chunk_text)
    if not spans:
        return chunk_text[:300]

    ans_words = set(re.findall(r"\b\w+\b", answer_sentence.lower()))
    best_span = spans[0]
    best_overlap = -1
    best_jaccard = -1.0

    for span in spans:
        span_words = set(re.findall(r"\b\w+\b", span.lower()))
        overlap = len(ans_words & span_words)
        jaccard = overlap / len(ans_words | span_words) if (ans_words | span_words) else 0.0

        if (overlap > best_overlap) or (overlap == best_overlap and jaccard > best_jaccard):
            best_overlap = overlap
            best_jaccard = jaccard
            best_span = span

    quote = best_span[:300]
    return quote


def repair_quote_to_sentence(quote: str, chunk_text: str) -> Optional[str]:
    """Deterministic repair: map drifted quote to verbatim sentence if overlap >= 0.5."""
    if not quote or not chunk_text:
        return None
    if quote in chunk_text:
        return quote
    spans = extract_candidate_spans(chunk_text)
    quote_words = set(re.findall(r"\b\w+\b", quote.lower()))
    if not quote_words:
        return None
    best_span = None
    best_jaccard = 0.0
    for span in spans:
        span_words = set(re.findall(r"\b\w+\b", span.lower()))
        if not span_words:
            continue
        overlap = len(quote_words & span_words)
        jaccard = overlap / len(quote_words | span_words)
        if jaccard > best_jaccard and jaccard >= 0.5:
            best_jaccard = jaccard
            best_span = span
    return best_span


def compute_sentence_support(sentence: str, chunk_text: str) -> Tuple[float, List[str], List[str]]:
    """Compute support = fraction of content words in sentence appearing in chunk_text."""
    clean_s = strip_chunk_markers(sentence)
    raw_tokens = re.findall(r"[a-zA-Z0-9_\-\./:]+", clean_s)

    content_words = []
    for t in raw_tokens:
        clean_t = re.sub(r"^[(\'\"\`]+|[)\'\"\`.,?!;:]+$", "", t)
        if not clean_t:
            continue
        if clean_t.lower() not in STOP_WORDS or is_identifier(clean_t):
            content_words.append(clean_t)

    if not content_words:
        return 1.0, [], []

    chunk_lower = chunk_text.lower()
    matched = [w for w in content_words if w.lower() in chunk_lower]
    support = len(matched) / len(content_words)
    return support, content_words, matched


def extract_code_quote(code_block: str, chunk_text: str) -> str:
    """Extract a verbatim substring quote (max 300 chars) from chunk_text matching code_block."""
    lines = [
        l.strip()
        for l in code_block.splitlines()
        if not l.strip().startswith("```") and not l.strip().startswith("~~~") and l.strip()
    ]
    if not lines:
        return chunk_text[:300]

    # 1. Try finding matching code fences in chunk_text
    fences = list(re.finditer(r"```(?:[a-zA-Z0-9_-]*\s*\n)?([\s\S]*?)\n```", chunk_text))
    for f in fences:
        inner = f.group(1)
        first_match = next((l for l in lines if l in inner), None)
        if first_match:
            pos = inner.find(first_match)
            cand = inner[pos:pos + 300]
            if "\n" in cand and len(cand) >= 200:
                quote = cand.rsplit("\n", 1)[0].strip()
            else:
                quote = cand.strip()
            if quote in chunk_text and len(quote) > 0:
                return quote

    # 2. Try finding first matching line anywhere in chunk_text
    for l in lines:
        if l in chunk_text:
            pos = chunk_text.find(l)
            cand = chunk_text[pos:pos + 300]
            if "\n" in cand and len(cand) >= 200:
                quote = cand.rsplit("\n", 1)[0].strip()
            else:
                quote = cand.strip()
            if quote in chunk_text and len(quote) > 0:
                return quote

    return pick_best_quote(code_block, chunk_text)


def strip_chunk_markers(text: str) -> str:
    """Remove ONLY chunk-shaped markers:
    - [v1.31:path#cN], [v1.27:path#cN]
    - [chunk_id N], [chunk_id]
    - [kubernetes 1.27], [kubernetes 1.31]
    - bare [1.27], [1.31]
    Preserves other bracketed text such as [alpha], [beta], [stable].
    """
    patterns = [
        r"\[v?1\.\d{2}:[a-zA-Z0-9_\-\./#]+\]",
        r"\[chunk_id(?:\s*[:=]?\s*\d+)?\]",
        r"\[(?:kubernetes|k8s)\s+v?1\.\d{2}\]",
        r"\[v?1\.\d{2}\]",
    ]
    res = text
    for p in patterns:
        res = re.sub(p, "", res, flags=re.IGNORECASE)
    res = re.sub(r"[ \t]+", " ", res)
    return res.strip()


def is_version_prefix_only(text: str) -> bool:
    """Check if a sentence is only a version prefix (e.g. 'In Kubernetes 1.27,' or 'In 1.27 and 1.31,')."""
    clean = re.sub(r"[,.:;–—\s]+", " ", text).strip().lower()
    prefix_pattern = r"^(?:(?:in|for|on|and)\s+)?(?:kubernetes|k8s\s+)?v?1\.\d{2}(?:\s+(?:and\s+)?(?:in|for|on\s+)?(?:kubernetes|k8s\s+)?v?1\.\d{2})?$"
    return bool(re.match(prefix_pattern, clean)) and ("1.27" in clean or "1.31" in clean)


def clean_final_bracket_markers(text: str, valid_cids: Set[str]) -> str:
    """Ensure no bracket marker remains unless it is a chunk_id present in citations[],
    while preserving other bracketed text such as [alpha], [beta], [stable].
    """
    def replace_bracket(match: re.Match) -> str:
        inner = match.group(1).strip()
        if inner in valid_cids:
            return match.group(0)
        # Legitimate bracketed terms like [alpha], [beta], [stable]
        if re.match(r"^(?:alpha|beta|stable|deprecated|ga|default)$", inner, re.IGNORECASE):
            return match.group(0)
        return ""

    cleaned = re.sub(r"\[([^\]]+)\]", replace_bracket, text)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\s+([.,;:!?])", r"\1", cleaned)
    return cleaned.strip()


def detect_sentence_version(text: str) -> Optional[str]:
    """Detect if sentence exclusively mentions 1.27 or 1.31 in prose (ignoring citation markers).
    
    If it mentions 1.27 and not 1.31 -> '1.27'.
    If it mentions 1.31 and not 1.27 -> '1.31'.
    If neither or both -> None (any version allowed).
    """
    clean_text = strip_chunk_markers(text)
    p127 = r"(?:\bv?1\.27\b|release-1\.27)"
    p131 = r"(?:\bv?1\.31\b|release-1\.31)"
    has_127 = bool(re.search(p127, clean_text, re.IGNORECASE))
    has_131 = bool(re.search(p131, clean_text, re.IGNORECASE))
    if has_127 and not has_131:
        return "1.27"
    if has_131 and not has_127:
        return "1.31"
    return None


def enforce_citations(
    raw_answer: str,
    retrieved_chunks_or_raw_citations: Any,
    retrieved_chunks_opt: Any = None,
    trace_details: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Citation], bool]:
    """Enforce citations and compute sentence support:
    
    1. Split answer into sentences and list items, preserving fenced code blocks intact.
    2. Version-aware attribution: if sentence names 1.27 or 1.31, attribute only to that version's chunks.
    3. For each sentence or code block: keep markers that point to eligible retrieved chunks.
       If it has none, compute support score against EACH eligible chunk (in prompt order)
       and attribute to best one (higher score, then earlier chunk).
       If best score >= MIN_SUPPORT, append [chunk_id]. Otherwise prune.
    4. If a sentence has a marker whose chunk has support below MIN_SUPPORT,
       try the other eligible chunks before pruning, and rewrite marker to the best one.
    5. Code blocks are attributed to the matching chunk using code lines as verbatim quotes.
    6. Final answer satisfies: every sentence carries at least one [chunk_id],
       and every marker appears in citations[].
    7. Refuse (no_valid_citation) only if no unit survives.
    """
    if isinstance(retrieved_chunks_opt, list):
        retrieved_chunks = retrieved_chunks_opt
    elif isinstance(retrieved_chunks_or_raw_citations, list) and (
        not retrieved_chunks_or_raw_citations or isinstance(retrieved_chunks_or_raw_citations[0], Chunk)
    ):
        retrieved_chunks = retrieved_chunks_or_raw_citations
    else:
        retrieved_chunks = []

    chunk_map = {c.metadata.chunk_id: c for c in retrieved_chunks}
    settings = get_settings()
    min_support = float(os.environ.get("MIN_SUPPORT", str(settings.MIN_SUPPORT)))

    answer_units = split_answer_into_units(raw_answer)
    valid_citations: List[Citation] = []
    surviving_units: List[Tuple[str, str]] = []
    dropped_sentences: List[str] = []
    trace_support: List[Dict[str, Any]] = []

    for unit_type, item in answer_units:
        existing_markers = re.findall(r"\[([a-zA-Z0-9_\-\.:/#]+)\]", item)

        target_version = detect_sentence_version(item)
        if target_version:
            eligible_chunks = [c for c in retrieved_chunks if c.metadata.version == target_version]
            valid_model_markers = [
                m for m in existing_markers
                if m in chunk_map and chunk_map[m].metadata.version == target_version
            ]
        else:
            eligible_chunks = retrieved_chunks
            valid_model_markers = [m for m in existing_markers if m in chunk_map]

        has_model_marker = bool(valid_model_markers)

        attributed_cids: List[str] = []
        best_score = -1.0
        rewritten = False

        if unit_type == "code_block":
            clean_block = strip_chunk_markers(item).strip()
            if has_model_marker:
                combined_cited_text = " ".join(chunk_map[m].text for m in valid_model_markers)
                m_score, _, _ = compute_sentence_support(clean_block, combined_cited_text)
                if m_score >= min_support:
                    attributed_cids = valid_model_markers
                    best_score = m_score
                else:
                    for c in eligible_chunks:
                        score, _, _ = compute_sentence_support(clean_block, c.text)
                        if score > best_score:
                            best_score = score
                            attributed_cids = [c.metadata.chunk_id]
                    if best_score >= min_support:
                        rewritten = True
            else:
                for c in eligible_chunks:
                    score, _, _ = compute_sentence_support(clean_block, c.text)
                    if score > best_score:
                        best_score = score
                        attributed_cids = [c.metadata.chunk_id]

            kept = (best_score >= min_support and len(attributed_cids) > 0)

            trace_support.append({
                "sentence": clean_block[:80] + "...",
                "model_marker": has_model_marker,
                "attributed_chunk": attributed_cids[0] if attributed_cids else None,
                "support": round(best_score if best_score >= 0 else 0.0, 3),
                "status": "kept" if kept else "pruned",
            })

            if not kept:
                dropped_sentences.append(item)
                continue

            cid = attributed_cids[0]
            final_block = f"{clean_block}\n[{cid}]"
            surviving_units.append(("code_block", final_block))

            for cid_target in attributed_cids:
                chunk = chunk_map[cid_target]
                quote = extract_code_quote(clean_block, chunk.text)
                cit = Citation(
                    doc_id=chunk.metadata.doc_id,
                    chunk_id=cid_target,
                    version=chunk.metadata.version,
                    quote=quote,
                )
                if not any(c.chunk_id == cit.chunk_id and c.quote == cit.quote for c in valid_citations):
                    valid_citations.append(cit)

        else:
            # Prose sentence
            clean_text = strip_chunk_markers(item).strip()
            clean_words = clean_text.split()
            if is_version_prefix_only(clean_text) or len(clean_words) < 4:
                dropped_sentences.append(item)
                continue

            if has_model_marker:
                combined_cited_text = " ".join(chunk_map[m].text for m in valid_model_markers)
                m_score, _, _ = compute_sentence_support(item, combined_cited_text)
                if m_score >= min_support:
                    attributed_cids = valid_model_markers
                    best_score = m_score
                else:
                    for c in eligible_chunks:
                        score, _, _ = compute_sentence_support(item, c.text)
                        if score > best_score:
                            best_score = score
                            attributed_cids = [c.metadata.chunk_id]
                    if best_score >= min_support:
                        rewritten = True
            else:
                for c in eligible_chunks:
                    score, _, _ = compute_sentence_support(item, c.text)
                    if score > best_score:
                        best_score = score
                        attributed_cids = [c.metadata.chunk_id]

            kept = (best_score >= min_support and len(attributed_cids) > 0)

            trace_support.append({
                "sentence": item,
                "model_marker": has_model_marker,
                "attributed_chunk": attributed_cids[0] if attributed_cids else None,
                "support": round(best_score if best_score >= 0 else 0.0, 3),
                "status": "kept" if kept else "pruned",
            })

            if not kept:
                dropped_sentences.append(item)
                continue

            cid = attributed_cids[0]
            punct_match = re.match(r"^(.*?)([.!?]+)$", clean_text)
            if punct_match:
                final_sent = f"{punct_match.group(1).rstrip()} [{cid}]{punct_match.group(2)}"
            else:
                final_sent = f"{clean_text} [{cid}]"
            surviving_units.append(("prose", final_sent))

            for cid_target in attributed_cids:
                chunk = chunk_map[cid_target]
                quote = pick_best_quote(clean_text, chunk.text)
                cit = Citation(
                    doc_id=chunk.metadata.doc_id,
                    chunk_id=cid_target,
                    version=chunk.metadata.version,
                    quote=quote,
                )
                if not any(c.chunk_id == cit.chunk_id and c.quote == cit.quote for c in valid_citations):
                    valid_citations.append(cit)

    if trace_details is not None:
        trace_details["sentences_pruned"] = dropped_sentences
        trace_details["sentence_support"] = trace_support
        trace_details["citations"] = [
            {
                "chunk_id": c.chunk_id,
                "quote": c.quote,
                "verified": True,
                "repaired": False,
                "dropped_reason": None,
            }
            for c in valid_citations
        ]

    reconstructed_parts = []
    for i, (u_type, u_text) in enumerate(surviving_units):
        if u_type == "code_block":
            reconstructed_parts.append(f"\n\n{u_text}\n\n")
        else:
            if i > 0 and surviving_units[i - 1][0] == "code_block":
                reconstructed_parts.append(u_text)
            elif reconstructed_parts:
                reconstructed_parts.append(" " + u_text)
            else:
                reconstructed_parts.append(u_text)

    reconstructed_answer = re.sub(r"\n{3,}", "\n\n", "".join(reconstructed_parts)).strip()
    valid_cids = {c.chunk_id for c in valid_citations}
    reconstructed_answer = clean_final_bracket_markers(reconstructed_answer, valid_cids)

    if not valid_citations or not reconstructed_answer:
        return (
            "The documentation does not provide sufficient verified citations to answer this question.",
            [],
            False,
        )

    return reconstructed_answer, valid_citations, True
