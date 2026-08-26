# Phase 1→EXE: freeze the product launcher with PyInstaller when available.
# Usage (from workspace root):
#   powershell -File scripts\package_kernel_exe.ps1
#
# Produces: export\ship\VerdanceAshes.exe  (console launcher)

param(
  [string]$Workspace = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
if (-not $OutDir) { $OutDir = Join-Path $Workspace "export\ship" }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$py = $env:VERDANCE_PY
if (-not $py) { $py = "python" }

Write-Host "Checking PyInstaller..."
& $py -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "PyInstaller not installed. Install with:"
  Write-Host "  $py -m pip install pyinstaller"
  Write-Host "Then re-run this script. Until then use: app\bin\PLAY.bat"
  exit 2
}

$entry = Join-Path $Workspace "tools\verdance_kernel\__main__.py"
$tools = Join-Path $Workspace "tools"
$showoff = Join-Path $Workspace "app\showoff"

Write-Host "Building VerdanceAshes.exe ..."
& $py -m PyInstaller `
  --noconfirm `
  --clean `
  --name VerdanceAshes `
  --console `
  --paths $tools `
  --add-data "$showoff;app/showoff" `
  --distpath $OutDir `
  --workpath (Join-Path $OutDir "build") `
  --specpath (Join-Path $OutDir "spec") `
  $entry

Write-Host "Done. Run: $OutDir\VerdanceAshes\VerdanceAshes.exe"
Write-Host "Note: full ship still needs workspace data (state, scripts, mod) beside the EXE."
