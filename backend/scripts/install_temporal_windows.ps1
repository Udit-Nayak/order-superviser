$ErrorActionPreference = "Stop"

$installDir = Join-Path $HOME "temporal-cli"
$zipPath = Join-Path $installDir "temporal.zip"

New-Item -ItemType Directory -Force $installDir | Out-Null
Write-Host "Downloading the latest Temporal CLI for Windows amd64..."
Invoke-WebRequest `
  -Uri "https://temporal.download/cli/archive/latest?arch=amd64&platform=windows" `
  -OutFile $zipPath

Write-Host "Extracting Temporal CLI to $installDir ..."
Expand-Archive $zipPath -DestinationPath $installDir -Force
Remove-Item $zipPath -Force

# Make it usable in this PowerShell immediately.
$env:Path = "$env:Path;$installDir"

# Add it to the current user's PATH for future terminals if needed.
$current = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $current) { $current = "" }
if ($current -notlike "*$installDir*") {
    $newPath = if ($current) { "$current;$installDir" } else { $installDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
}

Write-Host "Temporal CLI installed. Version:"
& (Join-Path $installDir "temporal.exe") --version
Write-Host "Open a new PowerShell later if 'temporal' is not immediately found there."
