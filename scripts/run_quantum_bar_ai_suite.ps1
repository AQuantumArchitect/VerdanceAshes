param(
  [string]$Workspace = "",
  [switch]$NoLlm,
  [int]$Missions = 5,
  [int]$LlmEvery = 4,
  [int]$Seed = 7
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

$py = "C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe"
if (!(Test-Path $py)) {
  $py = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source)
}
if (-not $py) { throw "Python not found (expected umwelt .venv or python on PATH)" }

$umweltSrc = "C:\Users\Luke Spooner\ws-win\umwelt\src"
$tools = Join-Path $Workspace "tools"
$env:PYTHONPATH = "$tools;$umweltSrc"
# Load yurt.env into process for GROK_* if present
$yurtEnv = "C:\Users\Luke Spooner\ws-win\yurt\config\yurt.env"
if (Test-Path $yurtEnv) {
  Get-Content $yurtEnv | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#") -or ($line -notmatch "=")) { return }
    $k, $v = $line.Split("=", 2)
    $k = $k.Trim(); $v = $v.Trim().Trim('"').Trim("'")
    if ($k -match '^(GROK_|XAI_|UMWELT)') {
      Set-Item -Path "Env:$k" -Value $v
    }
  }
}

$argsList = @(
  "-m", "quantum_bar_ai.suite",
  "--missions", "$Missions",
  "--llm-every", "$LlmEvery",
  "--seed", "$Seed"
)
if ($NoLlm) { $argsList += "--no-llm" }

Write-Host "quantum-BAR-AI suite via $py"
Write-Host "PYTHONPATH=$env:PYTHONPATH"
Set-Location $Workspace
& $py @argsList
if ($LASTEXITCODE -ne 0) { throw "suite exited $LASTEXITCODE" }

$latest = Join-Path $Workspace "outbox\quantum_bar_ai_suite.latest.json"
if (Test-Path $latest) {
  Write-Host "Latest summary: $latest"
}
