import os
import sys
import zipfile
import shutil
import tempfile
import hashlib
import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

BLOCKED_EXTENSIONS = {'.ps1', '.sh', '.sample', '.bat', '.cmd', '.exe', '.vbs', '.pyc', '.pyo', '.pyd', '.zip'}
EXCLUDED_NAMES = {'.env', '__pycache__', '.pytest_cache', '.DS_Store', 'Thumbs.db', 'index', 'k8s-1.27', 'k8s-1.31'}

INCLUDE_ITEMS = [
    ".git",
    ".gitignore",
    ".dockerignore",
    ".env.example",
    "app",
    "corpus",
    "eval",
    "scripts",
    "tests",
    "Dockerfile",
    "Makefile",
    "README.md",
    "requirements.txt",
    "conftest.py",
    "eval_report.json",
]

def make_clean_zip(output_zip_path: Path):
    if output_zip_path.exists():
        output_zip_path.unlink()
    
    print(f"Creating clean zip archive: {output_zip_path}")
    count = 0
    with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for item in INCLUDE_ITEMS:
            src_path = ROOT_DIR / item
            if not src_path.exists():
                print(f"Warning: {src_path} does not exist!")
                continue
            
            if src_path.is_file():
                ext = src_path.suffix.lower()
                if ext in BLOCKED_EXTENSIONS or src_path.name in EXCLUDED_NAMES:
                    continue
                z.write(src_path, arcname=item)
                count += 1
            else:
                for root, dirs, files in os.walk(src_path):
                    rel_root = Path(root).relative_to(ROOT_DIR)
                    parts = rel_root.parts
                    if any(p in EXCLUDED_NAMES for p in parts):
                        continue
                    
                    for f in files:
                        p = Path(root) / f
                        ext = p.suffix.lower()
                        if ext in BLOCKED_EXTENSIONS or f in EXCLUDED_NAMES:
                            continue
                        rel_file = p.relative_to(ROOT_DIR).as_posix()
                        if any(ex in rel_file.split('/') for ex in EXCLUDED_NAMES):
                            continue
                        z.write(p, arcname=rel_file)
                        count += 1
                        
    print(f"Wrote {count} files to {output_zip_path}.")

if __name__ == "__main__":
    out_clean = ROOT_DIR / "submission_clean.zip"
    make_clean_zip(out_clean)
    
    # Also update submission.zip with the exact clean version
    out_sub = ROOT_DIR / "submission.zip"
    shutil.copy2(out_clean, out_sub)
    print(f"Updated {out_sub} with clean archive.")

