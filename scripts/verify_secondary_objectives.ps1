param(
  [string]$Workspace = "",
  [string]$ScenarioPath = "",
  [int]$TimeoutSeconds = 720
)

# Drop 4 Wave 1: proves the secondary-objective victory gate on the REAL
# engine. Needs a scenario whose missionBase.secondaries has at least one
# REQUIRED mark (mission 6+ seeds; compile one with build_next_mission_v1.ps1
# from a mid-campaign state).
#
# Order of proof in one headless run:
#   1) VA_SECONDARY_ARMED groups=N required=M      (setup booked the ledger)
#   2) va_test_killobjective_frame=450             -> VA_OBJECTIVE_COMPLETE
#      ... but NOT VA_ALL_OBJECTIVES_DONE yet      (the gate holds)
#   3) va_test_secondary_frame=900                 -> VA_SECONDARY_COMPLETE
#      -> VA_ALL_OBJECTIVES_DONE                   (the gate opens)
# The probe also asserts the DONE echo appears AFTER the secondary kill, not
# before -- that ordering IS the required-mark gate.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace

if (-not $ScenarioPath) {
  $ScenarioPath = Join-Path $Workspace "data\scenarios\generated\next_mission_intent.playable.json"
}
if (!(Test-Path $ScenarioPath)) { throw "Scenario not found: $ScenarioPath (run build_next_mission_v1.ps1 first)" }

$scenario = Get-Content -Raw -LiteralPath $ScenarioPath | ConvertFrom-Json
$secondaries = @()
if ($scenario.missionBase -and $scenario.missionBase.PSObject.Properties["secondaries"]) {
  $secondaries = @($scenario.missionBase.secondaries)
}
$requiredCount = @($secondaries | Where-Object { $_.required }).Count
if ($secondaries.Count -eq 0) {
  throw "Scenario has no secondary objectives -- compile a mission-6+ seed (the escalation ladder adds them) and re-run."
}
Write-Host ("Secondaries under test: {0} total, {1} required" -f $secondaries.Count, $requiredCount)

$inboxExisted = Test-Path $config.resultInbox
$inboxStamp = if ($inboxExisted) { (Get-Item -LiteralPath $config.resultInbox).LastWriteTimeUtc } else { $null }

& (Join-Path $ScriptDir "install_playable_slice.ps1") -Workspace $Workspace `
  -ScenarioPath $ScenarioPath -Headless -TimeoutSeconds $TimeoutSeconds `
  -ExtraModOptions "va_headless_autostart=1;va_headless_fastwin=0;va_headless_quit=1;va_test_killobjective_frame=450;va_test_secondary_frame=900" `
  -DebugCommandsOverride "2000:quitforce"

$log = Get-Content -Raw -LiteralPath $config.infolog
$checks = [ordered]@{}
$checks["VA_BRIDGE_LOADED"] = ($log -match "VA_BRIDGE_LOADED")
$checks["VA_SECONDARY_ARMED"] = ($log -match "VA_SECONDARY_ARMED groups=[0-9]+ required=$requiredCount")
$checks["VA_TEST_KILLOBJECTIVE ran"] = ($log -match "VA_TEST_KILLOBJECTIVE destroyed=[0-9]+")
$checks["VA_OBJECTIVE_COMPLETE"] = ($log -match "VA_OBJECTIVE_COMPLETE")
$checks["VA_TEST_KILLSECONDARY ran"] = ($log -match "VA_TEST_KILLSECONDARY destroyed=[0-9]+")
$checks["VA_SECONDARY_COMPLETE"] = ($log -match "VA_SECONDARY_COMPLETE id=")
if ($requiredCount -gt 0) {
  $checks["VA_ALL_OBJECTIVES_DONE seen"] = ($log -match "VA_ALL_OBJECTIVES_DONE")
  # The gate itself: ALL_DONE must come from the secondary kill, not the
  # primary. VA_TEST_KILLSECONDARY (frame 900) precedes VA_ALL_OBJECTIVES_DONE.
  $killIdx = $log.IndexOf("VA_TEST_KILLSECONDARY")
  $doneIdx = $log.IndexOf("VA_ALL_OBJECTIVES_DONE")
  $checks["required gate held until secondary kill"] = ($killIdx -ge 0 -and $doneIdx -gt $killIdx)
}

$failed = @()
foreach ($k in $checks.Keys) {
  $mark = if ($checks[$k]) { "PASS" } else { $failed += $k; "FAIL" }
  Write-Host "$mark  $k"
}

# Phantom-advance gotcha: a probe run must never leave a result the campaign
# could accidentally advance on.
if (Test-Path $config.resultInbox) {
  $newStamp = (Get-Item -LiteralPath $config.resultInbox).LastWriteTimeUtc
  if (-not $inboxExisted -or $newStamp -ne $inboxStamp) {
    Remove-Item -LiteralPath $config.resultInbox -Force -Confirm:$false
    Write-Host "Removed probe-written result from inbox (phantom-advance guard)."
  }
}

if ($failed.Count -gt 0) {
  throw "Secondary-objective verification failed: $($failed -join ', '). Check $($config.infolog)"
}
Write-Host ("Secondary-objective verification passed ({0} marks, {1} required)." -f $secondaries.Count, $requiredCount)
