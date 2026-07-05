param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [string]$ScenarioPath = "",
  [string[]]$Variants = @("simple_defenders", "barbarian_hard", "barbarian_aggressive"),
  [switch]$SaveGame,
  [int]$TimeoutSeconds = 240,
  [string]$SavePrefix = "verdance_ats_matrix"
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

if (-not $ScenarioPath) {
  $ScenarioPath = Join-Path $Workspace "data\scenarios\all_that_simmers.playable.json"
}
if (!(Test-Path $ScenarioPath)) { throw "Scenario file not found: $ScenarioPath" }

$runRoot = Join-Path $Workspace "playable_runs"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$matrixDir = Join-Path $runRoot "matrix_$stamp"
New-Item -ItemType Directory -Force -Path $matrixDir | Out-Null

$installer = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "install_playable_slice.ps1"
$results = @()

foreach ($variant in $Variants) {
  $safeVariant = $variant -replace '[^A-Za-z0-9_-]', '_'
  $saveName = "$SavePrefix`_$safeVariant`_$stamp"
  $logPath = Join-Path $matrixDir "$safeVariant.log.txt"
  $args = @(
    "-ExecutionPolicy", "Bypass",
    "-File", $installer,
    "-Workspace", $Workspace,
    "-ScenarioPath", $ScenarioPath,
    "-Variant", $variant,
    "-TimeoutSeconds", ([string]$TimeoutSeconds)
  )
  if ($SaveGame) {
    $args += @("-SaveGame", "-SaveName", $saveName)
  } else {
    $args += "-Headless"
  }

  Write-Host "Running playable variant: $variant"
  $output = & powershell @args 2>&1
  $output | Set-Content -Encoding UTF8 -Path $logPath

  $exit = if ($LASTEXITCODE -ne $null) { [int]$LASTEXITCODE } else { 0 }
  $results += [ordered]@{
    variant = $variant
    saveName = if ($SaveGame) { $saveName } else { $null }
    logPath = $logPath
    exitCode = $exit
    succeeded = ($exit -eq 0)
  }
  if ($exit -ne 0) {
    throw "Variant '$variant' failed with exit code $exit. See $logPath"
  }
}

$manifest = [ordered]@{
  schemaVersion = "verdance-playable-variant-matrix/0.1"
  generatedAt = (Get-Date).ToString("s")
  scenarioPath = $ScenarioPath
  matrixDir = $matrixDir
  saveGame = [bool]$SaveGame
  timeoutSeconds = $TimeoutSeconds
  results = $results
}
$manifestPath = Join-Path $matrixDir "manifest.json"
$manifest | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 -Path $manifestPath
Write-Host "Playable variant matrix complete: $manifestPath"
