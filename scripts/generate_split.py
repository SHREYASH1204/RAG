#!/usr/bin/env python3
"""Generate a seeded (seed=42) 60/40 stratified split of questions by type into DEV and TEST sets.

Usage:
    python scripts/generate_split.py [--input eval/eval_set.jsonl] [--split-out eval/split.json] [--dev-out eval/dev_set.jsonl] [--test-out eval/test_set.jsonl]
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


def create_stratified_split(
    input_path: Path,
    seed: int = 42,
    dev_ratio: float = 0.6,
) -> Dict[str, List[str]]:
    """Partition question IDs stratified by 'type' into dev and test sets."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    by_type: Dict[str, List[dict]] = defaultdict(list)
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            q_type = item.get("type", "unknown")
            by_type[q_type].append(item)

    rng = random.Random(seed)
    dev_qids: List[str] = []
    test_qids: List[str] = []

    dev_items: List[dict] = []
    test_items: List[dict] = []

    for q_type in sorted(by_type.keys()):
        group = by_type[q_type]
        # Sort by qid first for stable ordering prior to shuffle
        group.sort(key=lambda x: x["qid"])
        rng.shuffle(group)

        # 60% dev, 40% test
        n_dev = int(round(len(group) * dev_ratio))
        # Ensure at least 1 in each split if group has >= 2 items
        if len(group) >= 2:
            n_dev = max(1, min(len(group) - 1, n_dev))

        dev_part = group[:n_dev]
        test_part = group[n_dev:]

        dev_items.extend(dev_part)
        test_items.extend(test_part)

        dev_qids.extend([item["qid"] for item in dev_part])
        test_qids.extend([item["qid"] for item in test_part])

    return {
        "dev": dev_qids,
        "test": test_qids,
        "dev_items": dev_items,
        "test_items": test_items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 60/40 stratified dev/test split.")
    parser.add_argument("--input", type=Path, default=Path("eval/eval_set.jsonl"), help="Input questions jsonl.")
    parser.add_argument("--split-out", type=Path, default=Path("eval/split.json"), help="Output split.json.")
    parser.add_argument("--dev-out", type=Path, default=Path("eval/dev_set.jsonl"), help="Output dev_set.jsonl.")
    parser.add_argument("--test-out", type=Path, default=Path("eval/test_set.jsonl"), help="Output test_set.jsonl.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42).")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"Warning: {args.input} does not exist yet. Split will be generated once available.")
        return

    split_result = create_stratified_split(args.input, seed=args.seed)

    # Write split.json
    args.split_out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.split_out, "w", encoding="utf-8") as f:
        json.dump({
            "seed": args.seed,
            "dev_ratio": 0.6,
            "dev": split_result["dev"],
            "test": split_result["test"],
        }, f, indent=2)
    print(f"Saved split metadata to {args.split_out} ({len(split_result['dev'])} DEV, {len(split_result['test'])} TEST).")

    # Write dev_set.jsonl
    with open(args.dev_out, "w", encoding="utf-8") as f:
        for item in split_result["dev_items"]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Saved DEV questions to {args.dev_out} ({len(split_result['dev_items'])} questions).")

    # Write test_set.jsonl
    with open(args.test_out, "w", encoding="utf-8") as f:
        for item in split_result["test_items"]:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"Saved TEST questions to {args.test_out} ({len(split_result['test_items'])} questions).")


if __name__ == "__main__":
    main()

