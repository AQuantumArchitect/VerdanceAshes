param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [string]$TranscriptPath = "",
  [string]$MilestoneMinutes = "1,2,3,5,8,13,21",
  [string]$ExtensionMilestoneMinutes = "34,55,89"
)

$ErrorActionPreference = "Continue"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runner = Join-Path $scriptDir "run_campaign_ai_baseline_suite.ps1"
$logDir = Join-Path $Workspace "reports\map_surveys"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (-not $TranscriptPath) {
  $TranscriptPath = Join-Path $logDir ("campaign_ai_transcript_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
}

$statePath = Join-Path $logDir "campaign_ai_overnight_state.json"
$state = [ordered]@{
  startedAt = (Get-Date).ToString("s")
  workspace = $Workspace
  transcriptPath = $TranscriptPath
  phase = "starting"
  pid = $PID
}
$state | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path $statePath

Set-Location $Workspace

try {
  try {
    Start-Transcript -Path $TranscriptPath -Force | Out-Null
  } catch {
    Write-Warning "Transcript start failed: $($_.Exception.Message)"
  }
  $state.phase = "running"
  $state | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path $statePath
  & $runner `
    -Workspace $Workspace `
    -GenerateMatrix `
    -VariantMode baseline `
    -MilestoneMinutes $MilestoneMinutes `
    -ExtensionMilestoneMinutes $ExtensionMilestoneMinutes `
    -TimeoutSecondsPerRun 43200 `
    -SkipPatchInstall `
    -Resume
  $exitCode = $LASTEXITCODE
  if ($exitCode -ne 0) {
    throw "Campaign AI suite exited with code $exitCode"
  }
  $state.phase = "finished"
  $state.exitCode = $exitCode
} finally {
  try {
    Stop-Transcript | Out-Null
  } catch {
    Write-Warning "Transcript stop failed: $($_.Exception.Message)"
  }
  if (-not $state.exitCode) {
    $state.phase = "failed"
    $state.error = $Error[0].Exception.Message
  }
  $state.completedAt = (Get-Date).ToString("s")
  $state | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 -Path $statePath
}
