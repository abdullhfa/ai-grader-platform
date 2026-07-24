param(
    [Parameter(Mandatory=$true)][string]$EvidenceDir,
    [Parameter(Mandatory=$true)][int]$TimeoutSeconds,
    [Parameter(Mandatory=$true)][string]$ExecutableRelativePath,
    [switch]$Probe
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
function Save-Capture {
    param([string]$Path)
    Add-Type -AssemblyName System.Drawing
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose(); $bitmap.Dispose()
}
try {
    Add-Type -AssemblyName System.Windows.Forms
    if ($Probe) {
        Save-Capture (Join-Path $EvidenceDir 'probe.png')
        @{ status='probe_completed'; host_execution_used=$false; timestamp=(Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'result.json')
        Start-Sleep -Seconds 2
        Stop-Computer -Force
        exit 0
    }
    $exe = Join-Path $PSScriptRoot $ExecutableRelativePath
    if (-not (Test-Path -LiteralPath $exe)) { throw 'guest_executable_missing' }
    $process = Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) -PassThru
    Start-Sleep -Seconds 3
    Save-Capture (Join-Path $EvidenceDir 'launch.png')
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) { $process.Kill(); throw 'guest_runtime_timeout' }
    @{ status='completed'; guest_pid=$process.Id; exit_code=$process.ExitCode; host_execution_used=$false; timestamp=(Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'result.json')
    Start-Sleep -Seconds 2
    Stop-Computer -Force
} catch {
    @{ status='error'; errors=@($_.Exception.Message); host_execution_used=$false; timestamp=(Get-Date).ToString('o') } | ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $EvidenceDir 'result.json')
    Start-Sleep -Seconds 2
    Stop-Computer -Force
    exit 1
}
