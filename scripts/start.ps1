param(
    [string]$BindHost = $env:COURSEBOX_HOST,
    [int]$Port = 0
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if ([string]::IsNullOrWhiteSpace($BindHost)) { $BindHost = "0.0.0.0" }
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
    $localPythonCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Python\pythoncore-3.14-64\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Python\bin\python.exe")
    )
    $pythonCommand = $localPythonCandidates |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1
}
if ([string]::IsNullOrWhiteSpace($pythonCommand)) {
    throw "Python was not found. Set COURSEBOX_PYTHON to the Python executable path."
}
Write-Host "CourseBox is listening on http://$BindHost`:$Port/"
if ($BindHost -eq "0.0.0.0") {
    $lanAddresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.PrefixOrigin -ne "WellKnown"
        } |
        Select-Object -ExpandProperty IPAddress
    foreach ($address in $lanAddresses) {
        Write-Host "Share this address on the same network: http://$address`:$Port/"
    }
}
& $pythonCommand -m uvicorn app.main:app --host $BindHost --port $Port
