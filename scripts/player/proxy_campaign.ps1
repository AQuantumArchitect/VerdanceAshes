# Proxy-player campaign overnight harness (no BAR, no human).
# quantum-BAR-AI LocalToolAgent vs SimpleAI and/or BARbarIAn (abstract sim).
param(
  [string]$Workspace = "",
  [int]$Sorties = 6,
  [int]$Seeds = 2,
  [int]$Seed = 11,
  [string]$Enemy = "both",  # simple | barbarian | both
  [double]$Difficulty = 1.2,
  [int]$Ticks = 48,
  [switch]$SelfTest,
  [switch]$VerboseRun
)

$ErrorActionPreference = "Stop"
$PlayerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsDir = Split-Path -Parent $PlayerDir
. (Join-Path $ScriptsDir "_common.ps1")

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
Write-Host "=== Verdance PROXY CAMPAIGN ==="
Write-Host "Workspace: $Workspace"

$py = Get-VerdancePython -Workspace $Workspace
# Prefer umwelt venv when present (has umwelt package path)
$umweltPy = "C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe"
if (Test-Path $umweltPy) { $py = $umweltPy }

$umweltSrc = "C:\Users\Luke Spooner\ws-win\umwelt\src"
$tools = Join-Path $Workspace "tools"
$env:PYTHONPATH = "$tools;$umweltSrc"
$env:QBAI_NO_LLM = "1"

Write-Host "Python: $py"
Write-Host "PYTHONPATH: $env:PYTHONPATH"

$prev = Get-Location
Set-Location $Workspace
$prevEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
  $args = @(
    (Join-Path $tools "proxy_campaign_v1.py"),
    "--workspace", $Workspace,
    "--sorties", "$Sorties",
    "--seeds", "$Seeds",
    "--seed", "$Seed",
    "--enemy", $Enemy,
    "--difficulty", "$Difficulty",
    "--ticks", "$Ticks",
    "--write"
  )
  if ($SelfTest) {
    $args = @((Join-Path $tools "proxy_campaign_v1.py"), "--workspace", $Workspace, "--self-test")
  }
  if ($VerboseRun -and -not $SelfTest) { $args += "--verbose" }

  Write-Host ("Running: {0} {1}" -f $py, ($args -join " "))
  & $py @args 2>&1 | ForEach-Object { "$_" }
  $code = $LASTEXITCODE
  if ($null -eq $code) { $code = 0 }
} finally {
  $ErrorActionPreference = $prevEap
  Set-Location $prev
}

if ($code -ne 0) {
  Write-Host "PROXY CAMPAIGN FAILED exit=$code"
  exit $code
}

$latest = Join-Path $Workspace "outbox\proxy_campaign.latest.json"
if (Test-Path $latest) {
  Write-Host "Latest: $latest"
}
Write-Host "=== PROXY CAMPAIGN PASS ==="
exit 0
