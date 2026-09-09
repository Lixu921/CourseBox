param(
    [Parameter(Mandatory = $true)]
    [string]$Backup,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

$database = if ($env:COURSEBOX_DB) { $env:COURSEBOX_DB } else { "data/coursebox.db" }
$databasePath = [System.IO.Path]::GetFullPath($database)
$backupPath = [System.IO.Path]::GetFullPath($Backup)
if (-not (Test-Path -LiteralPath $backupPath -PathType Leaf)) {
    throw "Backup file does not exist: $backupPath"
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
$env:COURSEBOX_BACKUP_SOURCE = $backupPath
& $pythonCommand scripts/db_check.py
if ($LASTEXITCODE -ne 0) { throw "Backup integrity check failed" }

if ((Test-Path -LiteralPath $databasePath -PathType Leaf) -and -not $Force) {
    throw "Target database exists. Use -Force to overwrite it."
}
New-Item -ItemType Directory -Path (Split-Path -Parent $databasePath) -Force | Out-Null
if (Test-Path -LiteralPath $databasePath -PathType Leaf) {
    Copy-Item -LiteralPath $databasePath -Destination "$databasePath.before-restore" -Force
}
Copy-Item -LiteralPath $backupPath -Destination $databasePath -Force
Write-Output $databasePath
