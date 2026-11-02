"""FastAPI service exposing /healthz and /ask with strict edge-case handling."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from app.config import get_settings
from app.llm import (
    BaseLLMClient,
    FakeLLMClient,
    OllamaClient,
    build_retry_prompt,
    build_system_prompt,
    build_user_prompt,
    enforce_citations,
    parse_llm_json,
)
from app.retrieval import ChromaDenseRetriever, Retriever, extract_identifier_tokens
from app.schemas import AskResponse, HealthResponse

# Configure structured logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("rag-service")

# Global instances
retriever_instance: Optional[Retriever] = None
llm_client_instance: Optional[BaseLLMClient] = None


def get_llm_client() -> BaseLLMClient:
    """Retrieve active LLM client instance (defaults to OllamaClient)."""
    global llm_client_instance
    if llm_client_instance is None:
        llm_client_instance = OllamaClient()
    return llm_client_instance


def set_llm_client(client: Optional[BaseLLMClient]) -> None:
    """Inject custom or fake LLM client for tests."""
    global llm_client_instance
    llm_client_instance = client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models, index, and sidecar once at startup."""
    global retriever_instance, llm_client_instance
    logger.info("Initializing models and retriever on startup...")
    retriever_instance = ChromaDenseRetriever()
    if llm_client_instance is None:
        llm_client_instance = OllamaClient()
    logger.info(f"Retriever ready with {len(retriever_instance.chunks_by_id)} chunks indexed.")
    yield
    logger.info("Shutting down service.")


app = FastAPI(
    title="Kubernetes Dual-Version RAG API",
    lifespan=lifespan,
    docs_url=None,  # Minimal footprint
    redoc_url=None,
)


def is_non_english(text: str) -> bool:
    """Heuristic for detecting non-English queries (e.g. Hindi, French, Russian, Chinese)."""
    # 1. Non-Latin scripts (Devanagari, Cyrillic, CJK, Arabic, etc.)
    non_latin_pattern = re.compile(
        r"[\u0900-\u097F"  # Devanagari (Hindi)
        r"\u0400-\u04FF"  # Cyrillic
        r"\u4E00-\u9FFF"  # CJK Unified Ideographs
        r"\u0600-\u06FF]"  # Arabic
    )
    if non_latin_pattern.search(text):
        return True

    # 2. Common non-English Latin phrase markers (French, German, Spanish stopwords)
    lowered = text.lower()
    non_english_markers = [
        "qu'est-ce", "est-ce que", "comment fonctionne", "c'est quoi",
        "was ist", "wie funktioniert", "qué es", "cómo funciona",
    ]
    if any(m in lowered for m in non_english_markers):
        return True

    return False


NON_ANSWER_PATTERN = re.compile(
    r"(?:"
    r"(?:documentation|docs|corpus|kubernetes|kube-apiserver|api|spec)\b[^.!?\n]*?\b(?:does\s+not|doesn't|do\s+not)\s+(?:specify|state|mention|provide|document|recommend)\b|"
    r"\bnot\s+explicitly\s+stated\b|"
    r"\bno\s+fixed\s+\w+|"
    r"\b(?:is|are)\s+not\s+(?:mentioned|documented|specified|provided|stated)\b"
    r")",
    re.IGNORECASE,
)


def find_non_answer_sentence(text: str) -> Optional[str]:
    """Check if text contains a sentence stating documentation/Kubernetes does not specify/state/recommend/provide/mention.
    
    Returns the clean statement if found, else None.
    """
    if not text:
        return None
    for line in text.splitlines():
        for s in re.split(r"(?<=[.!?])\s+", line):
            s_clean = s.strip()
            if not s_clean:
                continue
            if NON_ANSWER_PATTERN.search(s_clean):
                clean_stmt = re.sub(r"\[[a-zA-Z0-9_\-\.:/#]+\]", "", s_clean).strip()
                return clean_stmt
    return None


def make_refusal_response(
    answer: str,
    reason: str,
    retrieved_chunk_ids: Optional[List[str]] = None,
    latency_ms: int = 0,
) -> JSONResponse:
    """Helper creating standard HTTP 200 refusal response with internal reason header."""
    resp = AskResponse(
        answer=answer,
        refused=True,
        citations=[],
        retrieved_chunk_ids=retrieved_chunk_ids or [],
        latency_ms=latency_ms,
    )
    headers = {"X-Refusal-Reason": reason}
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=resp.model_dump(),
        headers=headers,
    )


def log_debug_trace(
    question: Optional[str],
    request_body: Any,
    retrieved_chunk_ids: List[str],
    raw_llm_output: Optional[str],
    supported: Optional[bool],
    citations_info: List[Dict[str, Any]],
    sentences_pruned: List[str],
    final_answer: str,
    refusal_reason: Optional[str],
    latency_ms: int,
    chunks_sent_to_llm: int = 0,
    prompt_tokens_sent_to_llm: int = 0,
    retrieval_ms: int = 0,
    llm_ms: int = 0,
    sentence_support: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Print detailed per-request trace if DEBUG_TRACE=1 is enabled."""
    if os.environ.get("DEBUG_TRACE") != "1":
        return
    print("\n" + "=" * 30 + " DEBUG TRACE " + "=" * 30)
    print(f"question: {question}")
    print(f"request body: {json.dumps(request_body, ensure_ascii=False) if isinstance(request_body, dict) else str(request_body)}")
    print(f"retrieved_chunk_ids: {retrieved_chunk_ids}")
    print(f"chunks sent to LLM: {chunks_sent_to_llm} (cap: at most 6)")
    print(f"prompt tokens sent to LLM: {prompt_tokens_sent_to_llm}")
    print(f"latency breakdown: retrieval={retrieval_ms}ms, llm={llm_ms}ms, total={latency_ms}ms")
    print(f"raw LLM output: {raw_llm_output}")
    print(f"supported flag: {supported}")
    if sentence_support:
        print("sentence attribution & support breakdown:")
        for s in sentence_support:
            print(f"  - model_marker={s.get('model_marker')} -> [{s.get('attributed_chunk')}] support={s.get('support')} ({s.get('status')}): {repr(s.get('sentence'))}")
    print(f"citations: ({len(citations_info)})")
    for c in citations_info:
        print(f"  - chunk_id: {c.get('chunk_id')}, verified: {c.get('verified')}, repaired: {c.get('repaired')}, dropped reason: {c.get('dropped_reason')}")
        print(f"    quote: {repr(c.get('quote'))}")
    print(f"sentences pruned: {sentences_pruned}")
    print(f"final answer: {final_answer}")
    print(f"refusal reason: {refusal_reason}")
    print(f"latency_ms: {latency_ms}")
    print("=" * 73 + "\n", flush=True)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Ensure invalid or missing fields return HTTP 200 with standard refusal schema."""
    logger.warning(f"Request validation error on {request.url.path}: {exc}")
    return make_refusal_response(
        answer=f"Invalid request format: {exc.errors()[0].get('msg', 'invalid fields')}",
        reason="language/empty input",
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Ensure any unexpected server error returns HTTP 200 with standard refusal schema."""
    logger.exception(f"Unhandled exception on {request.url.path}: {exc}")
    return make_refusal_response(
        answer=f"Internal error: {exc}",
        reason="internal_error",
    )


@app.get("/", response_class=FileResponse)
async def get_ui():
    """Serve minimal static web UI."""
    index_file = Path(__file__).resolve().parent / "static" / "index.html"
    return FileResponse(index_file, media_type="text/html")


@app.get("/healthz", response_model=HealthResponse)
async def healthz():
    """Liveness and readiness probe."""
    is_ready = bool(retriever_instance and len(retriever_instance.chunks_by_id) > 0)
    return HealthResponse(
        status="ok" if is_ready else "starting",
        version="1.0.0",
        index_ready=is_ready,
    )


@app.post("/ask", response_model=AskResponse)
async def ask(request: Request):
    """Answer questions against Kubernetes v1.27 and v1.31 documentation."""
    start_time = time.perf_counter()
    request.app.state.last_raw_llm = "<SKIPPED: Refused before generation>"
    data: Dict[str, Any] = {}
    question: Optional[str] = None
    retrieved_chunk_ids: List[str] = []
    trace_details: Dict[str, Any] = {}

    def emit_trace(
        final_ans: str,
        refusal_rsn: Optional[str],
        citations_list: List[Dict[str, Any]],
        sentences_pruned_list: List[str],
        supported_flag: Optional[bool],
        raw_llm: Optional[str],
        latency: int,
        chunks_sent: int = 0,
        tokens_sent: int = 0,
        ret_ms: int = 0,
        l_ms: int = 0,
        support_breakdown: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        trace_data = {
            "question": question,
            "request_body": data,
            "retrieved_chunk_ids": retrieved_chunk_ids,
            "raw_llm_output": raw_llm,
            "supported": supported_flag,
            "citations": citations_list,
            "sentences_pruned": sentences_pruned_list,
            "final_answer": final_ans,
            "refusal_reason": refusal_rsn,
            "latency_ms": latency,
            "chunks_sent_to_llm": chunks_sent,
            "prompt_tokens_sent_to_llm": tokens_sent,
            "retrieval_ms": ret_ms,
            "llm_ms": l_ms,
            "sentence_support": support_breakdown,
            "best_relevance_coverage": trace_details.get("best_relevance_coverage"),
            "best_similarity": trace_details.get("best_similarity", 0.0),
            "initial_attempt": trace_details.get("initial_attempt"),
            "retry_attempt": trace_details.get("retry_attempt"),
        }
        request.app.state.last_trace = trace_data
        log_debug_trace(
            question=question,
            request_body=data,
            retrieved_chunk_ids=retrieved_chunk_ids,
            raw_llm_output=raw_llm,
            supported=supported_flag,
            citations_info=citations_list,
            sentences_pruned=sentences_pruned_list,
            final_answer=final_ans,
            refusal_reason=refusal_rsn,
            latency_ms=latency,
            chunks_sent_to_llm=chunks_sent,
            prompt_tokens_sent_to_llm=tokens_sent,
            retrieval_ms=ret_ms,
            llm_ms=l_ms,
            sentence_support=support_breakdown,
        )

    # 1. Parse body and catch malformed JSON
    try:
        body_bytes = await request.body()
        if not body_bytes:
            emit_trace("Request body cannot be empty.", "language/empty input", [], [], None, None, 0)
            return make_refusal_response(
                answer="Request body cannot be empty.",
                reason="language/empty input",
                latency_ms=0,
            )
        data = json.loads(body_bytes.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Root payload must be a JSON object.")
    except Exception as e:
        logger.warning(f"Malformed JSON payload: {e}")
        emit_trace("Malformed JSON payload in request.", "language/empty input", [], [], None, None, 0)
        return make_refusal_response(
            answer="Malformed JSON payload in request.",
            reason="language/empty input",
            latency_ms=0,
        )

    # 2. Extract and validate question
    raw_question = data.get("question")
    if raw_question is None or not isinstance(raw_question, str) or not raw_question.strip():
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        emit_trace("Question cannot be empty or whitespace.", "language/empty input", [], [], None, None, elapsed_ms)
        return make_refusal_response(
            answer="Question cannot be empty or whitespace.",
            reason="language/empty input",
            latency_ms=elapsed_ms,
        )

    # 3. Truncate question if 4000+ characters before embedding
    question = raw_question.strip()
    if len(question) > 4000:
        question = question[:4000]

    # 4. Check non-English heuristic
    if is_non_english(question):
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        emit_trace("Non-English questions are not supported.", "language/empty input", [], [], None, None, elapsed_ms)
        return make_refusal_response(
            answer="Non-English questions are not supported.",
            reason="language/empty input",
            latency_ms=elapsed_ms,
        )

    # 5. Extract and clamp top_k (1..20)
    raw_top_k = data.get("top_k", 5)
    try:
        top_k = int(raw_top_k)
        top_k = max(1, min(20, top_k))
    except (ValueError, TypeError):
        top_k = 5

    # 6. Extract version constraint if provided
    raw_version = data.get("version")
    version: Optional[str] = None
    if raw_version:
        v_clean = str(raw_version).strip().lstrip("v")
        if v_clean in ("1.27", "1.31"):
            version = v_clean

    global retriever_instance
    if retriever_instance is None:
        retriever_instance = ChromaDenseRetriever()

    # Step 4: False premise check on extracted identifier tokens
    identifiers = extract_identifier_tokens(question)
    for term in identifiers:
        if version:
            if not retriever_instance.is_term_in_corpus(term, version=version):
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                ans = f"The term '{term}' is not documented in the Kubernetes {version} documentation covered by this corpus."
                emit_trace(ans, "false_premise", [], [], None, None, elapsed_ms)
                return make_refusal_response(
                    answer=ans,
                    reason="false_premise",
                    retrieved_chunk_ids=[],
                    latency_ms=elapsed_ms,
                )
        else:
            if not retriever_instance.is_term_in_corpus(term, version=None):
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                ans = f"The term '{term}' is not documented in the Kubernetes 1.27 or 1.31 documentation covered by this corpus."
                emit_trace(ans, "false_premise", [], [], None, None, elapsed_ms)
                return make_refusal_response(
                    answer=ans,
                    reason="false_premise",
                    retrieved_chunk_ids=[],
                    latency_ms=elapsed_ms,
                )

    # 7. Execute retrieval
    t_ret_start = time.perf_counter()
    results = retriever_instance.retrieve(query=question, version=version, top_k=top_k)
    retrieval_ms = int((time.perf_counter() - t_ret_start) * 1000)
    retrieved_chunk_ids = [c.metadata.chunk_id for c, _ in results]
    retrieved_chunks = [c for c, _ in results]
    scores = [score for _, score in results]
    best_score = max(scores) if scores else 0.0
    trace_details["best_similarity"] = best_score

    settings = get_settings()

    # Refusal: Score below REFUSE_MIN_SCORE
    if not results or best_score < settings.REFUSE_MIN_SCORE:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        target_version_str = f"Kubernetes {version}" if version else "Kubernetes 1.27 and 1.31"
        ans = f"The retrieved documentation for {target_version_str} does not contain sufficient confidence to answer this question."
        emit_trace(ans, "weak_retrieval", [], [], None, None, elapsed_ms, ret_ms=retrieval_ms)
        return make_refusal_response(
            answer=ans,
            reason="weak_retrieval",
            retrieved_chunk_ids=retrieved_chunk_ids,
            latency_ms=elapsed_ms,
        )

    # Step 6: Cap chunks sent to LLM at most 6
    llm_chunks = retrieved_chunks[:6]

    # LLM Generation
    client_llm = get_llm_client()
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(question, llm_chunks)

    prompt_tokens = 0
    try:
        prompt_tokens = len(retriever_instance.embed_model.tokenizer.encode(system_prompt + "\n" + user_prompt))
    except Exception:
        prompt_tokens = len((system_prompt + "\n" + user_prompt).split())

    raw_llm_out: Optional[str] = None
    t_llm_start = time.perf_counter()
    try:
        raw_llm_out = client_llm.generate(prompt=user_prompt, system=system_prompt)
        llm_ms = int((time.perf_counter() - t_llm_start) * 1000)
        request.app.state.last_raw_llm = raw_llm_out
    except Exception as exc:
        llm_ms = int((time.perf_counter() - t_llm_start) * 1000)
        request.app.state.last_raw_llm = f"<EXCEPTION: {exc}>"
        logger.exception(f"LLM generation unavailable or timed out: {exc}")
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        ans = f"Internal error: LLM generation unavailable: {exc}"
        emit_trace(ans, "internal_error", [], [], None, str(exc), elapsed_ms, chunks_sent=len(llm_chunks), tokens_sent=prompt_tokens, ret_ms=retrieval_ms, l_ms=llm_ms)
        return make_refusal_response(
            answer=ans,
            reason="internal_error",
            retrieved_chunk_ids=retrieved_chunk_ids,
            latency_ms=elapsed_ms,
        )

    # Robust JSON parsing
    parsed = parse_llm_json(raw_llm_out, client=client_llm)
    if not parsed:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        emit_trace(
            "Failed to parse structured JSON from model generation.",
            "no_valid_citation",
            [],
            [],
            None,
            raw_llm_out,
            elapsed_ms,
            chunks_sent=len(llm_chunks),
            tokens_sent=prompt_tokens,
            ret_ms=retrieval_ms,
            l_ms=llm_ms,
        )
        return make_refusal_response(
            answer="Failed to parse structured JSON from model generation.",
            reason="no_valid_citation",
            retrieved_chunk_ids=retrieved_chunk_ids,
            latency_ms=elapsed_ms,
        )

    target_version_str = f"Kubernetes {version}" if version else "Kubernetes 1.27 or 1.31"
    clean_answer = ""
    valid_citations = []
    is_supported = False
    raw_answer = str(parsed.get("answer", ""))

    # Check if model returned supported=false
    if not parsed.get("supported", False):
        # A2. Retry once if relevance check passes on top retrieved chunks with all identifiers present
        top_cand_chunks = llm_chunks[:3]
        can_retry = False
        if hasattr(retriever_instance, "compute_chunk_relevance"):
            for cand in top_cand_chunks:
                cov, _, ids_present = retriever_instance.compute_chunk_relevance(question, cand)
                if ids_present and cov >= settings.REL_MIN_COVERAGE:
                    can_retry = True
                    break

        if can_retry:
            logger.info("A2 Retry triggered: supported=false but top retrieved chunk passed relevance check.")
            retry_prompt = build_retry_prompt(question, top_cand_chunks)
            t_retry_start = time.perf_counter()
            try:
                retry_raw = client_llm.generate(prompt=retry_prompt)
                retry_llm_ms = int((time.perf_counter() - t_retry_start) * 1000)
                llm_ms += retry_llm_ms
                trace_details["initial_attempt"] = raw_llm_out
                trace_details["retry_attempt"] = retry_raw
                raw_llm_out = f"Initial: {raw_llm_out}\nRetry: {retry_raw}"

                # Enforce citations on retry plain-text output
                raw_answer = retry_raw
                clean_answer, valid_citations, is_supported = enforce_citations(
                    raw_answer=retry_raw,
                    retrieved_chunks_or_raw_citations=top_cand_chunks,
                    trace_details=trace_details,
                )
            except Exception as exc:
                logger.warning(f"Retry generation failed: {exc}")
                is_supported = False
        else:
            is_supported = False

        if not is_supported or not valid_citations:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            ans = f"The {target_version_str} documentation covered by this corpus does not provide sufficient documented information to answer this question."
            emit_trace(
                ans,
                "model_unsupported",
                [],
                [],
                False,
                raw_llm_out,
                elapsed_ms,
                chunks_sent=len(llm_chunks),
                tokens_sent=prompt_tokens,
                ret_ms=retrieval_ms,
                l_ms=llm_ms,
            )
            return make_refusal_response(
                answer=ans,
                reason="model_unsupported",
                retrieved_chunk_ids=retrieved_chunk_ids,
                latency_ms=elapsed_ms,
            )
    else:
        # Enforce citations in code with sentence support on initial answer
        raw_answer = str(parsed.get("answer", ""))
        clean_answer, valid_citations, is_supported = enforce_citations(
            raw_answer=raw_answer,
            retrieved_chunks_or_raw_citations=llm_chunks,
            trace_details=trace_details,
        )

    # Step 7.1: Non-answer rule: documentation/Kubernetes does not specify/state/recommend/provide/mention
    non_ans_stmt = find_non_answer_sentence(clean_answer) or find_non_answer_sentence(raw_answer)
    if non_ans_stmt:
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        emit_trace(
            non_ans_stmt,
            "model_nonanswer",
            [],
            trace_details.get("sentences_pruned", []),
            False,
            raw_llm_out,
            elapsed_ms,
            chunks_sent=len(llm_chunks),
            tokens_sent=prompt_tokens,
            ret_ms=retrieval_ms,
            l_ms=llm_ms,
            support_breakdown=trace_details.get("sentence_support", []),
        )
        return make_refusal_response(
            answer=non_ans_stmt,
            reason="model_nonanswer",
            retrieved_chunk_ids=retrieved_chunk_ids,
            latency_ms=elapsed_ms,
        )

    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
    sentence_support = trace_details.get("sentence_support", [])

    if not is_supported or not valid_citations:
        ans = f"The {target_version_str} documentation covered by this corpus does not provide sufficient verified citations to answer this question."
        emit_trace(
            ans,
            "no_valid_citation",
            trace_details.get("citations", []),
            trace_details.get("sentences_pruned", []),
            parsed.get("supported"),
            raw_llm_out,
            elapsed_ms,
            chunks_sent=len(llm_chunks),
            tokens_sent=prompt_tokens,
            ret_ms=retrieval_ms,
            l_ms=llm_ms,
            support_breakdown=sentence_support,
        )
        return make_refusal_response(
            answer=ans,
            reason="no_valid_citation",
            retrieved_chunk_ids=retrieved_chunk_ids,
            latency_ms=elapsed_ms,
        )

    # A3. Question-Relevance Check on cited chunks:
    # Coverage = weighted fraction of question's terms found in ONE cited chunk. All identifiers must be present.
    if hasattr(retriever_instance, "compute_chunk_relevance"):
        has_relevant_chunk = False
        best_missing_terms: List[str] = []
        best_cov = 0.0
        for cit in valid_citations:
            cid = cit.chunk_id
            chunk_obj = getattr(retriever_instance, "chunks_by_id", {}).get(cid)
            if not chunk_obj:
                # Fallback to prompt chunks
                chunk_obj = next((c for c in llm_chunks if c.metadata.chunk_id == cid), None)
            if chunk_obj:
                cov, missing, ids_present = retriever_instance.compute_chunk_relevance(question, chunk_obj)
                if cov > best_cov:
                    best_cov = cov
                    best_missing_terms = missing
                if ids_present and cov >= settings.REL_MIN_COVERAGE:
                    has_relevant_chunk = True
                    break

        trace_details["best_relevance_coverage"] = best_cov
        if not has_relevant_chunk:
            missing_desc = f": {', '.join(best_missing_terms)}" if best_missing_terms else ""
            ans = f"The {target_version_str} documentation covered by this corpus does not provide relevant evidence for the question{missing_desc}."
            emit_trace(
                ans,
                "irrelevant_evidence",
                trace_details.get("citations", []),
                trace_details.get("sentences_pruned", []),
                parsed.get("supported"),
                raw_llm_out,
                elapsed_ms,
                chunks_sent=len(llm_chunks),
                tokens_sent=prompt_tokens,
                ret_ms=retrieval_ms,
                l_ms=llm_ms,
                support_breakdown=sentence_support,
            )
            return make_refusal_response(
                answer=ans,
                reason="irrelevant_evidence",
                retrieved_chunk_ids=retrieved_chunk_ids,
                latency_ms=elapsed_ms,
            )

    emit_trace(
        clean_answer,
        None,
        trace_details.get("citations", []),
        trace_details.get("sentences_pruned", []),
        parsed.get("supported"),
        raw_llm_out,
        elapsed_ms,
        chunks_sent=len(llm_chunks),
        tokens_sent=prompt_tokens,
        ret_ms=retrieval_ms,
        l_ms=llm_ms,
        support_breakdown=sentence_support,
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=AskResponse(
            answer=clean_answer,
            refused=False,
            citations=valid_citations,
            retrieved_chunk_ids=retrieved_chunk_ids,
            latency_ms=elapsed_ms,
        ).model_dump(),
    )
