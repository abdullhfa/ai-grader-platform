# Recreate project virtualenv on Windows when .venv points to a missing Python.
# Usage (PowerShell):
#   .\scripts\recreate_venv.ps1
#   .\scripts\recreate_venv.ps1 -PythonExe "C:\Path\To\python.exe"

param(
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Find-Python {
    param([string]$Preferred)
    if ($Preferred -and (Test-Path $Preferred)) {
        return (Resolve-Path $Preferred).Path
    }
    $candidates = @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe"
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }
    try {
        $pyLauncher = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($pyLauncher -and (Test-Path $pyLauncher)) {
            return (Resolve-Path $pyLauncher).Path
        }
    } catch {}
    try {
        $pyLauncher = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
        if ($pyLauncher -and (Test-Path $pyLauncher)) {
            return (Resolve-Path $pyLauncher).Path
        }
    } catch {}
    return $null
}

$python = Find-Python -Preferred $PythonExe
if (-not $python) {
    Write-Host "Python 3.11/3.12 not found."
    Write-Host "Install: winget install Python.Python.3.12"
    Write-Error "Python 3.11/3.12 not found. Install Python, then rerun with -PythonExe."
}

Write-Host "Using Python: $python"
& $python --version

if (Test-Path ".venv") {
    Write-Host "Removing broken .venv ..."
    Remove-Item -Recurse -Force ".venv"
}

Write-Host "Creating .venv ..."
& $python -m venv .venv

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Error "venv creation failed."
}

Write-Host "Installing requirements ..."
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt

Write-Host "Running unit tests ..."
& $venvPython -m unittest test_unity_stage4_runtime.py
Write-Host "Done."
