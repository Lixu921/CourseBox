param(
    [string]$Destination = "backups",
    [int]$Keep = 7,
    [switch]$SkipUploads
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

$arguments = @("scripts/backup.py", "--destination", $destinationPath, "--keep", $Keep)
if ($SkipUploads) { $arguments += "--no-uploads" }
& $pythonCommand @arguments
if ($LASTEXITCODE -ne 0) { throw "Backup failed" }
