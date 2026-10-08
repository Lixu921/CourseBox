param(
    [Parameter(Mandatory = $true)]
    [string]$Backup,
    [string]$Uploads,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

$database = if ($env:COURSEBOX_DB) { $env:COURSEBOX_DB } else { "data/coursebox.db" }
$databasePath = [System.IO.Path]::GetFullPath($database)
$uploadDirectory = if ($env:COURSEBOX_UPLOAD_DIR) { $env:COURSEBOX_UPLOAD_DIR } else { "uploads" }
$uploadsPath = [System.IO.Path]::GetFullPath($uploadDirectory)
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

if ($Uploads) {
    # 上传目录归档（uploads-<时间戳>.zip）默认也随备份产出，恢复时一并还原，
    # 否则只还原数据库会指向一堆已经不在磁盘上的文件。
    $uploadsBackupPath = [System.IO.Path]::GetFullPath($Uploads)
    if (-not (Test-Path -LiteralPath $uploadsBackupPath -PathType Leaf)) {
        throw "Uploads backup file does not exist: $uploadsBackupPath"
    }
    if ((Test-Path -LiteralPath $uploadsPath) -and -not $Force) {
        throw "Upload directory exists. Use -Force to extract into it."
    }
    New-Item -ItemType Directory -Path $uploadsPath -Force | Out-Null
    Expand-Archive -LiteralPath $uploadsBackupPath -DestinationPath $uploadsPath -Force
    Write-Output $uploadsPath
}
