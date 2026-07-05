param(
  [string]$Workspace = "",
  [int]$MaxSessionMinutes = 120,
  [ValidateSet("visible", "headless-fastwin")]
  [string]$EngineMode = "visible",
  [string]$StatusPath = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "_common.ps1")

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace
if (-not $StatusPath) { $StatusPath = Join-Path $Workspace "outbox\play_session.status.json" }

$script:status = [ordered]@{
  schemaVersion = "verdance-play-session/1.0"
  phase = "starting"
  missionId = $null
  missionNumber = $null
  springPid = $null
  startedAt = (Get-Date).ToUniversalTime().ToString("o")
  updatedAt = $null
  resultStatus = $null
  nextMissionId = $null
  error = $null
  message = $null
}

function Write-SessionStatus {
  param([string]$Phase, [string]$Message = $null)
  if ($Phase) { $script:status.phase = $Phase }
  if ($null -ne $Message) { $script:status.message = $Message }
  $script:status.updatedAt = (Get-Date).ToUniversalTime().ToString("o")
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $StatusPath) | Out-Null
  $script:status | ConvertTo-Json | Set-Content -Encoding UTF8 -Path $StatusPath
  Write-Host "[$($script:status.phase)] $($script:status.message)"
}

function Get-RunningSpring {
  Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^spring(-headless)?$' }
}

function Invoke-FullCycle {
  & (Join-Path $ScriptDir "run_full_cycle_v1.ps1") -Workspace $Workspace -WriteState
}

function Backup-CampaignState {
  $statePath = $config.campaignState
  if (!(Test-Path $statePath)) { return }
  $backupDir = Join-Path $Workspace "state\backups"
  New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
  $missionTag = if ($script:status.missionId) { $script:status.missionId } else { "unknown" }
  $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
  Copy-Item -Force $statePath (Join-Path $backupDir "campaign_state.$missionTag.$stamp.json")
  Get-ChildItem $backupDir -Filter "campaign_state.*.json" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip 20 |
    Remove-Item -Force -ErrorAction SilentlyContinue
}

function Read-NewInfologText {
  param([ref]$Offset)
  if (!(Test-Path $config.infolog)) { return "" }
  $stream = $null
  try {
    $stream = [System.IO.FileStream]::new(
      $config.infolog,
      [System.IO.FileMode]::Open,
      [System.IO.FileAccess]::Read,
      ([System.IO.FileShare]::ReadWrite -bor [System.IO.FileShare]::Delete))
    if ($stream.Length -lt $Offset.Value) {
      # Spring truncates/rewrites infolog on start: reset to the beginning.
      $Offset.Value = 0
    }
    if ($stream.Length -eq $Offset.Value) { return "" }
    [void]$stream.Seek($Offset.Value, [System.IO.SeekOrigin]::Begin)
    $reader = [System.IO.StreamReader]::new($stream)
    $text = $reader.ReadToEnd()
    $Offset.Value = $stream.Length
    return $text
  } catch {
    return ""
  } finally {
    if ($stream) { $stream.Dispose() }
  }
}

try {
  # ---- preflight -------------------------------------------------------
  Write-SessionStatus "preflight" "Checking for running BAR processes..."
  if (Get-RunningSpring) {
    throw "A spring/spring-headless process is already running. Close BAR (or run VERDANCE_PROCESS_HEALTH.bat -StopSpring) and retry."
  }
  $intentPath = Join-Path $Workspace "outbox\next_mission_intent.json"
  if (!(Test-Path $intentPath)) {
    Write-SessionStatus "preflight" "No mission intent found; materializing from campaign state..."
    & (Join-Path $ScriptDir "advance_campaign_v1.ps1") -Workspace $Workspace -IntentOnly
  }
  $intent = Get-Content $intentPath -Raw | ConvertFrom-Json
  $script:status.missionId = $intent.missionId
  $script:status.missionNumber = $intent.missionNumber

  # ---- build + launch --------------------------------------------------
  Write-SessionStatus "building" "Building mission $($intent.missionId) on $($intent.mapId)..."
  $infologOffset = 0
  if (Test-Path $config.infolog) {
    $infologOffset = (Get-Item -LiteralPath $config.infolog).Length
  }

  if ($EngineMode -eq "headless-fastwin") {
    # Verification mode: build, then run the mission headlessly to a fast win.
    & (Join-Path $ScriptDir "build_next_mission_v1.ps1") -Workspace $Workspace
    Write-SessionStatus "in-game" "Running headless fast-win verification mission..."
    $playablePath = Join-Path $Workspace "data\scenarios\generated\next_mission_intent.playable.json"
    & (Join-Path $ScriptDir "install_playable_slice.ps1") -Workspace $Workspace `
      -ScenarioPath $playablePath -Headless -TimeoutSeconds 900 `
      -ExtraModOptions "va_headless_autostart=1,va_headless_fastwin=1,va_headless_quit=1"
  } else {
    & (Join-Path $ScriptDir "build_next_mission_v1.ps1") -Workspace $Workspace -Launch
    $launchManifestPath = Join-Path $Workspace "playable_runs\latest_launch.json"
    $springPid = $null
    if (Test-Path $launchManifestPath) {
      try {
        $launch = Get-Content $launchManifestPath -Raw | ConvertFrom-Json
        $springPid = $launch.pid
      } catch { }
    }
    $script:status.springPid = $springPid
    Write-SessionStatus "in-game" "BAR launched (pid $springPid). Play the mission; results are picked up automatically."

    # ---- watcher -------------------------------------------------------
    $deadline = (Get-Date).AddMinutes($MaxSessionMinutes)
    $resultSeen = $false
    $extracted = $false
    while ((Get-Date) -lt $deadline) {
      Start-Sleep -Seconds 3
      $newText = Read-NewInfologText ([ref]$infologOffset)
      if (-not $resultSeen -and ($newText -match "VA_RESULT_JSON_END" -or $newText -match "VA_RESULT_JSON_COMPACT")) {
        $resultSeen = $true
        Write-SessionStatus "extracting" "Mission result detected; extracting and advancing campaign..."
        try {
          Invoke-FullCycle
          $extracted = $true
          Write-SessionStatus "in-game" "Campaign advanced. Finish/exit the game when ready."
        } catch {
          Write-Warning "Mid-game extraction failed (will retry on exit): $($_.Exception.Message)"
          $resultSeen = $false
        }
      }
      $proc = $null
      if ($script:status.springPid) {
        $proc = Get-Process -Id $script:status.springPid -ErrorAction SilentlyContinue
      }
      if (-not $proc) { $proc = Get-RunningSpring }
      if (-not $proc) { break }
    }

    if (-not $extracted) {
      Write-SessionStatus "extracting" "Game exited; extracting result from infolog..."
      try {
        Invoke-FullCycle
        $extracted = $true
      } catch {
        Write-SessionStatus "no-result" "No mission result found. The same mission is still installed - run Play Session again to retry. ($($_.Exception.Message))"
        return
      }
    }
  }

  if ($EngineMode -eq "headless-fastwin") {
    Write-SessionStatus "extracting" "Extracting headless result..."
    Invoke-FullCycle
  }

  # ---- advance + build next -------------------------------------------
  $reportPath = Join-Path $Workspace "outbox\advance_report.v1.json"
  if (Test-Path $reportPath) {
    try {
      $report = Get-Content $reportPath -Raw | ConvertFrom-Json
      $script:status.resultStatus = ($report.resultKey -split '\|')[-1]
    } catch { }
  }

  Write-SessionStatus "build-next" "Building the next mission..."
  Backup-CampaignState
  & (Join-Path $ScriptDir "build_next_mission_v1.ps1") -Workspace $Workspace

  $manifestPath = Join-Path $Workspace "outbox\next_mission_build_manifest.json"
  if (Test-Path $manifestPath) {
    try {
      $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
      $script:status.nextMissionId = $manifest.missionId
    } catch { }
  }

  Write-SessionStatus "next-ready" "Mission $($script:status.nextMissionId) is built and ready. Run Play Session to continue the campaign."
  try { [System.Media.SystemSounds]::Asterisk.Play() } catch { }
} catch {
  $script:status.error = $_.Exception.Message
  Write-SessionStatus "error" $_.Exception.Message
  throw
}
