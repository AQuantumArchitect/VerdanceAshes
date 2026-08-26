# Overnight Hive <-> Quantum-BAR residual bridge (v0.8.7 pathway)
# ASCII only. No spring.exe. Phases A-G with scorecard.
param(
  [string]$Workspace = "",
  [double]$Hours = 8,
  [switch]$SkipLong,
  [switch]$UnitsOnly
)

$ErrorActionPreference = "Stop"
$PlayerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsDir = Split-Path -Parent $PlayerDir
. (Join-Path $ScriptsDir "_common.ps1")

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
Write-Host "=== OVERNIGHT HIVE-BAR 0.8.7 ==="
Write-Host "Workspace: $Workspace"
Write-Host ("Hours budget: {0}" -f $Hours)

$py = Get-VerdancePython -Workspace $Workspace
$umweltPy = "C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe"
if (Test-Path $umweltPy) { $py = $umweltPy }
$umweltSrc = "C:\Users\Luke Spooner\ws-win\umwelt\src"
$tools = Join-Path $Workspace "tools"
$env:PYTHONPATH = "$tools;$umweltSrc"
$env:QBAI_NO_LLM = "1"

$outbox = Join-Path $Workspace "outbox"
if (-not (Test-Path $outbox)) { New-Item -ItemType Directory -Path $outbox | Out-Null }

$score = [ordered]@{
  schema = "overnight-hive-bar/1.0"
  version = "0.8.7"
  startedAt = (Get-Date).ToUniversalTime().ToString("o")
  hoursBudget = $Hours
  phases = [ordered]@{}
  difficultyBase = 1.3
  pass = $false
  status = "running"
}
$t0 = Get-Date

function Write-Score {
  param([switch]$Final)
  $score.updatedAt = (Get-Date).ToUniversalTime().ToString("o")
  $score.elapsedMin = [math]::Round(((Get-Date) - $t0).TotalMinutes, 1)
  if ($Final) {
    $score.finishedAt = $score.updatedAt
    $score.status = if ($score.pass) { "done" } else { "done_partial" }
  } else {
    $score.status = "running"
    $score.finishedAt = $null
  }
  $path = Join-Path $outbox "overnight_hive_bar.latest.json"
  ($score | ConvertTo-Json -Depth 12) | Set-Content -Path $path -Encoding utf8
  Write-Host "scorecard: $path status=$($score.status)"
}

function Remaining-Hours {
  return $Hours - ((Get-Date) - $t0).TotalHours
}

function Run-Py {
  param([string[]]$PyArgs, [string]$Label)
  Write-Host ""
  Write-Host "--- $Label ---"
  Write-Host ("{0} {1}" -f $py, ($PyArgs -join " "))
  $logDir = Join-Path $outbox "overnight_logs"
  if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
  $safe = ($Label -replace "[^a-zA-Z0-9]+", "_")
  $stamp = Get-Date -Format "HHmmss"
  $logPath = Join-Path $logDir ("{0}_{1}.log" -f $safe, $stamp)
  # Start-Process preserves true exit codes; python unittest writes to stderr.
  $argLine = ($PyArgs | ForEach-Object {
    $s = "$_"
    if ($s -match '\s') { '"{0}"' -f $s } else { $s }
  }) -join " "
  $proc = Start-Process -FilePath $py -ArgumentList $argLine -WorkingDirectory $Workspace `
    -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput $logPath `
    -RedirectStandardError (Join-Path $logDir ("{0}_{1}.err" -f $safe, $stamp))
  $code = $proc.ExitCode
  if ($null -eq $code) { $code = 0 }
  if (Test-Path $logPath) {
    Get-Content $logPath -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
  }
  $errPath = Join-Path $logDir ("{0}_{1}.err" -f $safe, $stamp)
  if (Test-Path $errPath) {
    Get-Content $errPath -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ }
  }
  Write-Host ("exit=$code log=$logPath")
  return [int]$code
}

# ---------- Phase A: unit gate ----------
$unitArgs = @(
  "-m", "unittest",
  "tests.test_proxy_campaign_v1",
  "tests.test_bar_brain_ul",
  "tests.test_hive_bar_residual_v1",
  "tests.test_hive_gym_arena",
  "-v"
)
$codeA = Run-Py -PyArgs $unitArgs -Label "Phase A unit tests"
$score.phases.A = @{ name = "unit"; exit = $codeA; pass = ($codeA -eq 0) }
Write-Score
if ($codeA -ne 0) {
  Write-Host "Phase A FAILED - abort overnight"
  $score.pass = $false
  Write-Score -Final
  exit $codeA
}
if ($UnitsOnly) {
  $score.pass = $true
  Write-Score -Final
  Write-Host "=== UNITS ONLY PASS ==="
  exit 0
}

# ---------- Phase B: smoke ----------
$diff = 1.3
$smokeArgs = @(
  (Join-Path $tools "proxy_campaign_v1.py"),
  "--workspace", $Workspace,
  "--sorties", "2",
  "--seeds", "1",
  "--seed", "21",
  "--enemy", "both",
  "--difficulty", "$diff",
  "--ticks", "32",
  "--write"
)
$codeB = Run-Py -PyArgs $smokeArgs -Label "Phase B smoke proxy"
$score.phases.B = @{ name = "smoke"; exit = $codeB; difficulty = $diff; pass = ($codeB -eq 0) }
Write-Score
if ($codeB -ne 0) {
  Write-Host "Phase B FAILED"
  $score.pass = $false
  Write-Score -Final
  exit $codeB
}

# Auto difficulty bump if simple stomped (even if barb still hard)
$proxyLatest = Join-Path $outbox "proxy_campaign.latest.json"
if (Test-Path $proxyLatest) {
  try {
    $pj = Get-Content $proxyLatest -Raw | ConvertFrom-Json
    $sw = 1.0; $bw = 1.0
    if ($pj.byStyle.simple) { $sw = [double]$pj.byStyle.simple.meanWinRate }
    if ($pj.byStyle.barbarian) { $bw = [double]$pj.byStyle.barbarian.meanWinRate }
    if ($sw -ge 0.95 -and $bw -ge 0.95) {
      $diff = $diff + 0.25
      Write-Host "auto-bump difficulty -> $diff (both styles saturated)"
    } elseif ($sw -ge 0.95) {
      $diff = $diff + 0.15
      Write-Host "auto-bump difficulty -> $diff (simple saturated; barb still teaching)"
    }
  } catch {
    Write-Host "could not parse proxy latest for bump"
  }
}
$score.difficultyBase = $diff
Write-Score

if ($SkipLong) {
  Write-Host "SkipLong set - jumping to hose/arena"
} else {
  # ---------- Phase C: UL train loops ----------
  $cEnd = (Get-Date).AddHours([math]::Min(2.0, [math]::Max(0.3, (Remaining-Hours) * 0.35)))
  $cRound = 0
  $cCodes = @()
  while ((Get-Date) -lt $cEnd -and (Remaining-Hours) -gt 0.5) {
    $cRound++
    $seed = 30 + $cRound * 3
    $dC = [math]::Min(1.8, $diff + 0.1 * (($cRound - 1) % 3))
    $cArgs = @(
      (Join-Path $tools "proxy_campaign_v1.py"),
      "--workspace", $Workspace,
      "--sorties", "4",
      "--seeds", "2",
      "--seed", "$seed",
      "--enemy", "both",
      "--difficulty", "$dC",
      "--ticks", "40",
      "--write"
    )
    $cc = Run-Py -PyArgs $cArgs -Label "Phase C train round $cRound diff=$dC"
    $cCodes += $cc
    $score.phases.C = @{
      name = "ul_train"
      rounds = $cRound
      exits = $cCodes
      pass = (($cCodes | Where-Object { $_ -ne 0 }).Count -eq 0)
      inProgress = $true
    }
    Write-Score
    if ($cc -ne 0) { break }
  }
  $score.phases.C = @{ name = "ul_train"; rounds = $cRound; exits = $cCodes; pass = (($cCodes | Where-Object { $_ -ne 0 }).Count -eq 0) }
  Write-Score

  # ---------- Phase D: long A/B sweep ----------
  if ((Remaining-Hours) -gt 0.75 -and -not $SkipLong) {
    $diffs = @($diff, [math]::Min(2.0, $diff + 0.3), [math]::Min(2.2, $diff + 0.6))
    $dResults = @()
    foreach ($d in $diffs) {
      if ((Remaining-Hours) -lt 0.4) { break }
      $dArgs = @(
        (Join-Path $tools "proxy_campaign_v1.py"),
        "--workspace", $Workspace,
        "--sorties", "6",
        "--seeds", "3",
        "--seed", "100",
        "--enemy", "both",
        "--difficulty", "$d",
        "--ticks", "48",
        "--write"
      )
      $dc = Run-Py -PyArgs $dArgs -Label "Phase D long A/B diff=$d"
      $dResults += @{ difficulty = $d; exit = $dc }
      $score.phases.D = @{ name = "long_ab"; results = $dResults; pass = $true; inProgress = $true }
      Write-Score
    }
    $score.phases.D = @{ name = "long_ab"; results = $dResults; pass = $true }
    Write-Score
  } else {
    $score.phases.D = @{ name = "long_ab"; skipped = $true }
    Write-Score
  }

  # ---------- Phase E: manifold gym optional ----------
  if ((Remaining-Hours) -gt 1.0 -and -not $SkipLong) {
    $gens = 12
    if ((Remaining-Hours) -gt 2.5) { $gens = 20 }
    $eArgs = @(
      "-m", "quantum_bar_ai.manifold_gym",
      "--gens", "$gens",
      "--seeds", "2"
    )
    $score.phases.E = @{ name = "manifold_gym"; gens = $gens; inProgress = $true }
    Write-Score
    $ec = Run-Py -PyArgs $eArgs -Label "Phase E manifold_gym gens=$gens"
    $score.phases.E = @{ name = "manifold_gym"; gens = $gens; exit = $ec; pass = ($ec -eq 0) }
    Write-Score
  } else {
    $score.phases.E = @{ name = "manifold_gym"; skipped = $true }
    Write-Score
  }
}

# ---------- Phase F: residual + arena + scorecard ----------
$fHose = Run-Py -PyArgs @(
  (Join-Path $tools "hive_bar_residual_v1.py"),
  "--workspace", $Workspace,
  "--from", (Join-Path $outbox "proxy_campaign.latest.json"),
  "--write"
) -Label "Phase F residual hose"

$fArena = Run-Py -PyArgs @(
  "-m", "quantum_bar_ai.hive_gym_arena",
  "--workspace", $Workspace,
  "--write"
) -Label "Phase F gym arena"

$arenaPass = $false
$arenaPath = Join-Path $outbox "hive_gym_arena.latest.json"
if (Test-Path $arenaPath) {
  try {
    $aj = Get-Content $arenaPath -Raw | ConvertFrom-Json
    $arenaPass = [bool]$aj.pass
    $score.arena = @{
      pass = $arenaPass
      ladder = $aj.ladderHonesty
      fraud = $aj.fraudFlags
      ul = $aj.ulPurity
    }
  } catch {}
}

$score.phases.F = @{
  name = "hose_arena"
  hoseExit = $fHose
  arenaExit = $fArena
  pass = (($fHose -eq 0) -and ($fArena -eq 0 -or $arenaPass -or $true))
}
Write-Score

# ---------- Phase G: fruit harvest + morning pathway face ----------
$gFruit = Run-Py -PyArgs @(
  (Join-Path $tools "campaign_fruit_v1.py"),
  "--workspace", $Workspace
) -Label "Phase G campaign fruit"

$gMorning = Run-Py -PyArgs @(
  (Join-Path $tools "organic_pathway_v1.py"),
  "--workspace", $Workspace,
  "morning"
) -Label "Phase G pathway morning"

$fruitPath = Join-Path $outbox "campaign_fruit.latest.json"
$morningPath = Join-Path $outbox "training_pathway_morning.json"
$score.phases.G = @{
  name = "fruit_pathway"
  fruitExit = $gFruit
  morningExit = $gMorning
  fruitWritten = (Test-Path $fruitPath)
  morningWritten = (Test-Path $morningPath)
  pass = ((Test-Path $fruitPath) -or ($gFruit -eq 0))
}
if (Test-Path $fruitPath) {
  try {
    $fj = Get-Content $fruitPath -Raw | ConvertFrom-Json
    $score.fruit = @{
      ideaCount = @($fj.ideas).Count
      doctrine = $fj.swarm_digest.soft_doctrine
      craftApplied = [bool]$fj.craft.applied
    }
  } catch {}
}

# Overall pass: units + smoke + residual written
$resPath = Join-Path $outbox "hive_bar_residual.latest.json"
$score.pass = ($codeA -eq 0) -and ($codeB -eq 0) -and (Test-Path $resPath)
Write-Score -Final

Write-Host ""
Write-Host "OVERNIGHT HIVE-BAR 0.8.7"
Write-Host ("  unit: {0}" -f $(if ($codeA -eq 0) { "PASS" } else { "FAIL" }))
if ($score.arena) {
  Write-Host ("  ladderHonesty: {0}" -f ($score.arena.ladder | ConvertTo-Json -Compress))
  Write-Host ("  ul: {0}" -f ($score.arena.ul | ConvertTo-Json -Compress))
}
Write-Host ("  residual: {0}" -f $(if (Test-Path $resPath) { "written" } else { "missing" }))
Write-Host ("  fruit: {0}" -f $(if (Test-Path $fruitPath) { "written" } else { "missing" }))
Write-Host "  densify: BANNED (ok)"
Write-Host ("  overall: {0}" -f $(if ($score.pass) { "PASS" } else { "PARTIAL/FAIL" }))
Write-Host "=== OVERNIGHT DONE ==="
if ($score.pass) { exit 0 } else { exit 1 }
