# First-run / re-arm: BAR detect, install mutator, config, hub rebuild.
param(
  [string]$Workspace = "",
  [switch]$Junction
)

$ErrorActionPreference = "Stop"
$PlayerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsDir = Split-Path -Parent $PlayerDir
. (Join-Path $ScriptsDir "_common.ps1")

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
Write-Host "=== Verdance SETUP (player path) ==="
Write-Host "Workspace: $Workspace"

$verFile = Join-Path $Workspace "VERSION"
$version = if (Test-Path $verFile) {
  ((Get-Content -Raw $verFile).Trim() -split "[\r\n]+")[0].Trim()
} else { "0.8.0" }
Write-Host "Version:   $version"

# BAR detect + config + first mission intent (existing helper)
$setupTester = Join-Path $ScriptsDir "setup_tester.ps1"
if (!(Test-Path $setupTester)) { throw "scripts\setup_tester.ps1 missing" }

$setupArgs = @{
  Workspace     = $Workspace
  NonInteractive = $true
}
if ($Junction) { $setupArgs["Junction"] = $true }
& $setupTester @setupArgs

# Prefer a full copy of the mutator into BAR for reliable loads (re-copy after tester)
if (-not $Junction) {
  $install = Join-Path $ScriptsDir "install_mod_archive.ps1"
  & $install -Workspace $Workspace -Copy
}

$py = Get-VerdancePython -Workspace $Workspace
$env:PYTHONPATH = (Join-Path $Workspace "tools")
Write-Host "Python:    $py"
Write-Host "Rebuilding hub surface..."

$prev = Get-Location
Set-Location $Workspace
try {
  # Avoid PowerShell @"..."@ here-strings (broken on LF-only .ps1 in PS 5.1).
  $result = & $py -m verdance_kernel rebuild --workspace $Workspace
  Write-Host "Hub: $result"
  if ($LASTEXITCODE -ne 0) { throw "hub rebuild failed (exit $LASTEXITCODE)" }
} finally {
  Set-Location $prev
}

Write-Host ""
Write-Host "=== SETUP complete (v$version) ==="
Write-Host "Run PLAY.bat from the workspace root:"
Write-Host "  $Workspace\PLAY.bat"
