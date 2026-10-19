# Player-path: install / repoint VerdanceAshes.sdd into BAR games.
# Default for playtests = Deployed (My Games mod).
# -Mode Workspace = live-edit junction into the dev repo (debug only).
# -Copy = frozen snapshot copy (customer / no junction).
param(
  [string]$Workspace = "",
  [ValidateSet("Deployed", "Workspace")]
  [string]$Mode = "Deployed",
  [switch]$Copy,
  [switch]$Junction
)
$ErrorActionPreference = "Stop"
$PlayerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsDir = Split-Path -Parent $PlayerDir

if ($Copy) {
  & (Join-Path $ScriptsDir "install_mod_archive.ps1") -Workspace $Workspace -Copy
  return
}

# Legacy -Junction switch meant "workspace live-edit".
if ($Junction) { $Mode = "Workspace" }

& (Join-Path $PlayerDir "point_bar_mod.ps1") -Mode $Mode -Workspace $Workspace
