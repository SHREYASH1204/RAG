"""Offline Hallucination Rate Calculator.

Computes hallucination rate offline from the answers saved in eval_report.json
using the exact definition from the README:
"An answer that contains a claim not supported by the chunks it cites,
including answering when it should have refused."

Specifically:
Among answered questions (refused=False):
1. Share of answered questions with at least one sentence whose token support
   score against its cited chunk(s) falls below MIN_SUPPORT (0.50).
2. Number of questions answered when they should have been refused
   (unanswerable or false_premise).
"""

import json
import sys
from pathlib import Path

# Ensure local repo root is at the head of sys.path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from typing import Dict, List, Tuple

from app.config import get_settings

MIN_SUPPORT = get_settings().MIN_SUPPORT
from app.llm import compute_sentence_support, split_answer_into_units, strip_chunk_markers


def load_chunks(chunks_path: Path = Path("index/chunks.jsonl")) -> Dict[str, str]:
    chunks = {}
    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                c = json.loads(line)
                chunks[c["chunk_id"]] = c["text"]
    return chunks


def compute_offline_hallucination(
    report_path: Path = Path("eval_report.json"),
    chunks_path: Path = Path("index/chunks.jsonl"),
) -> Dict[str, float]:
    chunks = load_chunks(chunks_path)

    with open(report_path, "r", encoding="utf-8") as f:
        rep = json.load(f)

    results = rep["per_question_results"]
    total_questions = len(results)

    answered_questions = [r for r in results if not r.get("refused")]
    answered_count = len(answered_questions)

    # 1. Unanswerable or false premise questions that were answered
    should_refuse_answered = [
        r for r in answered_questions if r.get("type") in ("unanswerable", "false_premise")
    ]
    should_refuse_answered_count = len(should_refuse_answered)

    # 2. Sentences with support < MIN_SUPPORT against the cited chunks
    questions_with_unsupported_claim = []
    unsupported_sentence_details = []

    for r in answered_questions:
        ans = r.get("answer", "")
        citations = r.get("citations", [])
        cited_cids = [c["chunk_id"] for c in citations if "chunk_id" in c]
        cited_texts = " ".join(chunks.get(cid, "") for cid in cited_cids)

        units = split_answer_into_units(ans)
        has_unsupported_unit = False

        for u_type, u_text in units:
            if u_type == "prose":
                clean_s = strip_chunk_markers(u_text)
                if not clean_s.strip():
                    continue
                # If the sentence has specific citations in brackets, check against those;
                # otherwise check against all cited texts for this question
                sup, content_words, matched = compute_sentence_support(u_text, cited_texts)
                if sup < MIN_SUPPORT:
                    has_unsupported_unit = True
                    unsupported_sentence_details.append({
                        "qid": r["qid"],
                        "sentence": u_text,
                        "support": sup,
                        "content_words": content_words,
                        "matched": matched,
                    })

        if has_unsupported_unit:
            questions_with_unsupported_claim.append(r["qid"])

    # Total hallucinated under definition:
    # Any question with an unsupported claim OR answered when should refuse
    hallucinated_qids = sorted(list(set(
        questions_with_unsupported_claim + [r["qid"] for r in should_refuse_answered]
    )))
    hallucinated_count = len(hallucinated_qids)

    hallucination_rate_answered = (
        (hallucinated_count / answered_count * 100.0) if answered_count > 0 else 0.0
    )
    unsupported_claim_rate = (
        (len(questions_with_unsupported_claim) / answered_count * 100.0) if answered_count > 0 else 0.0
    )

    summary = {
        "total_questions": total_questions,
        "answered_count": answered_count,
        "should_refuse_answered_count": should_refuse_answered_count,
        "should_refuse_answered_qids": [r["qid"] for r in should_refuse_answered],
        "questions_with_unsupported_claim_count": len(questions_with_unsupported_claim),
        "questions_with_unsupported_claim_qids": questions_with_unsupported_claim,
        "total_hallucinated_count": hallucinated_count,
        "total_hallucinated_qids": hallucinated_qids,
        "hallucination_rate_pct": round(hallucination_rate_answered, 2),
        "unsupported_claim_rate_pct": round(unsupported_claim_rate, 2),
        "unsupported_sentence_details": unsupported_sentence_details,
    }

    return summary


if __name__ == "__main__":
    summary = compute_offline_hallucination()
    print("=" * 60)
    print("OFFLINE HALLUCINATION REPORT")
    print("=" * 60)
    print(f"Total Questions Evaluated: {summary['total_questions']}")
    print(f"Answered Questions: {summary['answered_count']}")
    print(f"Should-Refuse Answered: {summary['should_refuse_answered_count']} (QIDs: {summary['should_refuse_answered_qids']})")
    print(f"Questions with Unsupported Sentence (< {MIN_SUPPORT}): {summary['questions_with_unsupported_claim_count']} (QIDs: {summary['questions_with_unsupported_claim_qids']})")
    print(f"Total Hallucinated (Definition): {summary['total_hallucinated_count']}/{summary['answered_count']} ({summary['hallucination_rate_pct']}%)")
    print("=" * 60)
    if summary["unsupported_sentence_details"]:
        print("\nUnsupported Sentences:")
        for det in summary["unsupported_sentence_details"]:
            print(f"- [{det['qid']}] (support={det['support']:.2f}): {det['sentence']}")
