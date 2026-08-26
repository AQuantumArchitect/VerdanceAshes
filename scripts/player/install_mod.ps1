# Player-path alias: copy mutator into BAR games.
param(
  [string]$Workspace = "",
  [switch]$Junction
)
$ErrorActionPreference = "Stop"
$ScriptsDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if ($Junction) {
  & (Join-Path $ScriptsDir "install_mod_archive.ps1") -Workspace $Workspace
} else {
  & (Join-Path $ScriptsDir "install_mod_archive.ps1") -Workspace $Workspace -Copy
}
