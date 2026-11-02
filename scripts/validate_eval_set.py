#!/usr/bin/env python3
"""Validation script for evaluation question sets (eval_set.jsonl, dev_set.jsonl, test_set.jsonl).

Usage:
    python scripts/validate_eval_set.py <path_to_jsonl> [--smoke]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set


VALID_TARGET_VERSIONS = {"1.27", "1.31"}


def load_corpus_doc_versions(chunks_path: Path) -> Dict[str, Set[str]]:
    """Index doc_ids and their available versions from chunks.jsonl."""
    doc_versions: Dict[str, Set[str]] = {}
    if not chunks_path.exists():
        return doc_versions

    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            doc_id = row.get("doc_id")
            version = row.get("version")
            if doc_id and version:
                if doc_id not in doc_versions:
                    doc_versions[doc_id] = set()
                doc_versions[doc_id].add(version)
    return doc_versions


def validate_eval_set(filepath: Path, smoke: bool = False, chunks_path: Path = Path("index/chunks.jsonl")) -> List[str]:
    """Validate question set against schema and constraint rules.
    
    Returns:
        List of error messages (empty if valid).
    """
    errors: List[str] = []

    if not filepath.exists():
        return [f"File not found: {filepath}"]

    doc_versions = load_corpus_doc_versions(chunks_path)
    if not doc_versions and not smoke:
        errors.append(f"Corpus chunks not found at {chunks_path}; cannot verify doc_ids.")

    seen_qids: Set[str] = set()
    type_counts: Counter = Counter()
    total_questions = 0

    with open(filepath, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            total_questions += 1
            try:
                item = json.loads(line)
            except Exception as e:
                errors.append(f"Line {line_num}: Invalid JSON - {e}")
                continue

            if not isinstance(item, dict):
                errors.append(f"Line {line_num}: Record must be a JSON object.")
                continue

            # 1. qid
            qid = item.get("qid")
            if not qid or not isinstance(qid, str) or not qid.strip():
                errors.append(f"Line {line_num}: 'qid' must be a non-empty string.")
            elif qid in seen_qids:
                errors.append(f"Line {line_num}: Duplicate qid '{qid}'.")
            else:
                seen_qids.add(qid)

            # 2. question
            question = item.get("question")
            if not question or not isinstance(question, str) or not question.strip():
                errors.append(f"Line {line_num} ({qid}): 'question' must be a non-empty string.")

            # 3. type
            q_type = item.get("type")
            if not q_type or not isinstance(q_type, str) or not q_type.strip():
                errors.append(f"Line {line_num} ({qid}): 'type' must be a non-empty string.")
            else:
                type_counts[q_type] += 1

            # 4. target_version
            target_version = item.get("target_version")
            if target_version is not None:
                if str(target_version) not in VALID_TARGET_VERSIONS:
                    errors.append(f"Line {line_num} ({qid}): 'target_version' must be '1.27' or '1.31' if present (got '{target_version}').")

            # 5. gold_docs
            gold_docs = item.get("gold_docs")
            if gold_docs is not None:
                if not isinstance(gold_docs, list):
                    errors.append(f"Line {line_num} ({qid}): 'gold_docs' must be a list of strings if present.")
                else:
                    for doc_id in gold_docs:
                        if not isinstance(doc_id, str):
                            errors.append(f"Line {line_num} ({qid}): Element in 'gold_docs' is not a string: {doc_id}")

            # For version_conflict, both versions must exist in corpus for gold_docs
            if q_type == "version_conflict":
                if not gold_docs or not isinstance(gold_docs, list) or len(gold_docs) == 0:
                    errors.append(f"Line {line_num} ({qid}): 'version_conflict' questions must specify non-empty 'gold_docs'.")
                else:
                    for doc_id in gold_docs:
                        versions_found = doc_versions.get(doc_id, set())
                        if "1.27" not in versions_found or "1.31" not in versions_found:
                            missing = []
                            if "1.27" not in versions_found:
                                missing.append("1.27")
                            if "1.31" not in versions_found:
                                missing.append("1.31")
                            errors.append(
                                f"Line {line_num} ({qid}): 'version_conflict' doc_id '{doc_id}' is missing in corpus version(s): {', '.join(missing)}."
                            )

            # 6. must_include
            must_include = item.get("must_include")
            if must_include is not None:
                if not isinstance(must_include, list) or any(not isinstance(s, str) for s in must_include):
                    errors.append(f"Line {line_num} ({qid}): 'must_include' must be a list of strings if present.")

            # 7. versions_expected
            versions_expected = item.get("versions_expected")
            if versions_expected is not None:
                if not isinstance(versions_expected, list) or any(v not in VALID_TARGET_VERSIONS for v in versions_expected):
                    errors.append(f"Line {line_num} ({qid}): 'versions_expected' must be a list containing '1.27' and/or '1.31'.")

    # Enforce minimums for full sets (bypass if --smoke is passed)
    if not smoke:
        if total_questions < 36:
            errors.append(f"Set count violation: Expected >= 36 questions, found {total_questions}.")
        if type_counts["version_conflict"] < 8:
            errors.append(f"Category count violation: Expected >= 8 'version_conflict', found {type_counts['version_conflict']}.")
        if type_counts["unanswerable"] < 8:
            errors.append(f"Category count violation: Expected >= 8 'unanswerable', found {type_counts['unanswerable']}.")
        if type_counts["false_premise"] < 2:
            errors.append(f"Category count violation: Expected >= 2 'false_premise', found {type_counts['false_premise']}.")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate evaluation question set against schema and constraint rules.")
    parser.add_argument("filepath", type=Path, help="Path to evaluation questions jsonl file.")
    parser.add_argument("--smoke", action="store_true", help="Bypass minimum question count checks (for smoke testing).")
    parser.add_argument("--chunks", type=Path, default=Path("index/chunks.jsonl"), help="Path to index/chunks.jsonl.")
    args = parser.parse_args()

    errors = validate_eval_set(args.filepath, smoke=args.smoke, chunks_path=args.chunks)
    if errors:
        print(f"Validation FAILED for {args.filepath} ({len(errors)} errors):", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"Validation PASSED for {args.filepath}.")
        sys.exit(0)


if __name__ == "__main__":
    main()

