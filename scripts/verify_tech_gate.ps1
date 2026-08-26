param(
  [string]$Workspace = "",
  [string]$ScenarioPath = "",
  [int]$TimeoutSeconds = 720
)

# Drop 3 Wave 1: proves the act tech gate on the REAL engine. The gadget's
# va_test_techgate_frame hook spawns a con bot at the deploy beacon, echoes the
# gate's verdict for a def matrix (VA_TEST_TECHGATE def=<name> allowed=<bool>),
# and issues a real T2-lab build order so the engine's AllowUnitCreation path
# produces a genuine VA_TECH_GATE_DENY when the gate is armed.
#
# Expected verdicts are computed from the scenario's own missionBase.techPolicy,
# so the same probe covers act-1 (no structures), act-2 (T1 build only), and
# act-3 (gate off) seeds. The resurrect exemption is live-covered separately by
# verify_hero_lifecycle.ps1 (its rez step runs under act-1 policy).

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
$techPolicy = if ($scenario.missionBase -and $scenario.missionBase.PSObject.Properties["techPolicy"]) { $scenario.missionBase.techPolicy } else { $null }
$buildTech = if ($techPolicy -and $null -ne $techPolicy.buildTech) { [int]$techPolicy.buildTech } else { 3 }
$buildStructures = if ($techPolicy -and $null -ne $techPolicy.buildStructures) { [bool]$techPolicy.buildStructures } else { $true }
Write-Host "Tech policy under test: buildTech=$buildTech buildStructures=$buildStructures"

# The gadget's probe matrix: def -> @(isStructure, techLevel)
$matrix = [ordered]@{
  legalab  = @($true, 2)   # T2 bot lab
  leglab   = @($true, 1)   # T1 bot lab
  legsolar = @($true, 1)   # T1 solar
  legcen   = @($false, 1)  # T1 assault bot
  legshot  = @($false, 2)  # T2 riot walker
}
$expected = [ordered]@{}
foreach ($def in $matrix.Keys) {
  $isStruct = [bool]$matrix[$def][0]
  $tech = [int]$matrix[$def][1]
  $allowed = ($tech -le $buildTech) -and ($buildStructures -or -not $isStruct)
  $expected[$def] = $allowed
}
$anyDenied = @($expected.Values | Where-Object { -not $_ }).Count -gt 0

$inboxExisted = Test-Path $config.resultInbox
$inboxStamp = if ($inboxExisted) { (Get-Item -LiteralPath $config.resultInbox).LastWriteTimeUtc } else { $null }

& (Join-Path $ScriptDir "install_playable_slice.ps1") -Workspace $Workspace `
  -ScenarioPath $ScenarioPath -Headless -TimeoutSeconds $TimeoutSeconds `
  -ExtraModOptions "va_headless_autostart=1;va_headless_fastwin=0;va_headless_quit=1;va_test_techgate_frame=450" `
  -DebugCommandsOverride "1500:quitforce"

$log = Get-Content -Raw -LiteralPath $config.infolog
$checks = [ordered]@{}
$checks["VA_BRIDGE_LOADED"] = ($log -match "VA_BRIDGE_LOADED")
if ($anyDenied) {
  # A constrained seed must arm the gate and announce it.
  $checks["VA_TECH_GATE armed"] = ($log -match "VA_TECH_GATE act=")
}
$checks["VA_TEST_TECHGATE_DONE"] = ($log -match "VA_TEST_TECHGATE_DONE builder=[0-9]+")
foreach ($def in $expected.Keys) {
  $want = if ($expected[$def]) { "true" } else { "false" }
  $checks["verdict $def=$want"] = ($log -match ("VA_TEST_TECHGATE def=" + $def + " allowed=" + $want))
}
if ($anyDenied) {
  $checks["VA_TECH_GATE_DENY seen"] = ($log -match "VA_TECH_GATE_DENY")
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
  throw "Tech gate verification failed: $($failed -join ', '). Check $($config.infolog)"
}
Write-Host "Tech gate verification passed (buildTech=$buildTech buildStructures=$buildStructures)."
