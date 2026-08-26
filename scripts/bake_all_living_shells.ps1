param(
  [string]$Workspace = "",
  [switch]$PlaceholderOnly,
  [switch]$SkipEngine,
  [switch]$Headed,
  [string[]]$Maps = @(),
  [int]$TimeoutSeconds = 0,
  [int]$GrowFrames = 0
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $Maps -or $Maps.Count -eq 0) {
  $Maps = @(
    "the_rock_jungle",   # shortest first (smoke)
    "eye_of_horus",
    "koom_valley",
    "all_that_simmers",
    "tabula",
    "greenest_fields",
    "ancient_bastion"    # longest grow last
  )
}

$results = @()
foreach ($m in $Maps) {
  Write-Host ""
  Write-Host "======== BAKE $m ========"
  $args = @("-ExecutionPolicy", "Bypass", "-File", (Join-Path $ScriptDir "bake_living_shell.ps1"),
            "-Workspace", $Workspace, "-MapId", $m)
  if ($PlaceholderOnly) { $args += "-PlaceholderOnly" }
  if ($SkipEngine) { $args += "-SkipEngine" }
  if ($Headed) { $args += "-Headed" }
  if ($TimeoutSeconds -gt 0) { $args += @("-TimeoutSeconds", "$TimeoutSeconds") }
  if ($GrowFrames -gt 0) { $args += @("-GrowFrames", "$GrowFrames") }
  try {
    & powershell @args
    $results += [ordered]@{ mapId = $m; ok = $true }
  } catch {
    Write-Warning "Bake failed for ${m}: $($_.Exception.Message)"
    $results += [ordered]@{ mapId = $m; ok = $false; error = $_.Exception.Message }
  }
}

# Refresh shell character membrane pack for campaign craft.
$py = $null
$candidates = @(
  "C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe",
  "python"
)
foreach ($c in $candidates) {
  if ($c -eq "python") { $py = "python"; break }
  if (Test-Path $c) { $py = $c; break }
}
if ($py) {
  $env:PYTHONPATH = "$(Join-Path $Workspace 'tools');$env:PYTHONPATH"
  try {
    & $py -m quantum_bar_ai.shell_character_membrane $Workspace
  } catch {
    Write-Warning "Membrane refresh skipped: $($_.Exception.Message)"
  }
}

$summaryPath = Join-Path $Workspace "outbox\shell_bake_all.latest.json"
$summary = [ordered]@{
  generatedAt = (Get-Date).ToString("s")
  placeholderOnly = [bool]$PlaceholderOnly
  skipEngine = [bool]$SkipEngine
  headed = [bool]$Headed
  computeLocus = if ($Headed) { "local_headed_gpu" } elseif ($PlaceholderOnly -or $SkipEngine) { "placeholder" } else { "local_headless" }
  results = $results
}
($summary | ConvertTo-Json -Depth 5) | Set-Content -Encoding UTF8 -LiteralPath $summaryPath
Write-Host ""
Write-Host "Bake-all summary: $summaryPath"
$results | ForEach-Object { Write-Host ("  {0}: {1}" -f $_.mapId, $(if ($_.ok) { "ok" } else { "FAIL" })) }
