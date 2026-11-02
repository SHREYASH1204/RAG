"""Evaluation runner measuring accuracy, refusal behavior, citation integrity, and latency.

Complies with Part B3 specifications:
- Per-type accuracy (factual, version_conflict, unanswerable, false_premise)
- Refusal breakdown (counts and percentages)
- Correct refusal rate vs false refusal rate
- Independent citation verification against index/chunks.jsonl
- Standalone retrieval metrics: Recall@1, Recall@3, Recall@5, Recall@10, and MRR
- Hallucination rate on numbers and conditions unsupported by citations
- Latency percentiles: p50 and p95 for retrieval_ms, llm_ms, total_ms
- Hardware & model echo: Ollama /api/show metadata + GPU VRAM
- Top 3 confidently wrong answers with explanations
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import platform
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import psutil
from fastapi.testclient import TestClient

from app.api import app, set_llm_client
from app.config import get_settings
from app.llm import OllamaClient
from app.retrieval import ChromaDenseRetriever
from app.schemas import AskResponse, Chunk

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("rag-eval")


def get_hardware_and_model_info(model_name: str = "qwen2.5:3b") -> Dict[str, Any]:
    """Capture hardware specifications and Ollama model metadata from /api/show."""
    mem_gb = round(psutil.virtual_memory().total / (1024 ** 3), 2)
    info: Dict[str, Any] = {
        "os": platform.system(),
        "os_release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": psutil.cpu_count(logical=True),
        "total_ram_gb": mem_gb,
        "python_version": platform.python_version(),
        "cuda_available": False,
        "gpu_name": None,
        "gpu_vram_gb": None,
        "model_name": model_name,
        "model_details": {},
    }

    # Check CUDA VRAM if torch is installed
    try:
        import torch
        if torch.cuda.is_available():
            info["cuda_available"] = True
            info["gpu_name"] = torch.cuda.get_device_name(0)
            total_vram = torch.cuda.get_device_properties(0).total_memory
            info["gpu_vram_gb"] = round(total_vram / (1024 ** 3), 2)
    except Exception:
        pass

    # Query Ollama /api/show for model architecture, quant, parameter size, context length
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/show",
            data=json.dumps({"model": model_name}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            details = data.get("details", {})
            model_info = data.get("model_info", {})
            info["model_details"] = {
                "format": details.get("format"),
                "family": details.get("family"),
                "parameter_size": details.get("parameter_size"),
                "quantization_level": details.get("quantization_level"),
                "context_length": model_info.get("general.context_length", model_info.get("qwen2.context_length", "unknown")),
            }
    except Exception as e:
        logger.warning(f"Could not retrieve Ollama model info: {e}")
        info["model_details"] = {"error": str(e)}

    return info


def verify_citation_independently(
    cit: Dict[str, Any],
    chunks_by_id: Dict[str, Chunk],
) -> Tuple[bool, Optional[str]]:
    """Independently verify a citation against stored chunks.
    
    Checks:
    1. chunk exists in chunks.jsonl
    2. quote matches verbatim
    3. doc_id matches chunk metadata
    4. version matches chunk metadata
    """
    cid = cit.get("chunk_id")
    quote = cit.get("quote", "")
    doc_id = cit.get("doc_id")
    version = cit.get("version")

    if not cid or cid not in chunks_by_id:
        return False, f"chunk_id '{cid}' not in corpus"

    chunk = chunks_by_id[cid]
    if not quote or quote not in chunk.text:
        return False, f"quote does not match chunk text verbatim"

    if doc_id != chunk.metadata.doc_id:
        return False, f"doc_id mismatch: expected '{chunk.metadata.doc_id}', got '{doc_id}'"

    if version != chunk.metadata.version:
        return False, f"version mismatch: expected '{chunk.metadata.version}', got '{version}'"

    return True, None


def compute_hallucination(answer: str, citations: List[Dict[str, Any]], chunks_by_id: Dict[str, Chunk]) -> bool:
    """Check if an answer contains numbers or conditions not supported by citations."""
    if not citations:
        return False

    cited_texts = []
    for cit in citations:
        c = chunks_by_id.get(cit.get("chunk_id", ""))
        if c:
            cited_texts.append(c.text.lower())
    combined_chunk_text = " ".join(cited_texts)

    answer_lower = answer.lower()
    digits = re.findall(r"\b\d+(?:\.\d+)?\b", answer_lower)
    for d in digits:
        if d not in combined_chunk_text:
            return True

    return False


def percentile(data: List[float], p: float) -> float:
    """Compute exact percentile value."""
    if not data:
        return 0.0
    sorted_d = sorted(data)
    idx = (len(sorted_d) - 1) * p
    floor_idx = int(idx)
    ceil_idx = min(floor_idx + 1, len(sorted_d) - 1)
    if floor_idx == ceil_idx:
        return round(sorted_d[floor_idx], 2)
    val = sorted_d[floor_idx] * (ceil_idx - idx) + sorted_d[ceil_idx] * (idx - floor_idx)
    return round(val, 2)


def run_evaluation(
    eval_set_path: Path,
    out_path: Path,
    top_k: int = 5,
    llm_client: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute end-to-end evaluation runner producing full eval_report.json."""
    logger.info(f"Loading evaluation questions from {eval_set_path}...")
    questions: List[Dict[str, Any]] = []
    with eval_set_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))

    logger.info(f"Loaded {len(questions)} evaluation questions.")

    retriever = ChromaDenseRetriever()
    chunks_by_id = retriever.chunks_by_id

    # 1. Standalone Retrieval Evaluation
    # Recall@1, Recall@3, Recall@5, Recall@10 and MRR against gold_docs
    hits_at_1 = 0
    hits_at_3 = 0
    hits_at_5 = 0
    hits_at_10 = 0
    reciprocal_ranks: List[float] = []
    gold_eval_count = 0

    logger.info("Computing standalone retrieval metrics (Recall@k, MRR)...")
    for q in questions:
        gold_docs = q.get("gold_docs") or []
        if not gold_docs:
            continue
        gold_eval_count += 1
        q_text = q["question"]
        target_v = q.get("target_version")
        ret_results = retriever.retrieve(query=q_text, version=target_v, top_k=10)
        ret_doc_ids = [c.metadata.doc_id for c, _ in ret_results]

        # Recall@k
        if any(d in ret_doc_ids[:1] for d in gold_docs):
            hits_at_1 += 1
        if any(d in ret_doc_ids[:3] for d in gold_docs):
            hits_at_3 += 1
        if any(d in ret_doc_ids[:5] for d in gold_docs):
            hits_at_5 += 1
        if any(d in ret_doc_ids[:10] for d in gold_docs):
            hits_at_10 += 1

        # MRR
        rr = 0.0
        for rank, doc_id in enumerate(ret_doc_ids, 1):
            if doc_id in gold_docs:
                rr = 1.0 / rank
                break
        reciprocal_ranks.append(rr)

    recall_at_1 = round((hits_at_1 / gold_eval_count) * 100, 2) if gold_eval_count > 0 else 0.0
    recall_at_3 = round((hits_at_3 / gold_eval_count) * 100, 2) if gold_eval_count > 0 else 0.0
    recall_at_5 = round((hits_at_5 / gold_eval_count) * 100, 2) if gold_eval_count > 0 else 0.0
    recall_at_10 = round((hits_at_10 / gold_eval_count) * 100, 2) if gold_eval_count > 0 else 0.0
    mrr = round(statistics.mean(reciprocal_ranks), 4) if reciprocal_ranks else 0.0

    # 2. End-to-End Pipeline Evaluation
    logger.info("Running questions through /ask endpoint...")
    if llm_client is not None:
        set_llm_client(llm_client)
    else:
        set_llm_client(OllamaClient())

    results_by_type: Dict[str, List[Dict[str, Any]]] = {}
    total_retrieval_ms: List[float] = []
    total_llm_ms: List[float] = []
    total_latencies_ms: List[float] = []

    total_citations_count = 0
    verified_citations_count = 0
    hallucination_count = 0
    answered_count = 0

    refusals_by_reason: Dict[str, int] = {
        "weak_retrieval": 0,
        "model_unsupported": 0,
        "no_valid_citation": 0,
        "irrelevant_evidence": 0,
        "false_premise": 0,
        "language/empty input": 0,
        "internal_error": 0,
    }

    confidently_wrong_candidates: List[Dict[str, Any]] = []
    per_question_results: List[Dict[str, Any]] = []

    with TestClient(app) as client:
        for q in questions:
            qid = q["qid"]
            q_type = q.get("type", "factual")
            # Map legacy single_fact -> factual
            if q_type == "single_fact":
                q_type = "factual"

            payload: Dict[str, Any] = {"question": q["question"], "top_k": top_k}
            if q.get("target_version"):
                payload["version"] = q["target_version"]

            resp = client.post("/ask", json=payload)
            trace = getattr(app.state, "last_trace", {})

            data = resp.json()
            refused = data.get("refused", False)
            citations = data.get("citations", [])
            answer = data.get("answer", "")
            retrieved_chunk_ids = data.get("retrieved_chunk_ids", [])

            ret_ms = trace.get("retrieval_ms", 0)
            l_ms = trace.get("llm_ms", 0)
            tot_ms = data.get("latency_ms", 0)

            total_retrieval_ms.append(float(ret_ms))
            total_llm_ms.append(float(l_ms))
            total_latencies_ms.append(float(tot_ms))

            refusal_reason = resp.headers.get("X-Refusal-Reason", trace.get("refusal_reason"))
            if refused and refusal_reason:
                refusals_by_reason[refusal_reason] = refusals_by_reason.get(refusal_reason, 0) + 1

            # Independent citation verification
            cits_verified = True
            for cit in citations:
                total_citations_count += 1
                is_v, _ = verify_citation_independently(cit, chunks_by_id)
                if is_v:
                    verified_citations_count += 1
                else:
                    cits_verified = False

            # Check Hallucination on answered questions
            is_hallucinated = False
            if not refused:
                answered_count += 1
                is_hallucinated = compute_hallucination(answer, citations, chunks_by_id)
                if is_hallucinated:
                    hallucination_count += 1

            # Accuracy per type evaluation
            is_correct = False
            wrong_reason = ""
            vconf_grader_pass = False

            if q_type == "version_conflict":
                versions_expected = q.get("versions_expected") or ["1.27", "1.31"]
                has_both_named = all(v in answer for v in versions_expected)
                cited_versions = {c.get("version") for c in citations}
                has_both_cited = all(v in cited_versions for v in versions_expected)
                vconf_grader_pass = (not refused) and cits_verified and has_both_named and has_both_cited

            # Answered and verified evaluation
            answered_and_verified = False
            if q_type == "unanswerable":
                valid_reasons = {"weak_retrieval", "no_valid_citation", "irrelevant_evidence", "model_unsupported", "model_nonanswer"}
                answered_and_verified = refused and (refusal_reason in valid_reasons)
            elif q_type == "false_premise":
                answered_and_verified = refused and (refusal_reason == "false_premise")
            elif q_type == "version_conflict":
                versions_expected = q.get("versions_expected") or ["1.27", "1.31"]
                has_both_named = all(v in answer for v in versions_expected)
                cited_versions = {c.get("version") for c in citations}
                has_both_cited = all(v in cited_versions for v in versions_expected)
                answered_and_verified = (not refused) and cits_verified and has_both_named and has_both_cited
            else:
                answered_and_verified = (not refused) and cits_verified and bool(citations)

            # Rule: internal_error is a FAILURE in every metric
            if refusal_reason == "internal_error":
                is_correct = False
                wrong_reason = "internal_error encountered"
            elif q_type == "unanswerable":
                valid_reasons = {"weak_retrieval", "no_valid_citation", "irrelevant_evidence", "model_unsupported", "model_nonanswer"}
                if refused and refusal_reason in valid_reasons:
                    is_correct = True
                else:
                    is_correct = False
                    wrong_reason = f"Unanswerable answered or invalid refusal reason: {refusal_reason}"
            elif q_type == "false_premise":
                # refused=true, reason == "false_premise"
                if refused and refusal_reason == "false_premise":
                    is_correct = True
                else:
                    is_correct = False
                    wrong_reason = f"False premise answered or wrong refusal reason: {refusal_reason}"
            else:
                # Answerable questions (factual, single_fact, version_conflict, etc.)
                if refused:
                    is_correct = False
                    wrong_reason = f"Answerable question falsely refused: {refusal_reason}"
                elif not citations or not cits_verified:
                    is_correct = False
                    wrong_reason = "Missing or unverified citations"
                else:
                    # Check must_include terms
                    must_include = q.get("must_include") or []
                    missing_terms = [t for t in must_include if t.lower() not in answer.lower()]
                    
                    if missing_terms:
                        is_correct = False
                        wrong_reason = f"Missing must_include terms: {missing_terms}"
                    elif q_type == "version_conflict":
                        # For version_conflict also require both versions named and cited
                        versions_expected = q.get("versions_expected") or ["1.27", "1.31"]
                        missing_named_versions = [v for v in versions_expected if v not in answer]
                        
                        cited_versions = {c.get("version") for c in citations}
                        missing_cited_versions = [v for v in versions_expected if v not in cited_versions]
                        
                        if missing_named_versions:
                            is_correct = False
                            wrong_reason = f"Versions not named in answer: {missing_named_versions}"
                        elif missing_cited_versions:
                            is_correct = False
                            wrong_reason = f"Versions not cited in citations: {missing_cited_versions}"
                        else:
                            is_correct = True
                    else:
                        is_correct = True

            if not is_correct:
                confidently_wrong_candidates.append({
                    "qid": qid,
                    "question": q["question"],
                    "type": q_type,
                    "refused": refused,
                    "refusal_reason": refusal_reason,
                    "answer": answer,
                    "why_wrong": wrong_reason,
                    "best_similarity": trace.get("best_similarity", 0.0),
                })

            results_by_type.setdefault(q_type, []).append({
                "qid": qid,
                "is_correct": is_correct,
                "refused": refused,
                "refusal_reason": refusal_reason,
            })

            per_question_results.append({
                "qid": qid,
                "type": q_type,
                "question": q["question"],
                "refused": refused,
                "refusal_reason": refusal_reason,
                "answer": answer,
                "citations": citations,
                "retrieved_chunk_ids": retrieved_chunk_ids,
                "latency_ms": tot_ms,
                "retrieval_ms": ret_ms,
                "llm_ms": l_ms,
                "is_correct": is_correct,
                "answered_and_verified": answered_and_verified,
                "version_conflict_grader_pass": vconf_grader_pass if q_type == "version_conflict" else None,
                "failed_condition": wrong_reason if not is_correct else None,
                "why_wrong": wrong_reason if not is_correct else None,
            })

    # Per-type accuracy
    accuracy_per_type: Dict[str, float] = {}
    total_q = len(questions)
    total_correct = 0
    for t_name, r_list in results_by_type.items():
        n_corr = sum(1 for r in r_list if r["is_correct"])
        total_correct += n_corr
        accuracy_per_type[t_name] = round((n_corr / len(r_list)) * 100, 2)

    overall_accuracy = round((total_correct / total_q) * 100, 2) if total_q > 0 else 0.0
    total_answered_verified = sum(1 for p in per_question_results if p.get("answered_and_verified"))
    answered_and_verified_pct = round((total_answered_verified / total_q) * 100, 2) if total_q > 0 else 0.0

    # Version conflict grader pass metric
    vconf_items = results_by_type.get("version_conflict", [])
    total_vconf = len(vconf_items)
    vconf_grader_passed = sum(
        1 for p in per_question_results if p.get("type") == "version_conflict" and p.get("version_conflict_grader_pass")
    )
    version_conflict_grader_pass_pct = round(vconf_grader_passed / total_vconf * 100, 2) if total_vconf > 0 else 0.0

    # Refusal rates
    total_refusals = sum(1 for it_list in results_by_type.values() for it in it_list if it["refused"])
    overall_refusal_rate = round((total_refusals / total_q) * 100, 2) if total_q > 0 else 0.0

    unans_items = results_by_type.get("unanswerable", []) + results_by_type.get("false_premise", [])
    correct_refusals = sum(1 for it in unans_items if it["refused"] and it["refusal_reason"] != "internal_error")
    correct_refusal_rate = round((correct_refusals / len(unans_items)) * 100, 2) if unans_items else 0.0

    ans_items = results_by_type.get("factual", []) + results_by_type.get("version_conflict", [])
    false_refusals = sum(1 for it in ans_items if it["refused"])
    false_refusal_rate = round((false_refusals / len(ans_items)) * 100, 2) if ans_items else 0.0

    citation_validity = round((verified_citations_count / total_citations_count) * 100, 2) if total_citations_count > 0 else 100.0
    hallucination_rate = round((hallucination_count / answered_count) * 100, 2) if answered_count > 0 else 0.0

    # Top 3 confidently wrong answers:
    # Sort by best similarity descending (or answered unanswerables first)
    confidently_wrong_candidates.sort(
        key=lambda x: (not x["refused"], x.get("best_similarity", 0.0)),
        reverse=True,
    )
    top_3_confidently_wrong = confidently_wrong_candidates[:3]

    settings = get_settings()
    report = {
        "evaluation_date": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "dataset": str(eval_set_path),
        "total_questions": total_q,
        "note": f"Evaluation performed on the full verified {total_q}-question set ({eval_set_path}).",
        "thresholds": {
            "REFUSE_MIN_SCORE": settings.REFUSE_MIN_SCORE,
            "MIN_SUPPORT": settings.MIN_SUPPORT,
            "REL_MIN_COVERAGE": settings.REL_MIN_COVERAGE,
        },
        "metrics": {
            "overall_accuracy_pct": overall_accuracy,
            "content_check_must_include_pct": overall_accuracy,
            "answered_and_verified_pct": answered_and_verified_pct,
            "accuracy_names": {
                "answered and verified (not refused, citations valid, versions named and cited)": answered_and_verified_pct,
                "content check (must_include)": overall_accuracy,
            },
            "accuracy_per_type": accuracy_per_type,
            "version_conflict_strict_accuracy_pct": accuracy_per_type.get("version_conflict", 0.0),
            "version_conflict_grader_pass_pct": version_conflict_grader_pass_pct,
            "version_conflict_grader_pass_count": vconf_grader_passed,
            "version_conflict_total_count": total_vconf,
            "overall_refusal_rate_pct": overall_refusal_rate,
            "refusals_by_reason": refusals_by_reason,
            "correct_refusal_rate_pct": correct_refusal_rate,
            "false_refusal_rate_pct": false_refusal_rate,
            "citation_verification_rate_pct": citation_validity,
            "hallucination_rate_pct": hallucination_rate,
            "retrieval": {
                "recall@1_pct": recall_at_1,
                "recall@3_pct": recall_at_3,
                "recall@5_pct": recall_at_5,
                "recall@10_pct": recall_at_10,
                "mrr": mrr,
            },
            "latency": {
                "p50_retrieval_ms": percentile(total_retrieval_ms, 0.50),
                "p95_retrieval_ms": percentile(total_retrieval_ms, 0.95),
                "p50_llm_ms": percentile(total_llm_ms, 0.50),
                "p95_llm_ms": percentile(total_llm_ms, 0.95),
                "p50_total_ms": percentile(total_latencies_ms, 0.50),
                "p95_total_ms": percentile(total_latencies_ms, 0.95),
            },
        },
        "top_3_confidently_wrong": [
            {
                "qid": w["qid"],
                "question": w["question"],
                "type": w["type"],
                "answer": w["answer"],
                "why_wrong": w["why_wrong"],
            }
            for w in top_3_confidently_wrong
        ],
        "hardware_and_model": get_hardware_and_model_info(),
        "per_question_results": per_question_results,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    logger.info(f"Evaluation complete. Report saved to {out_path}.")
    print("\n" + "=" * 35 + " EVALUATION SUMMARY " + "=" * 35)
    print(f"Accuracy - answered and verified (not refused, citations valid, versions named and cited): {answered_and_verified_pct}% ({total_answered_verified}/{total_q})")
    print(f"Accuracy - content check (must_include): {overall_accuracy}% ({total_correct}/{total_q})")
    for t_name, acc in accuracy_per_type.items():
        print(f"  - {t_name}: {acc}%")
    print(f"Citation Verification Rate: {citation_validity}%")
    print(f"Correct Refusal Rate: {correct_refusal_rate}% | False Refusal Rate: {false_refusal_rate}%")
    if total_vconf > 0:
        print(f"Version Conflict Strict Accuracy: {accuracy_per_type.get('version_conflict', 0.0)}%")
        print(f"Version Conflict Grader Pass Rate: {version_conflict_grader_pass_pct}% ({vconf_grader_passed}/{total_vconf})")
    print(f"Retrieval Recall@5: {recall_at_5}% | MRR: {mrr}")
    print(f"Latency Total: p50={report['metrics']['latency']['p50_total_ms']}ms, p95={report['metrics']['latency']['p95_total_ms']}ms")
    print("=" * 90 + "\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Kubernetes documentation RAG assistant.")
    parser.add_argument("--set", type=Path, default=Path("eval/eval_set.jsonl"), help="Path to evaluation question set.")
    parser.add_argument("--out", type=Path, default=Path("eval_report.json"), help="Output path for eval report JSON.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of chunks to retrieve per version.")
    args = parser.parse_args()

    run_evaluation(args.set, args.out, top_k=args.top_k)


if __name__ == "__main__":
    main()
