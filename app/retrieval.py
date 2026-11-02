"""Retriever interface and Chroma-backed dense retriever implementation."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import chromadb
import math
from sentence_transformers import SentenceTransformer

from app.config import Settings, get_settings
from app.schemas import Chunk, ChunkMetadata

EXTENDED_STOP_WORDS = {
    # Standard English stop words
    'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are', 'was', 'were',
    'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a', 'an',
    'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with',
    'about', 'against', 'between', 'into', 'through', 'during', 'before', 'after', 'above', 'below',
    'to', 'from', 'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then',
    'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too',
    'very', 's', 't', 'can', 'will', 'just', 'don', 'should', 'now', 'kubernetes', 'k8s', 'also', 'true', 'false',
    'use', 'used', 'using',
    # Generic question words specified in A3:
    'maximum', 'supported', 'role', 'order', 'relative', 'component', 'default', 'number', 'cluster'
}


def light_stem(w: str) -> str:
    """Light deterministic stemmer for English content words."""
    w = w.lower()
    if w.endswith('tions') or w.endswith('tion'):
        return re.sub(r'tions?$', 't', w)
    if w.endswith('sions') or w.endswith('sion'):
        return re.sub(r'sions?$', 's', w)
    if w.endswith('ing') and len(w) > 5:
        return re.sub(r'ing$', '', w)
    if w.endswith('ed') and len(w) > 4:
        return re.sub(r'ed$', '', w)
    if w.endswith('es') and len(w) > 4:
        return re.sub(r'es$', '', w)
    if w.endswith('s') and not w.endswith('ss') and len(w) > 3:
        return re.sub(r's$', '', w)
    return w


def get_identifier_variants(term: str) -> Set[str]:
    """Generate case-insensitive variants (singular and plural) for an identifier term."""
    t = term.strip().lower()
    variants = {t}

    # Plural -> Singular
    if t.endswith("ies") and len(t) > 4:
        variants.add(t[:-3] + "y")
    elif t.endswith("es") and len(t) > 3:
        if t.endswith(("sses", "shes", "ches", "xes", "zes")):
            variants.add(t[:-2])
        else:
            variants.add(t[:-1])
            variants.add(t[:-2])
    elif t.endswith("s") and not t.endswith("ss") and len(t) > 2:
        variants.add(t[:-1])

    # Singular -> Plural
    if t.endswith("y") and len(t) > 2 and t[-2] not in "aeiou":
        variants.add(t[:-1] + "ies")
    elif t.endswith(("sh", "ch", "x", "z")):
        variants.add(t + "es")
    elif t.endswith("ss"):
        variants.add(t + "es")
    elif not t.endswith("s"):
        variants.add(t + "s")

    return {v for v in variants if v}


def extract_question_relevance_terms(question: str) -> Tuple[List[str], List[str]]:
    """Extract question terms: identifiers and stemmed content words.
    
    Returns:
        (identifiers, content_stems)
    """
    identifiers = extract_identifier_tokens(question)
    id_set = {id_tok.lower() for id_tok in identifiers}

    raw_tokens = re.findall(r"[a-zA-Z0-9_\-\./:]+", question)
    content_stems: List[str] = []
    for raw in raw_tokens:
        clean = re.sub(r"^[^\w]+|[^\w]+$", "", raw).lower()
        if not clean or len(clean) < 2:
            continue
        if clean in id_set:
            continue
        if clean in EXTENDED_STOP_WORDS:
            continue
        stem = light_stem(clean)
        if stem not in EXTENDED_STOP_WORDS and stem not in content_stems:
            content_stems.append(stem)
    return identifiers, content_stems


class Retriever(ABC):
    """Abstract retriever interface to allow dense, sparse, or hybrid implementations."""

    @abstractmethod
    def retrieve(
        self,
        query: str,
        version: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Tuple[Chunk, float]]:
        """Retrieve top_k chunks for a query with similarity scores.
        
        Returns:
            List of (Chunk, similarity_score) tuples.
        """
        pass


def extract_identifier_tokens(question: str) -> List[str]:
    """Extract identifier-like tokens from the question:
    - Contains '/' or '--' prefix
    - kubernetes.io style names
    - 2+ hyphens
    - CamelCase with 2+ humps
    """
    raw_tokens = re.findall(r"[^\s]+", question)
    identifiers: List[str] = []
    for raw in raw_tokens:
        tok = re.sub(r"^[(\'\"\`\[\{<]+|[)\'\"\`\]\}>.,?!;:]+$", "", raw)
        if not tok:
            continue
        # 1. contains '/' or '--' prefix
        if "/" in tok or tok.startswith("--"):
            identifiers.append(tok)
            continue
        # 2. kubernetes.io style names
        if "kubernetes.io" in tok.lower():
            identifiers.append(tok)
            continue
        # 3. 2+ hyphens
        if tok.count("-") >= 2:
            identifiers.append(tok)
            continue
        # 4. CamelCase with 2+ humps
        if re.match(r"^[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+$", tok):
            identifiers.append(tok)
            continue
    return identifiers


def detect_version_in_text(text: str) -> Optional[str]:
    """Detect if the query explicitly targets a single Kubernetes version (1.27 or 1.31).
    
    Accepts '1.27', 'v1.27', 'release-1.27' and '1.31', 'v1.31', 'release-1.31'.
    Other versions (e.g. '1.25', 'v1.30') do NOT pin.
    If both 1.27 and 1.31 appear, returns None (search both).
    """
    pattern_127 = r"(?:\bv?1\.27\b|release-1\.27)"
    pattern_131 = r"(?:\bv?1\.31\b|release-1\.31)"

    has_127 = bool(re.search(pattern_127, text, re.IGNORECASE))
    has_131 = bool(re.search(pattern_131, text, re.IGNORECASE))

    if has_127 and not has_131:
        return "1.27"
    if has_131 and not has_127:
        return "1.31"
    return None


class ChromaDenseRetriever(Retriever):
    """Dense retriever using SentenceTransformer embeddings over ChromaDB."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.index_dir = Path(self.settings.INDEX_DIR)
        self.chroma_dir = self.index_dir / "chroma"
        self.chunks_path = Path(self.settings.CHUNKS_PATH)

        # 1. Load embedding model
        self.embed_model = SentenceTransformer(self.settings.EMBED_MODEL)

        # 2. Connect to Chroma persistent client
        self.chroma_client = chromadb.PersistentClient(path=str(self.chroma_dir))
        self.collection = self.chroma_client.get_collection(name="k8s_docs")

        # 3. Load chunks metadata sidecar and build corpus tokens
        self.chunks_by_id: Dict[str, Chunk] = {}
        self.tokens_by_version: Dict[str, Set[str]] = {"1.27": set(), "1.31": set()}
        self.all_corpus_tokens: Set[str] = set()

        if self.chunks_path.exists():
            with self.chunks_path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    meta = ChunkMetadata(
                        doc_id=row["doc_id"],
                        version=row["version"],
                        chunk_id=row["chunk_id"],
                        title=row["title"],
                        heading_path=row["heading_path"],
                        ordinal=row["ordinal"],
                        source_path=row["source_path"],
                    )
                    self.chunks_by_id[row["chunk_id"]] = Chunk(
                        metadata=meta,
                        text=row["text"],
                        embedded_text=row["embedded_text"],
                    )
                    v = row["version"]
                    target_set = self.tokens_by_version.get(v, self.all_corpus_tokens)
                    text = row["text"]
                    for w in re.findall(r"[^\s]+", text):
                        cleaned = re.sub(r"^[(\'\"\`\[\{<]+|[)\'\"\`\]\}>.,?!;:]+$", "", w)
                        if cleaned:
                            target_set.add(cleaned.lower())
                            self.all_corpus_tokens.add(cleaned.lower())
                            if "/" in cleaned:
                                for part in cleaned.split("/"):
                                    if part:
                                        target_set.add(part.lower())
                                        self.all_corpus_tokens.add(part.lower())
                    for w in re.findall(r"[a-zA-Z0-9_\-\./:]+", text):
                        target_set.add(w.lower())
                        self.all_corpus_tokens.add(w.lower())
                        if "/" in w:
                            for part in w.split("/"):
                                if part:
                                    target_set.add(part.lower())
                                    self.all_corpus_tokens.add(part.lower())

        # 4. Compute document frequencies and IDF for relevance checking
        self.doc_count = len(self.chunks_by_id)
        self.df: Dict[str, int] = {}
        for chunk in self.chunks_by_id.values():
            search_space = f"{chunk.text} {chunk.metadata.title} {chunk.metadata.heading_path}".lower()
            tokens = set()
            for raw in re.findall(r"[a-zA-Z0-9_\-\./:]+", search_space):
                c = re.sub(r"^[^\w]+|[^\w]+$", "", raw)
                if c:
                    tokens.add(c)
                    tokens.add(light_stem(c))
                if "/" in raw:
                    for part in raw.split("/"):
                        p_clean = re.sub(r"^[^\w]+|[^\w]+$", "", part)
                        if p_clean:
                            tokens.add(p_clean)
                            tokens.add(light_stem(p_clean))
            for tok in tokens:
                self.df[tok] = self.df.get(tok, 0) + 1

    def get_idf(self, term: str) -> float:
        """Compute smooth BM25 IDF for a term (considering plural/singular variants)."""
        tl = term.lower()
        stem = light_stem(tl)
        variants = get_identifier_variants(term)
        cand_dfs = [self.df.get(tl, 0), self.df.get(stem, 0)] + [self.df.get(v, 0) for v in variants]
        df_val = max(cand_dfs)
        n = max(1, self.doc_count)
        return math.log(1.0 + (n - df_val + 0.5) / (df_val + 0.5))

    def compute_chunk_relevance(
        self,
        question: str,
        chunk: Chunk,
    ) -> Tuple[float, List[str], bool]:
        """Compute weighted coverage of question terms in a chunk (including title and heading_path).
        
        Returns:
            (coverage_score, missing_terms, all_identifiers_present)
        """
        identifiers, content_stems = extract_question_relevance_terms(question)
        search_space = f"{chunk.text} {chunk.metadata.title} {chunk.metadata.heading_path}".lower()
        
        # Check identifiers (plural/singular and case insensitive)
        missing_identifiers = []
        for id_tok in identifiers:
            id_vars = get_identifier_variants(id_tok)
            if not any(v in search_space for v in id_vars):
                missing_identifiers.append(id_tok)
        all_identifiers_present = len(missing_identifiers) == 0

        all_terms = list(identifiers) + list(content_stems)
        if not all_terms:
            return 1.0, [], True

        # Weight by IDF
        total_weight = 0.0
        covered_weight = 0.0
        missing_terms = list(missing_identifiers)

        for term in identifiers:
            weight = self.get_idf(term)
            total_weight += weight
            id_vars = get_identifier_variants(term)
            if any(v in search_space for v in id_vars):
                covered_weight += weight

        for stem in content_stems:
            weight = self.get_idf(stem)
            total_weight += weight
            stem_found = False
            for w in re.findall(r"[a-zA-Z0-9_\-\./:]+", search_space):
                clean_w = re.sub(r"^[^\w]+|[^\w]+$", "", w)
                if light_stem(clean_w) == stem or stem == clean_w:
                    stem_found = True
                    break
            if stem_found:
                covered_weight += weight
            else:
                missing_terms.append(stem)

        coverage = round(covered_weight / total_weight, 4) if total_weight > 0 else 1.0
        return coverage, missing_terms, all_identifiers_present

    def is_term_in_corpus(self, term: str, version: Optional[str] = None) -> bool:
        """Check if an identifier term (or any plural/singular variant) exists in the corpus (or targeted version)."""
        variants = get_identifier_variants(term)
        if version:
            v_clean = version.lstrip("v")
            if v_clean in self.tokens_by_version:
                if any(v in self.tokens_by_version[v_clean] for v in variants):
                    return True
                return any(any(v in c.text.lower() for v in variants) for c in self.chunks_by_id.values() if c.metadata.version == v_clean)
            return False
        if any(v in self.all_corpus_tokens for v in variants):
            return True
        return any(any(v in c.text.lower() for v in variants) for c in self.chunks_by_id.values())

    def retrieve(
        self,
        query: str,
        version: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Tuple[Chunk, float]]:
        """Retrieve top_k chunks per version or targeted version, then merge.
        
        Per decision:
        Both versions are always searched (top_k per version) unless the request has
        version='1.27'/'1.31' or the question names a version, in which case search only that one.
        """
        # Determine effective target version
        target_version = version or detect_version_in_text(query)

        # Clamp top_k to valid range
        clamped_k = max(1, min(20, top_k))

        # Truncate query if excessively long before embedding
        clean_query = query[:4000].strip()
        query_embedding = self.embed_model.encode(clean_query, normalize_embeddings=True).tolist()

        if target_version in ("1.27", "1.31"):
            # Single version search
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=clamped_k,
                where={"version": target_version},
            )
            return self._format_results(results, limit=clamped_k)
        else:
            # Search 1.27 and 1.31 separately (top_k per version), then merge
            res_127 = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=clamped_k,
                where={"version": "1.27"},
            )
            res_131 = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=clamped_k,
                where={"version": "1.31"},
            )

            list_127 = self._format_results(res_127, limit=clamped_k)
            list_131 = self._format_results(res_131, limit=clamped_k)

            # Guarantee version balance: include at least 2 from each version (if available)
            guaranteed_127 = list_127[:2]
            guaranteed_131 = list_131[:2]
            guaranteed_ids = {c.metadata.chunk_id for c, _ in (guaranteed_127 + guaranteed_131)}

            # Fill the rest from the remaining pool sorted by similarity score
            remaining_pool = [
                item for item in (list_127 + list_131)
                if item[0].metadata.chunk_id not in guaranteed_ids
            ]
            remaining_pool.sort(key=lambda item: item[1], reverse=True)

            total_target = clamped_k * 2
            needed = max(0, total_target - len(guaranteed_127) - len(guaranteed_131))
            combined = guaranteed_127 + guaranteed_131 + remaining_pool[:needed]

            # Sort merged results by similarity score descending
            combined.sort(key=lambda item: item[1], reverse=True)
            return combined

    def _format_results(self, raw_results: dict, limit: int) -> List[Tuple[Chunk, float]]:
        formatted: List[Tuple[Chunk, float]] = []
        if not raw_results or not raw_results.get("ids") or not raw_results["ids"][0]:
            return formatted

        ids = raw_results["ids"][0]
        distances = raw_results["distances"][0] if "distances" in raw_results else [0.0] * len(ids)

        for cid, dist in zip(ids, distances):
            if cid in self.chunks_by_id:
                # In Chroma with cosine space, distance is (1 - cosine_similarity).
                # Convert distance to similarity score: similarity = 1 - distance
                similarity = round(1.0 - float(dist), 4)
                formatted.append((self.chunks_by_id[cid], similarity))

        return formatted[:limit]
