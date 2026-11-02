.PHONY: setup fetch ingest serve eval test validate clean

setup:
	python -m pip install -r requirements.txt

fetch:
	python scripts/fetch_corpus.py

ingest:
	python -m app.ingest --rebuild

serve:
	python -m uvicorn app.api:app --host 0.0.0.0 --port 8080

eval:
	python -m app.eval --set eval/eval_set.jsonl --out eval_report.json

test:
	pytest -v tests

validate:
	python scripts/validate_submission.py

clean:
	python -c "import shutil, os; [shutil.rmtree(d, ignore_errors=True) for d in ['index', '__pycache__', '.pytest_cache']]"
			