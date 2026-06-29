# Package project source for delivery — excludes venv, secrets, runtime data.
# Usage: .\scripts\package-source.ps1 [-OutputZip "..\ai_grader_source.zip"]

param(
    [string]$OutputZip = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not $OutputZip) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmm"
    $OutputZip = Join-Path (Split-Path $Root -Parent) "ai_grader_source_$stamp.zip"
}

$ExcludeDirNames = @(
    ".venv", "venv", "env", "ENV",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "node_modules", ".wwebjs_cache", ".wwebjs_auth", "wa_session",
    ".git", ".idea", ".vscode"
)

$ExcludeFilePatterns = @(
    ".env", ".env.local", "*.pyc", "*.pyo", "*.log",
    "ai_grader.db", "ai_grader.db-*", "grading.db"
)

function Should-SkipPath([string]$FullPath, [string]$RelativePath) {
    $parts = $RelativePath -split '[\\/]'
    foreach ($part in $parts) {
        if ($ExcludeDirNames -contains $part) { return $true }
    }
    $leaf = Split-Path -Leaf $RelativePath
    foreach ($pat in $ExcludeFilePatterns) {
        if ($leaf -like $pat) { return $true }
    }
    if ($RelativePath -match '^uploads[\\/]students') { return $true }
    if ($RelativePath -match '^uploads[\\/]reports') { return $true }
    if ($RelativePath -match '^uploads[\\/]debug') { return $true }
    if ($RelativePath -match '^uploads[\\/]assignments') { return $true }
    if ($RelativePath -match '^app[\\/]calibration[\\/]reports') { return $true }
    return $false
}

$tempDir = Join-Path $env:TEMP ("ai_grader_pkg_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $tempDir | Out-Null
$stageRoot = Join-Path $tempDir (Split-Path -Leaf $Root)
New-Item -ItemType Directory -Path $stageRoot | Out-Null

Write-Host "Staging from: $Root"
Write-Host "Output zip:   $OutputZip"

Get-ChildItem -Path $Root -Recurse -Force | ForEach-Object {
    $rel = $_.FullName.Substring($Root.Length).TrimStart('\', '/')
    if (-not $rel) { return }
    if (Should-SkipPath $_.FullName $rel) { return }

    $dest = Join-Path $stageRoot $rel
    if ($_.PSIsContainer) {
        if (-not (Test-Path $dest)) {
            New-Item -ItemType Directory -Path $dest -Force | Out-Null
        }
    } else {
        $destParent = Split-Path -Parent $dest
        if (-not (Test-Path $destParent)) {
            New-Item -ItemType Directory -Path $destParent -Force | Out-Null
        }
        Copy-Item -LiteralPath $_.FullName -Destination $dest -Force
    }
}

if (Test-Path $OutputZip) { Remove-Item -Force $OutputZip }
Compress-Archive -Path $stageRoot -DestinationPath $OutputZip -CompressionLevel Optimal

Remove-Item -Recurse -Force $tempDir

$zip = Get-Item $OutputZip
Write-Host ""
Write-Host "Done. Size: $([math]::Round($zip.Length / 1MB, 2)) MB"
Write-Host "Path: $($zip.FullName)"
