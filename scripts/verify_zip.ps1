# scripts/verify_zip.ps1
$ErrorActionPreference = "Stop"

$repoRoot = (Get-Item $PSScriptRoot).Parent.FullName
$zipPath = Join-Path $repoRoot "submission.zip"

$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
Write-Host "Extracting to: $tempDir"
Expand-Archive -Path $zipPath -DestinationPath $tempDir

Write-Host "`n--- Verification Checks ---"
$checks = @(
    ".git",
    ".gitignore",
    ".dockerignore",
    ".env.example",
    "eval_report.json",
    "eval/eval_set.jsonl",
    "eval/split.json",
    "Dockerfile",
    "tests",
    "README.md",
    ".env"
)

foreach ($c in $checks) {
    $p = Join-Path $tempDir $c
    $exists = Test-Path -Path $p
    if ($c -eq ".env") {
        Write-Host "$c present? $exists (Expected: False)"
    } else {
        Write-Host "$c present? $exists (Expected: True)"
    }
}

Write-Host "`n--- Top-level Extracted Contents ---"
Get-ChildItem -Path $tempDir -Force | Select-Object Name, Mode

# Cleanup temp dir
Remove-Item -Path $tempDir -Recurse -Force
Write-Host "`nTemporary extraction cleaned up."

