param(
    [string]$Destination = "backups"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

$database = if ($env:COURSEBOX_DB) { $env:COURSEBOX_DB } else { "data/coursebox.db" }
$databasePath = [System.IO.Path]::GetFullPath($database)
if (-not (Test-Path -LiteralPath $databasePath -PathType Leaf)) {
    throw "Database does not exist: $databasePath"
}

$destinationPath = [System.IO.Path]::GetFullPath($Destination)
New-Item -ItemType Directory -Path $destinationPath -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = Join-Path $destinationPath "coursebox-$stamp.db"

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
$env:COURSEBOX_BACKUP_SOURCE = $databasePath
$env:COURSEBOX_BACKUP_TARGET = $backupPath
& $pythonCommand scripts/db_backup.py
if ($LASTEXITCODE -ne 0) { throw "Database backup failed" }
Write-Output $backupPath
