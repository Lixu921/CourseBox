param(
    [string]$BindHost = $env:COURSEBOX_HOST,
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if ([string]::IsNullOrWhiteSpace($BindHost)) { $BindHost = "127.0.0.1" }
if ($Port -le 0) {
    $Port = if ($env:COURSEBOX_PORT) { [int]$env:COURSEBOX_PORT } else { 8000 }
}

$pythonCommand = $env:COURSEBOX_PYTHON
if ([string]::IsNullOrWhiteSpace($pythonCommand)) {
    foreach ($candidate in @("py", "python")) {
        $command = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($null -ne $command -and $command.Source -notlike "*WindowsApps*") {
            $pythonCommand = $command.Source
            break
        }
    }
}
if ([string]::IsNullOrWhiteSpace($pythonCommand)) {
    throw "Python was not found. Set COURSEBOX_PYTHON to the Python executable path."
}
& $pythonCommand -m uvicorn app.main:app --host $BindHost --port $Port
