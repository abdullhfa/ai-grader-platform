$ErrorActionPreference = "Stop"

Write-Host "========================================"
Write-Host "Starting AI Assignment Grader..."
Write-Host "========================================"

# Try to find python
$pythonCmd = "python"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pythonCmd = "py"
    } else {
        # Check common installation paths
        $commonPaths = @(
            "$env:USERPROFILE\AppData\Local\Programs\Python\Python312\python.exe",
            "$env:USERPROFILE\AppData\Local\Programs\Python\Python311\python.exe",
            "$env:USERPROFILE\AppData\Local\Programs\Python\Python310\python.exe",
            "C:\Python312\python.exe",
            "C:\Python311\python.exe"
        )
        
        foreach ($path in $commonPaths) {
            if (Test-Path $path) {
                $pythonCmd = $path
                break
            }
        }
        
        if ($pythonCmd -eq "python") {
            Write-Host "❌ Python is not installed or not found in PATH." -ForegroundColor Red
            Write-Host "Please install Python from https://www.python.org/downloads/"
            Write-Host "Make sure to check 'Add python.exe to PATH' during installation."
            Read-Host "Press Enter to exit"
            exit
        }
    }
}

Write-Host "✅ Python found: $pythonCmd" -ForegroundColor Green

# Check and create virtual environment
if (-not (Test-Path ".venv")) {
    Write-Host "📦 Creating virtual environment..."
    & $pythonCmd -m venv .venv
}

# Run the app using the virtual environment python
$venvPython = ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Host "🚀 Starting server..." -ForegroundColor Cyan
    & $venvPython main.py
} else {
    Write-Host "❌ Virtual environment not configured correctly." -ForegroundColor Red
}

Read-Host "Press Enter to exit"
