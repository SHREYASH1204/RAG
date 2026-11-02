# scripts/make_zip.ps1
# Creates a clean submission zip archive including .git, eval_report.json, eval/eval_set.jsonl,
# eval/split.json, Dockerfile, tests, README.md, and excluding .env, __pycache__, and temporary caches.

$ErrorActionPreference = "Stop"

$repoRoot = (Get-Item $PSScriptRoot).Parent.FullName
$zipPath = Join-Path $repoRoot "submission.zip"

if (Test-Path $zipPath) {
    Remove-Item $zipPath -Force
}

Write-Host "Creating submission zip: $zipPath"

Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression

$zip = [System.IO.Compression.ZipFile]::Open($zipPath, [System.IO.Compression.ZipArchiveMode]::Create)

$includeItems = @(
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
    "eval_report.json"
)

$excludeExtensions = @(".pyc", ".pyo", ".pyd")
$excludeNames = @(".env", ".pytest_cache", "__pycache__", ".DS_Store", "Thumbs.db")

foreach ($item in $includeItems) {
    $itemPath = Join-Path $repoRoot $item
    if (-not (Test-Path $itemPath)) {
        Write-Warning "Item not found: $itemPath"
        continue
    }

    $itemObj = Get-Item -LiteralPath $itemPath -Force -ErrorAction SilentlyContinue
    if (-not $itemObj) {
        Write-Warning "Item not found: $itemPath"
        continue
    }

    if ($itemObj.PSIsContainer) {
        $files = Get-ChildItem -Path $itemPath -Recurse -Force
        foreach ($file in $files) {
            if ($file.PSIsContainer) { continue }
            
            $relPath = $file.FullName.Substring($repoRoot.Length + 1).Replace("\", "/")
            $skip = $false
            foreach ($exName in $excludeNames) {
                if ($relPath -split "/" -contains $exName) {
                    $skip = $true
                    break
                }
            }
            if ($skip -or ($excludeExtensions -contains $file.Extension)) {
                continue
            }

            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $file.FullName, $relPath) | Out-Null
        }
    } else {
        $relPath = $item.Replace("\", "/")
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $itemPath, $relPath) | Out-Null
    }
}

$zip.Dispose()
Write-Host "Created $zipPath successfully."
