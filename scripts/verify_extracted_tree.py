import zipfile
import tempfile
import os
from pathlib import Path

zip_path = Path("submission.zip")
size_mb = zip_path.stat().st_size / (1024 * 1024)
print(f"=== submission.zip size: {size_mb:.2f} MB ({zip_path.stat().st_size} bytes) ===")

temp_dir = Path(tempfile.mkdtemp(prefix="submission_verify_"))
print(f"Extracting to NEW temp folder: {temp_dir}")

with zipfile.ZipFile(zip_path, "r") as z:
    z.extractall(temp_dir)

print("\n=== Verifying Required Files & Folders ===")
required = [
    ".git", "README.md", "Dockerfile", ".dockerignore", ".env.example",
    "eval_report.json", "eval/eval_set.jsonl", "eval/split.json", "tests",
    "corpus", "app/static/index.html"
]
for r in required:
    p = temp_dir / r
    status = "PRESENT" if p.exists() else "MISSING"
    print(f"  {r}: {status}")

print("\n=== Verifying Excluded Items are ABSENT ===")
absent = [".env", "index", "k8s-1.27", "k8s-1.31", "__pycache__"]
for a in absent:
    p = temp_dir / a
    status = "ABSENT (Verified)" if not p.exists() else "FOUND (Error!)"
    print(f"  {a}: {status}")

print("\n=== Final Extracted Tree (2 levels deep) ===")
def print_tree(d, level=0, max_level=2):
    if level >= max_level:
        return
    entries = sorted(d.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    for e in entries:
        if e.name == ".git" and level > 0:
            continue
        indent = "  " * level
        if e.is_dir():
            print(f"{indent}[DIR]  {e.name}/")
            print_tree(e, level + 1, max_level)
        else:
            print(f"{indent}[FILE] {e.name} ({e.stat().st_size / 1024:.1f} KB)")

print_tree(temp_dir)
print(f"\nExtracted folder: {temp_dir}")

