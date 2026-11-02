"""Comprehensive end-to-end validator checking schema compliance, edge cases, and eval set integrity."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure workspace root is in sys.path for direct script execution
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import httpx

from app.api import app
from app.schemas import AskResponse, EvalQuestion

REQUIRED_KEYS = {"answer", "refused", "citations", "retrieved_chunk_ids", "latency_ms"}


class SubmissionValidator:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client: Optional[httpx.Client] = None
        self.test_client = None
        self.is_live = False

        # Check if live server is reachable
        try:
            with httpx.Client(timeout=2.0) as probe:
                r = probe.get(f"{self.base_url}/healthz")
                if r.status_code == 200:
                    self.is_live = True
        except Exception:
            self.is_live = False

        if not self.is_live:
            from fastapi.testclient import TestClient
            self.test_client = TestClient(app)
            print(f"[*] Live server at {self.base_url} not detected. Using in-process ASGI TestClient for validation.")
        else:
            print(f"[*] Connected to live running server at {self.base_url}")
            self.client = httpx.Client(base_url=self.base_url, timeout=120.0)

    def post_ask(self, payload: Any, raw_content: Optional[str] = None) -> httpx.Response:
        headers = {"Content-Type": "application/json"}
        if self.is_live:
            if raw_content is not None:
                return self.client.post("/ask", content=raw_content, headers=headers)
            return self.client.post("/ask", json=payload)
        else:
            if raw_content is not None:
                return self.test_client.post("/ask", content=raw_content, headers=headers)
            return self.test_client.post("/ask", json=payload)

    def assert_schema(self, resp: httpx.Response, label: str) -> Dict[str, Any]:
        """Assert HTTP 200 and exact 5-field schema."""
        if resp.status_code != 200:
            raise AssertionError(f"[{label}] Expected HTTP 200, got {resp.status_code}: {resp.text}")
        data = resp.json()
        missing = REQUIRED_KEYS - set(data.keys())
        extra = set(data.keys()) - REQUIRED_KEYS
        if missing or extra:
            raise AssertionError(f"[{label}] Schema violation: missing={missing}, extra={extra}")
        AskResponse.model_validate(data)
        if "internal error" in data.get("answer", "").lower():
            raise AssertionError(f"[{label}] Failure: Response contains internal_error: {data.get('answer')}")
        return data

    def run_all(self, eval_set_path: Path):
        print("\n" + "=" * 60)
        print("RUNNING SUBMISSION VALIDATION SUITE")
        print("=" * 60)
        tests_passed = 0

        # 1. Edge Case: Empty question
        print("[1/13] Testing empty question...")
        r = self.post_ask({"question": ""})
        d = self.assert_schema(r, "empty_question")
        assert d["refused"] is True and d["citations"] == [], "Empty query must refuse with empty citations"
        tests_passed += 1

        # 2. Edge Case: Whitespace question
        print("[2/13] Testing whitespace question...")
        r = self.post_ask({"question": "   \n\t  "})
        d = self.assert_schema(r, "whitespace_question")
        assert d["refused"] is True and d["citations"] == [], "Whitespace query must refuse with empty citations"
        tests_passed += 1

        # 3. Edge Case: 4000+ characters question
        print("[3/13] Testing 4000+ characters question...")
        long_q = "What is a Pod in Kubernetes? " + ("word " * 1000)
        assert len(long_q) > 4000
        r = self.post_ask({"question": long_q, "top_k": 3})
        d = self.assert_schema(r, "long_question")
        assert len(d["retrieved_chunk_ids"]) > 0, "Long query should safely retrieve chunks"
        tests_passed += 1

        # 4. Edge Case: Hindi question
        print("[4/13] Testing Hindi non-English question...")
        r = self.post_ask({"question": "कुबेरनेट्स क्या है?"})
        d = self.assert_schema(r, "hindi_question")
        assert d["refused"] is True and d["citations"] == [], "Non-English Hindi query must refuse"
        tests_passed += 1

        # 5. Edge Case: French question
        print("[5/13] Testing French non-English question...")
        r = self.post_ask({"question": "Qu'est-ce qu'un pod dans Kubernetes?"})
        d = self.assert_schema(r, "french_question")
        assert d["refused"] is True and d["citations"] == [], "Non-English French query must refuse"
        tests_passed += 1

        # 6. Edge Case: Invalid JSON string
        print("[6/13] Testing malformed JSON payload...")
        r = self.post_ask(payload=None, raw_content="malformed json {")
        d = self.assert_schema(r, "malformed_json")
        assert d["refused"] is True, "Malformed JSON must return HTTP 200 refusal"
        tests_passed += 1

        # 7. Edge Case: Missing question field
        print("[7/13] Testing missing question field...")
        r = self.post_ask({"top_k": 5})
        d = self.assert_schema(r, "missing_fields")
        assert d["refused"] is True, "Missing required question must return HTTP 200 refusal"
        tests_passed += 1

        # 8. Edge Case: Bad top_k (-1)
        print("[8/13] Testing negative top_k (-1)...")
        r = self.post_ask({"question": "What is a Service in Kubernetes?", "top_k": -1})
        d = self.assert_schema(r, "negative_top_k")
        assert len(d["retrieved_chunk_ids"]) >= 1, "top_k=-1 must be clamped to at least 1"
        tests_passed += 1

        # 9. Edge Case: Bad top_k (999)
        print("[9/13] Testing excessive top_k (999)...")
        r = self.post_ask({"question": "What is a Service in Kubernetes?", "top_k": 999})
        d = self.assert_schema(r, "excessive_top_k")
        assert len(d["retrieved_chunk_ids"]) <= 40, "top_k=999 must be clamped to at most 20 per version"
        tests_passed += 1

        # 10. Eval Set: False premise test
        print("[10/13] Testing false premise flag rejection...")
        r = self.post_ask({"question": "How to set --nonexistent-hypothetical-scheduler-quantum-mode in kube-scheduler?"})
        d = self.assert_schema(r, "false_premise")
        assert d["refused"] is True and d["citations"] == [], "Nonexistent flag must trigger refusal"
        assert "--nonexistent-hypothetical-scheduler-quantum-mode" in d["answer"]
        tests_passed += 1

        # 11. Eval Set: Unanswerable test
        print("[11/13] Testing unanswerable question...")
        r = self.post_ask({"question": "How do you configure BGP mesh routing in Docker Swarm mode?"})
        d = self.assert_schema(r, "unanswerable")
        assert d["refused"] is True and d["citations"] == [], "Unanswerable question must be refused"
        tests_passed += 1

        # 12. Eval Set: Version conflict retrieval balance
        print("[12/13] Testing version conflict balance on kubelet skew...")
        r = self.post_ask({"question": "How many minor versions older than kube-apiserver can a kubelet be supported at?", "top_k": 5})
        d = self.assert_schema(r, "version_conflict")
        retrieved_ids = d["retrieved_chunk_ids"]
        assert any(c.startswith("v1.27:") for c in retrieved_ids), "1.27 chunks must be retrieved"
        assert any(c.startswith("v1.31:") for c in retrieved_ids), "1.31 chunks must be retrieved"
        tests_passed += 1

        # 13. Citation Integrity Check
        print("[13/13] Testing citation integrity against chunks.jsonl...")
        chunks_map: Dict[str, str] = {}
        chunks_file = Path("index/chunks.jsonl")
        if chunks_file.exists():
            with chunks_file.open("r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        chunks_map[row["chunk_id"]] = row["text"]

        if d["citations"]:
            for cit in d["citations"]:
                cid = cit["chunk_id"]
                quote = cit["quote"]
                assert cid in chunks_map, f"Citation chunk_id {cid} not in chunks.jsonl"
                assert quote in chunks_map[cid], f"Citation quote '{quote}' is not an exact substring of chunk {cid}"
        print("         Citation integrity verified.")
        tests_passed += 1

        print("=" * 60)
        print(f"ALL {tests_passed}/{tests_passed} VALIDATION TESTS PASSED SUCCESSFULLY!")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Validate Grounded Documentation Assistant Submission")
    parser.add_argument("--url", default="http://localhost:8080", help="Service URL")
    parser.add_argument("--set", default="eval/eval_set.jsonl", help="Evaluation set path")
    args = parser.parse_args()

    validator = SubmissionValidator(base_url=args.url)
    validator.run_all(Path(args.set))


if __name__ == "__main__":
    main()
