# Player-path alias — kernel may call this; forwards to build_next_mission_v1.
param(
  [string]$Workspace = "",
  [switch]$Launch
)
$ErrorActionPreference = "Stop"
$ScriptsDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$args = @{ Workspace = $Workspace }
if ($Launch) { $args.Launch = $true }
& (Join-Path $ScriptsDir "build_next_mission_v1.ps1") @args
