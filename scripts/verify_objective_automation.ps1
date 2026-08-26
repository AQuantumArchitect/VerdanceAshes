param(
  [string]$Workspace = "",
  [string]$ScenarioPath = "",
  [int]$TimeoutSeconds = 720
)

# Proves the gadget's REAL objective detection (no fastwin): spawns the mission,
# destroys the objective targets at a scripted frame (va_test_killobjective_frame
# modoption), and expects the gadget itself to complete the objective, run the
# extraction hold, and emit a genuine victory result marker.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace

if (-not $ScenarioPath) {
  $ScenarioPath = Join-Path $Workspace "data\scenarios\generated\next_mission_intent.playable.json"
}
if (!(Test-Path $ScenarioPath)) { throw "Scenario not found: $ScenarioPath (run build_next_mission_v1.ps1 first)" }

$infologBaseline = 0
if (Test-Path $config.infolog) { $infologBaseline = (Get-Item -LiteralPath $config.infolog).Length }

# Extraction is now a distinct LZ (not the deploy zone), so the probe teleports
# the idle player force onto it after the objective falls - validating the full
# objective -> extraction-hold -> victory loop.
& (Join-Path $ScriptDir "install_playable_slice.ps1") -Workspace $Workspace `
  -ScenarioPath $ScenarioPath -Headless -TimeoutSeconds $TimeoutSeconds `
  -ExtraModOptions "va_headless_autostart=1;va_headless_fastwin=0;va_headless_quit=1;va_test_killobjective_frame=600;va_test_teleport_extract_frame=900" `
  -DebugCommandsOverride "4500:quitforce"

$log = Get-Content -Raw -LiteralPath $config.infolog
$checks = [ordered]@{
  "VA_OBJECTIVE_ARMED"       = ($log -match "VA_OBJECTIVE_ARMED kind=\S+ targets=([1-9][0-9]*)")
  "VA_OBJECTIVE_TARGET_DOWN" = ($log -match "VA_OBJECTIVE_TARGET_DOWN")
  "VA_OBJECTIVE_COMPLETE"    = ($log -match "VA_OBJECTIVE_COMPLETE .*how=target_destroyed")
  "VA_TERMINAL victory"      = ($log -match "VA_TERMINAL status=victory reason=(extracted|objective_complete_no_extraction_zone)")
  "VA_RESULT_JSON emitted"   = ($log -match "VA_RESULT_JSON_COMPACT .*""objectiveComplete"":true")
}

$failed = @()
foreach ($k in $checks.Keys) {
  $mark = if ($checks[$k]) { "PASS" } else { $failed += $k; "FAIL" }
  Write-Host "$mark  $k"
}
if ($failed.Count -gt 0) {
  throw "Objective automation verification failed: $($failed -join ', '). Check $($config.infolog)"
}

& (Join-Path $ScriptDir "extract_latest_result.ps1") -Workspace $Workspace
$result = Get-Content $config.resultInbox -Raw | ConvertFrom-Json
Write-Host ""
Write-Host "Result: status=$($result.status) terminalReason=$($result.terminalReason) objectiveComplete=$($result.objectiveComplete) extractionStatus=$($result.extractionStatus) destroyed=$($result.destroyedObjectiveIds -join ',')"
if ($result.status -ne "victory" -or -not $result.objectiveComplete) {
  throw "Extracted result does not show a genuine objective victory."
}
Write-Host "Objective automation verification passed."
