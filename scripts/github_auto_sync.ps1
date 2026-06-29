<#
.SYNOPSIS
  Watch the repo and auto-commit + push to GitHub after changes settle.

.USAGE
  powershell -ExecutionPolicy Bypass -File scripts\github_auto_sync.ps1
  Double-click: scripts\start_github_sync.bat
#>
param(
    [int]$DebounceSeconds = 60,
    [int]$PollSeconds = 5,
    [string]$Branch = "main",
    [string]$Remote = "origin"
)

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Git = if (Test-Path "C:\Program Files\Git\bin\git.exe") {
    "C:\Program Files\Git\bin\git.exe"
} else {
    "git"
}

function Invoke-RepoGit {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    $out = & $Git -c "safe.directory=$RepoRoot" -C $RepoRoot @Args 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($out | Out-String).Trim()
    }
    return $out
}

function Get-RepoChanges {
    $lines = @(Invoke-RepoGit status --porcelain)
    return $lines | Where-Object {
        $_ -and $_ -notmatch '^\?\? .*[\\/](\.venv|venv|node_modules|__pycache__|uploads[\\/]students)'
    }
}

function Sync-ToGitHub {
    $porcelain = Get-RepoChanges
    if (-not $porcelain) {
        Write-Host "[sync] $(Get-Date -Format 'HH:mm:ss') — no changes"
        return $true
    }

    Write-Host "[sync] $(Get-Date -Format 'HH:mm:ss') — staging..."
    Invoke-RepoGit add -A | Out-Null

    $staged = @(Invoke-RepoGit diff --cached --name-only)
    if (-not $staged) {
        Write-Host "[sync] nothing to commit (gitignore filtered)"
        return $true
    }

    $msg = "auto-sync: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ($($staged.Count) file(s))"
    Write-Host "[sync] commit: $msg"
    Invoke-RepoGit commit -m $msg | Out-Null

    Write-Host "[sync] push → $Remote/$Branch"
    Invoke-RepoGit push $Remote $Branch | Out-Null
    Write-Host "[sync] GitHub updated."
    return $true
}

if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
    Write-Error "Not a git repo: $RepoRoot"
}

try {
    Invoke-RepoGit remote get-url $Remote | Out-Null
} catch {
    Write-Error "Remote '$Remote' missing. Add: git remote add origin https://github.com/abdullhfa/ai-teacher.git"
}

Write-Host "========================================"
Write-Host " GitHub Auto-Sync"
Write-Host " Repo:     $RepoRoot"
Write-Host " Remote:   $Remote / $Branch"
Write-Host " Debounce: ${DebounceSeconds}s | Poll: ${PollSeconds}s"
Write-Host " Ctrl+C to stop"
Write-Host "========================================"

try { Sync-ToGitHub | Out-Null } catch { Write-Warning $_ }

$lastChangeAt = $null

while ($true) {
    Start-Sleep -Seconds $PollSeconds
    try {
        $changes = Get-RepoChanges
        if ($changes) {
            if (-not $lastChangeAt) {
                Write-Host "[watch] changes detected — sync in ${DebounceSeconds}s if idle..."
            }
            $lastChangeAt = Get-Date
            continue
        }
        if ($lastChangeAt) {
            $idle = ((Get-Date) - $lastChangeAt).TotalSeconds
            if ($idle -ge $DebounceSeconds) {
                Sync-ToGitHub | Out-Null
                $lastChangeAt = $null
            }
        }
    } catch {
        Write-Warning "[sync] $($_.Exception.Message)"
        Write-Warning "Login: gh auth login  OR Git Credential Manager when pushing"
        Start-Sleep -Seconds 30
    }
}
