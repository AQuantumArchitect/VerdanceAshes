# Night preflight (v0.8.4) - abstract world checks, no BAR launch.
param(
  [string]$Workspace = "",
  [switch]$SkipKernelSim,
  [switch]$SkipSnapshot
)

$ErrorActionPreference = "Stop"
$PlayerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsDir = Split-Path -Parent $PlayerDir
. (Join-Path $ScriptsDir "_common.ps1")

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
Write-Host "=== Verdance NIGHT PREFLIGHT ==="
Write-Host "Workspace: $Workspace"

$report = [ordered]@{
  schemaVersion = "verdance-night-preflight/1.0"
  workspace     = $Workspace
  startedAt     = (Get-Date).ToString("o")
  checks        = @()
  ok            = $true
}

function Add-Check([string]$Name, [bool]$Ok, [string]$Detail = "") {
  $script:report.checks += [ordered]@{ name = $Name; ok = $Ok; detail = $Detail }
  if (-not $Ok) { $script:report.ok = $false }
  $mark = if ($Ok) { "PASS" } else { "FAIL" }
  Write-Host ("  [{0}] {1} {2}" -f $mark, $Name, $Detail)
}

# Version
$verPath = Join-Path $Workspace "VERSION"
$version = if (Test-Path $verPath) { ((Get-Content -Raw $verPath).Trim() -split "[\r\n]+")[0].Trim() } else { "?" }
Add-Check "version" ($version -match "^0\.8\.") "VERSION=$version"

# Parse-check critical player scripts (ASCII / no broken quotes)
$psFiles = @(
  (Join-Path $PlayerDir "reset_campaign.ps1"),
  (Join-Path $PlayerDir "setup_play.ps1"),
  (Join-Path $PlayerDir "night_preflight.ps1")
)
$parseOk = $true
foreach ($f in $psFiles) {
  if (-not (Test-Path $f)) { $parseOk = $false; continue }
  $tokens = $null
  $errs = $null
  $null = [System.Management.Automation.Language.Parser]::ParseFile($f, [ref]$tokens, [ref]$errs)
  if ($errs -and $errs.Count -gt 0) {
    $parseOk = $false
    Write-Host "  parse error in $f : $($errs[0])"
  }
}
Add-Check "player_scripts_parse" $parseOk

# Snapshot campaign state
if (-not $SkipSnapshot) {
  $snapDir = Join-Path $Workspace "state\backups\pre_night_playtest"
  New-Item -ItemType Directory -Force -Path $snapDir | Out-Null
  $statePath = Join-Path $Workspace "state\campaign_state.json"
  if (Test-Path $statePath) {
    $dest = Join-Path $snapDir ("campaign_state_{0}.json" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
    Copy-Item -Force $statePath $dest
    Add-Check "snapshot" $true $dest
  } else {
    Add-Check "snapshot" $true "no campaign_state yet"
  }
}

$py = Get-VerdancePython -Workspace $Workspace
$env:PYTHONPATH = (Join-Path $Workspace "tools")
Write-Host "Python: $py"

# Unit tests (theater + multirate). PS wraps python stderr as errors; use Continue.
$prev = Get-Location
Set-Location $Workspace
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
  $testOut = & $py -m unittest tests.test_offscreen_multirate_v084 tests.test_theater_home_v083 -v 2>&1 | ForEach-Object { "$_" }
  $testCode = $LASTEXITCODE
  $testOut | ForEach-Object { Write-Host $_ }
  $okTests = ($testCode -eq 0) -or (($testOut -join "`n") -match "(?m)^OK\s*$")
  Add-Check "unittest_v084" $okTests "exit=$testCode"
} catch {
  Add-Check "unittest_v084" $false "$_"
}

# Offscreen clash self-test
try {
  $clashOut = & $py -c "import offscreen_clash_v1 as c; c.self_test()" 2>&1 | ForEach-Object { "$_" }
  $clashOut | ForEach-Object { Write-Host $_ }
  Add-Check "clash_self_test" ($LASTEXITCODE -eq 0 -or (($clashOut -join "`n") -match "self_test OK"))
} catch {
  Add-Check "clash_self_test" $false "$_"
}

# Kernel sim (abstract multi-sortie)
if (-not $SkipKernelSim) {
  try {
    $simOut = & $py (Join-Path $Workspace "tools\kernel_campaign_sim_v1.py") --workspace $Workspace --sorties 6 --seeds 3 --write 2>&1 | ForEach-Object { "$_" }
    $simCode = $LASTEXITCODE
    $simOut | ForEach-Object { Write-Host $_ }
    $nightWorld = Join-Path $Workspace "outbox\night_world.latest.json"
    $simOk = ($simCode -eq 0) -and (Test-Path $nightWorld)
    if ($simOk) {
      Add-Check "kernel_sim" $true "night_world.latest.json"
    } else {
      Add-Check "kernel_sim" $false "exit=$simCode"
    }
  } catch {
    Add-Check "kernel_sim" $false "$_"
  }
} else {
  Add-Check "kernel_sim" $true "skipped"
}

# Defaults smoke from engine (temp script avoids -c quoting issues)
try {
  $tmpPy = Join-Path $env:TEMP "va_night_defaults_check.py"
  $wsEsc = $Workspace.Replace("\", "\\")
  @(
    "from pathlib import Path"
    "from verdance_story_engine_v1 import default_v1_state, bp_access, ensure_commerce"
    "s = default_v1_state()"
    "ensure_commerce(s, Path(r'$Workspace'))"
    "rep = s.get('reputation') or {}"
    "home = s.get('sessionHomeMap')"
    "a = bp_access(s)"
    "print('rep', rep.get('armada'), rep.get('cortex'))"
    "print('home', home)"
    "print('bpmax', a.get('maxPlayerBuildPower'))"
    "assert int(rep.get('armada') or 0) <= 25"
    "assert int(rep.get('cortex') or 0) >= 60"
    "assert home == 'the_rock_jungle'"
    "assert int(a.get('maxPlayerBuildPower', -1)) == 0"
    "print('defaults_ok')"
  ) | Set-Content -Encoding ASCII $tmpPy
  $out = & $py $tmpPy 2>&1 | ForEach-Object { "$_" }
  $out | ForEach-Object { Write-Host $_ }
  Add-Check "defaults_rep_home_bp" ($LASTEXITCODE -eq 0 -or (($out -join "`n") -match "defaults_ok"))
  Remove-Item -Force $tmpPy -ErrorAction SilentlyContinue
} catch {
  Add-Check "defaults_rep_home_bp" $false "$_"
}

$ErrorActionPreference = $prevEap
Set-Location $prev

$report.finishedAt = (Get-Date).ToString("o")
$report.version = $version
$outbox = Join-Path $Workspace "outbox"
New-Item -ItemType Directory -Force -Path $outbox | Out-Null
$outPath = Join-Path $outbox "night_preflight.latest.json"
($report | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 $outPath
Write-Host ""
Write-Host "Wrote $outPath"
if ($report.ok) {
  Write-Host "=== NIGHT PREFLIGHT PASS ==="
  exit 0
} else {
  Write-Host "=== NIGHT PREFLIGHT FAIL ==="
  exit 1
}
