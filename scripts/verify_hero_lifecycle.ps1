param(
  [string]$Workspace = "",
  [string]$ScenarioPath = "",
  [int]$TimeoutSeconds = 720
)

# Proves the named-hero wreck lifecycle end to end in a real headless BAR run:
# 1. frame 400  - scripted kill of a hero (va_test_killhero_frames) -> wreck -> VA_HERO_DOWN
# 2. frame 550  - scripted rez-bot resurrection order (va_test_rezwreck_frame) -> VA_HERO_RECOVERED
# 3. frame 3600 - scripted kill of a hero again -> wreck
# 4. frame 3700 - scripted wreck destruction (va_test_destroywreck_frame) -> VA_HERO_LOST
#                 -> mission-critical hero => VA_TERMINAL defeat reason=hero_lost_*
# The result marker must carry heroResults with the lost hero dead.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace

if (-not $ScenarioPath) {
  $ScenarioPath = Join-Path $Workspace "data\scenarios\generated\next_mission_intent.playable.json"
}
if (!(Test-Path $ScenarioPath)) { throw "Scenario not found: $ScenarioPath (run build_next_mission_v1.ps1 first)" }

& (Join-Path $ScriptDir "install_playable_slice.ps1") -Workspace $Workspace `
  -ScenarioPath $ScenarioPath -Headless -TimeoutSeconds $TimeoutSeconds `
  -ExtraModOptions "va_headless_autostart=1;va_headless_fastwin=0;va_headless_quit=1;va_test_killhero_frames=400,3600;va_test_rezwreck_frame=550;va_test_destroywreck_frame=3700" `
  -DebugCommandsOverride "5400:quitforce"

$log = Get-Content -Raw -LiteralPath $config.infolog
$checks = [ordered]@{
  "VA_HERO_SPAWNED"            = ($log -match "VA_HERO_SPAWNED id=\S+")
  "VA_TEST_KILLHERO"           = ($log -match "VA_TEST_KILLHERO id=\S+")
  "VA_HERO_DOWN (wreck found)" = ($log -match "VA_HERO_DOWN id=\S+")
  "VA_TEST_REZWRECK ordered"   = ($log -match "VA_TEST_REZWRECK feature=")
  "VA_HERO_RECOVERED"          = ($log -match "VA_HERO_RECOVERED id=\S+")
  "VA_HERO_LOST"               = ($log -match "VA_HERO_LOST id=\S+")
  "VA_TERMINAL hero defeat"    = ($log -match "VA_TERMINAL status=defeat reason=hero_lost_")
  "heroResults dead in result" = ($log -match 'VA_RESULT_JSON_COMPACT .*"heroResults":\{.*"status":"dead"')
}

$failed = @()
foreach ($k in $checks.Keys) {
  $mark = if ($checks[$k]) { "PASS" } else { $failed += $k; "FAIL" }
  Write-Host "$mark  $k"
}
if ($failed.Count -gt 0) {
  throw "Hero lifecycle verification failed: $($failed -join ', '). Check $($config.infolog)"
}
Write-Host ""
Write-Host "Hero lifecycle verification passed."
