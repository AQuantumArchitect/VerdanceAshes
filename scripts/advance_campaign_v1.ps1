param(
  [string]$Workspace = "",
  [string]$StatePath = "",
  [string]$ResultPath = "",
  [string]$TelemetryPath = "",
  [switch]$WriteState,
  [switch]$IntentOnly
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent $ScriptDir
if (-not $Workspace) { $Workspace = $WorkspaceRoot }
$Engine = Join-Path $WorkspaceRoot "tools\verdance_story_engine_v1.py"
if (!(Test-Path $Engine)) { throw "Story engine not found: $Engine" }

. (Join-Path $ScriptDir "_common.ps1")
$python = Get-VerdancePython -Workspace $Workspace
$command = if ($IntentOnly) { "intent" } else { "advance" }
$args = @($Engine, $command, "--workspace", $Workspace)
if ($StatePath) { $args += @("--state", $StatePath) }
if (-not $IntentOnly) {
  if ($ResultPath) { $args += @("--result", $ResultPath) }
  if ($TelemetryPath) { $args += @("--telemetry", $TelemetryPath) }
  if ($WriteState) { $args += "--write-state" }
}

& $python @args
if ($LASTEXITCODE -ne 0) { throw "Verdance Story Engine v1 failed with exit code $LASTEXITCODE" }

