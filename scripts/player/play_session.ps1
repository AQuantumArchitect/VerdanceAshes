# Player-path alias for play_session_v1 (kernel private).
param(
  [string]$Workspace = "",
  [int]$MaxSessionMinutes = 240,
  [int]$MaxMissions = 12,
  [switch]$SessionHost,
  [switch]$NoAutoRelaunch,
  [ValidateSet("visible", "headless-fastwin", "headless-zip")]
  [string]$EngineMode = "visible",
  [string]$StatusPath = ""
)
$ErrorActionPreference = "Stop"
$ScriptsDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$invoke = @{
  Workspace          = $Workspace
  MaxSessionMinutes  = $MaxSessionMinutes
  MaxMissions        = $MaxMissions
  EngineMode         = $EngineMode
}
if ($SessionHost) { $invoke.SessionHost = $true }
if ($NoAutoRelaunch) { $invoke.NoAutoRelaunch = $true }
if ($StatusPath) { $invoke.StatusPath = $StatusPath }
& (Join-Path $ScriptsDir "play_session_v1.ps1") @invoke
