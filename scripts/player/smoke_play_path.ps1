# Smoke the consolidated player path (no BAR launch).
param([string]$Workspace = "")

$ErrorActionPreference = "Stop"
$PlayerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsDir = Split-Path -Parent $PlayerDir
. (Join-Path $ScriptsDir "_common.ps1")

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$script:failures = New-Object System.Collections.Generic.List[string]

function Ok([string]$msg) { Write-Host ("  OK  " + $msg) -ForegroundColor Green }
function Bad([string]$msg) {
  Write-Host ("  FAIL " + $msg) -ForegroundColor Red
  $script:failures.Add($msg) | Out-Null
}

Write-Host "=== smoke_play_path ==="
Write-Host ("Workspace: " + $Workspace)

$ver = Join-Path $Workspace "VERSION"
if (Test-Path $ver) {
  $v = ((Get-Content -Raw $ver).Trim() -split "[\r\n]+")[0].Trim()
  Ok ("VERSION = " + $v)
} else {
  Bad "VERSION missing"
}

foreach ($b in @("PLAY.bat", "SETUP.bat", "RESET.bat", "SHIP.bat")) {
  if (Test-Path (Join-Path $Workspace $b)) { Ok $b } else { Bad ($b + " missing at root") }
}
$shipPs1 = Join-Path $Workspace "scripts\ship.ps1"
if (Test-Path $shipPs1) { Ok "scripts\ship.ps1" } else { Bad "scripts\ship.ps1 missing" }
foreach ($p in @("setup_play.ps1", "install_mod.ps1", "build_mission.ps1", "play_session.ps1", "extract_result.ps1")) {
  if (Test-Path (Join-Path $Workspace "scripts\player\$p")) { Ok ("scripts\player\" + $p) } else { Bad ("scripts\player\" + $p + " missing") }
}

$py = $null
try {
  $py = Get-VerdancePython -Workspace $Workspace
  Ok ("Python " + $py)
} catch {
  Bad ("Python: " + $_.Exception.Message)
}

if ($py) {
  $env:PYTHONPATH = (Join-Path $Workspace "tools")
  $out = & $py -c "import verdance_kernel; print(verdance_kernel.__version__)" 2>&1
  if ($LASTEXITCODE -eq 0) {
    Ok ("verdance_kernel " + $out)
  } else {
    Bad ("import verdance_kernel: " + $out)
  }

  $status = & $py -c "from verdance_kernel.api import CampaignKernel; print(CampaignKernel(r'''$Workspace''').status().get('capabilities',{}).get('launch'))" 2>&1
  if ($LASTEXITCODE -eq 0) {
    Ok ("kernel launch capability = " + $status)
  } else {
    Bad ("kernel status: " + $status)
  }
}

try {
  $cfg = Get-VerdanceConfig -Workspace $Workspace
  if (Test-Path $cfg.barDataRoot) {
    Ok ("BAR data " + $cfg.barDataRoot)
  } else {
    Bad "BAR data root missing"
  }
  $modinfo = Join-Path $cfg.modSdd "modinfo.lua"
  if (Test-Path $modinfo) {
    Ok ("Mutator installed at " + $cfg.modSdd)
  } else {
    Bad "Mutator not in BAR games - run SETUP.bat"
  }
} catch {
  Bad ("BAR/config: " + $_.Exception.Message)
}

$hub = Join-Path $Workspace "app\showoff\hub_state.json"
$show = Join-Path $Workspace "app\showoff\index.html"
if (Test-Path $show) { Ok "showoff index.html" } else { Bad "app/showoff/index.html missing" }
if (Test-Path $hub) { Ok "hub_state.json present" } else { Bad "hub_state.json missing - run SETUP.bat" }

foreach ($s in @("build_next_mission_v1.ps1", "play_session_v1.ps1", "extract_latest_result.ps1", "install_mod_archive.ps1")) {
  if (Test-Path (Join-Path $ScriptsDir $s)) {
    Ok ("scripts\" + $s)
  } else {
    Bad ("scripts\" + $s + " missing")
  }
}

Write-Host ""
if ($script:failures.Count -eq 0) {
  Write-Host "SMOKE PASS - run PLAY.bat" -ForegroundColor Green
  exit 0
}

Write-Host ("SMOKE FAIL (" + $script:failures.Count + "):") -ForegroundColor Red
foreach ($f in $script:failures) {
  Write-Host ("  - " + $f)
}
exit 1
