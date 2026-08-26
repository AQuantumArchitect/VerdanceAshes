param(
  [string]$Workspace = "",
  [int]$MaxSessionMinutes = 240,
  [int]$MaxMissions = 12,
  [switch]$SessionHost,
  [switch]$NoAutoRelaunch,
  [ValidateSet("visible", "headless-fastwin")]
  [string]$EngineMode = "visible",
  [string]$StatusPath = ""
)

# WO-057: Session host loops build -> launch -> extract/advance -> next until
# MaxMissions, BAR is closed mid-campaign, or AutoContinue is off.
# Mode A (same-map continue) keeps one BAR process alive across sorties; we
# re-arm extraction on every VA_RESULT so each chapter advances campaign state.
# Mode B (pkt-bar-mode-b-reload-travel): strategic_link hops → session host
# Reload path (resolve + rebuild + relaunch). Spring.Reload present (capability
# GO); external relaunch carries until startscript write is available.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $ScriptDir "_common.ps1")

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace
if (-not $StatusPath) { $StatusPath = Join-Path $Workspace "outbox\play_session.status.json" }

# Default: multi-mission host on unless explicitly disabled.
$autoRelaunch = $true
if ($NoAutoRelaunch) { $autoRelaunch = $false }
if ($SessionHost) { $autoRelaunch = $true }
if ($EngineMode -eq "headless-fastwin") { $autoRelaunch = $false; $MaxMissions = 1 }

$script:status = [ordered]@{
  schemaVersion = "verdance-play-session/1.2"
  phase = "starting"
  missionId = $null
  missionNumber = $null
  springPid = $null
  startedAt = (Get-Date).ToUniversalTime().ToString("o")
  updatedAt = $null
  resultStatus = $null
  nextMissionId = $null
  missionsCompleted = 0
  maxMissions = $MaxMissions
  sessionHost = [bool]$autoRelaunch
  modeB = [ordered]@{
    reloadCapability = $null
    lastAction = $null
    lastHop = $null
  }
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

function Get-ResultKeysFromText {
  param([string]$Text)
  $keys = @()
  if (-not $Text) { return $keys }
  # Compact JSON line embeds "resultKey":"..."
  $matches = [regex]::Matches($Text, '"resultKey"\s*:\s*"([^"]+)"')
  foreach ($m in $matches) { $keys += $m.Groups[1].Value }
  return $keys
}

function Update-ModeBCapabilityFromText {
  param([string]$Text)
  if (-not $Text) { return }
  # VA_CAPABILITY {io=...,reload=true,...}
  $m = [regex]::Match($Text, 'VA_CAPABILITY\s*\{([^}]+)\}')
  if (-not $m.Success) { return }
  $body = $m.Groups[1].Value
  $reload = $false
  if ($body -match 'reload\s*=\s*true') { $reload = $true }
  $script:status.modeB.reloadCapability = $reload
  if ($reload) {
    Write-Host "[mode-b] VA_CAPABILITY reload=true (Mode B session host path armed)"
  }
}

function Invoke-ModeBReloadPath {
  # Wire strategic_link edges into the session host Reload path before rebuild.
  # tools/mode_b_reload_travel.py validates next_sortie_choice against the atlas.
  $py = $null
  try { $py = Get-VerdancePython -Workspace $Workspace } catch { $py = $null }
  if (-not $py) {
    foreach ($c in @("C:\Python313\python.exe", "python", "py")) {
      $cmd = Get-Command $c -ErrorAction SilentlyContinue
      if ($cmd) { $py = $cmd.Source; break }
      if (Test-Path $c) { $py = $c; break }
    }
  }
  if (-not $py) {
    Write-Warning "Mode B: no Python; skipping strategic_link resolve"
    return $null
  }
  $tool = Join-Path $Workspace "tools\mode_b_reload_travel.py"
  if (!(Test-Path $tool)) {
    Write-Warning "Mode B: tools/mode_b_reload_travel.py missing"
    return $null
  }
  Write-SessionStatus "mode-b-travel" "Resolving Mode B strategic_link travel (session host Reload path)..."
  $raw = & $py $tool --workspace $Workspace --action resolve 2>&1 | Out-String
  $code = $LASTEXITCODE
  $modeBPath = Join-Path $Workspace "outbox\mode_b_travel.latest.json"
  $result = $null
  if (Test-Path $modeBPath) {
    try { $result = Get-Content $modeBPath -Raw | ConvertFrom-Json } catch { $result = $null }
  }
  if ($result) {
    $script:status.modeB.lastAction = [string]$result.action
    if ($result.selectedHop) {
      $script:status.modeB.lastHop = [ordered]@{
        from = [string]$result.selectedHop.fromZoneId
        to = [string]$result.selectedHop.targetZoneId
        mapId = [string]$result.selectedHop.mapId
      }
    }
    $msg = if ($result.sessionHost -and $result.sessionHost.message) {
      [string]$result.sessionHost.message
    } else {
      "Mode B action=$($result.action)"
    }
    Write-Host "[mode-b] $msg (rc=$code)"
  } else {
    Write-Host "[mode-b] resolve finished rc=$code (no stamp file)"
    if ($raw) { Write-Host $raw.Trim() }
  }
  return $result
}

try {
  Write-SessionStatus "preflight" "Session host=$autoRelaunch maxMissions=$MaxMissions. Checking for running BAR..."
  if (Get-RunningSpring) {
    throw "A spring/spring-headless process is already running. Close BAR (or run VERDANCE_PROCESS_HEALTH.bat -StopSpring) and retry."
  }

  $sessionDeadline = (Get-Date).AddMinutes($MaxSessionMinutes)
  $missionsDone = 0
  $seenResultKeys = @{}

  while ($missionsDone -lt $MaxMissions -and (Get-Date) -lt $sessionDeadline) {
    $intentPath = Join-Path $Workspace "outbox\next_mission_intent.json"
    if (!(Test-Path $intentPath)) {
      Write-SessionStatus "preflight" "No mission intent found; materializing from campaign state..."
      & (Join-Path $ScriptDir "advance_campaign_v1.ps1") -Workspace $Workspace -IntentOnly
    }
    $intent = Get-Content $intentPath -Raw | ConvertFrom-Json
    $script:status.missionId = $intent.missionId
    $script:status.missionNumber = $intent.missionNumber

    Write-SessionStatus "building" "Building mission $($intent.missionId) on $($intent.mapId) (slot $($missionsDone + 1)/$MaxMissions)..."
    $infologOffset = 0
    if (Test-Path $config.infolog) {
      $infologOffset = (Get-Item -LiteralPath $config.infolog).Length
    }

    if ($EngineMode -eq "headless-fastwin") {
      & (Join-Path $ScriptDir "build_next_mission_v1.ps1") -Workspace $Workspace
      Write-SessionStatus "in-game" "Running headless fast-win verification mission..."
      $playablePath = Join-Path $Workspace "data\scenarios\generated\next_mission_intent.playable.json"
      & (Join-Path $ScriptDir "install_playable_slice.ps1") -Workspace $Workspace `
        -ScenarioPath $playablePath -Headless -TimeoutSeconds 900 `
        -ExtraModOptions "va_headless_autostart=1,va_headless_fastwin=1,va_headless_quit=1"
      Write-SessionStatus "extracting" "Extracting headless result..."
      Invoke-FullCycle
      $missionsDone += 1
      $script:status.missionsCompleted = $missionsDone
      break
    }

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
    Write-SessionStatus "in-game" "BAR launched (pid $springPid). Play; Mode A continues stay in-seat. Results extract live."

    $missionDeadline = (Get-Date).AddMinutes([Math]::Min(90, $MaxSessionMinutes))
    $chaptersThisLaunch = 0
    while ((Get-Date) -lt $missionDeadline -and (Get-Date) -lt $sessionDeadline) {
      Start-Sleep -Seconds 3
      $newText = Read-NewInfologText ([ref]$infologOffset)
      Update-ModeBCapabilityFromText $newText

      # Mode A: multiple VA_RESULT lines per launch -- extract each unique resultKey.
      $newKeys = Get-ResultKeysFromText $newText
      foreach ($rk in $newKeys) {
        if ($seenResultKeys.ContainsKey($rk)) { continue }
        $seenResultKeys[$rk] = $true
        Write-SessionStatus "extracting" "Sortie result $rk -- advancing campaign..."
        try {
          Invoke-FullCycle
          # Mode B: if debrief pick was a strategic_link travel, stamp Reload path.
          Invoke-ModeBReloadPath | Out-Null
          $chaptersThisLaunch += 1
          $missionsDone += 1
          $script:status.missionsCompleted = $missionsDone
          $script:status.resultStatus = ($rk -split '\|')[-1]
          Write-SessionStatus "in-game" ("Mission advanced. Count so far: " + $missionsDone + ". Mode A same-map stays in-seat; Mode B travel exits for session host Reload.")
        } catch {
          Write-Warning "Extraction failed for $rk : $($_.Exception.Message)"
          $seenResultKeys.Remove($rk)
        }
      }

      # Protocol: never invent credit-bearing fake resultKeys. Marker without
      # parseable key → one harvest retry only (idempotent on real key).
      if ($newKeys.Count -eq 0 -and ($newText -match "VA_RESULT_JSON_END" -or $newText -match "VA_RESULT_JSON_COMPACT")) {
        $retryTag = "parse_retry_$chaptersThisLaunch"
        if (-not $seenResultKeys.ContainsKey($retryTag)) {
          try {
            Write-SessionStatus "extracting" "Result marker seen (no key parse); retry harvest only..."
            Invoke-FullCycle
            Invoke-ModeBReloadPath | Out-Null
            $seenResultKeys[$retryTag] = $true
            $chaptersThisLaunch += 1
            $missionsDone += 1
            $script:status.missionsCompleted = $missionsDone
            Write-SessionStatus "in-game" "Harvest retry done. Mode A stays in-seat; Mode B exits for Reload."
          } catch {
            Write-Warning "Harvest retry failed (no credit invented): $($_.Exception.Message)"
            $seenResultKeys[$retryTag] = $true
          }
        }
      }

      $proc = $null
      if ($script:status.springPid) {
        $proc = Get-Process -Id $script:status.springPid -ErrorAction SilentlyContinue
      }
      if (-not $proc) { $proc = Get-RunningSpring }
      if (-not $proc) { break }
    }

    # BAR exited.
    $script:status.springPid = $null
    if ($chaptersThisLaunch -eq 0) {
      Write-SessionStatus "extracting" "Game exited with no live extract; trying infolog harvest..."
      try {
        Invoke-FullCycle
        Invoke-ModeBReloadPath | Out-Null
        $missionsDone += 1
        $script:status.missionsCompleted = $missionsDone
      } catch {
        Write-SessionStatus "no-result" "No mission result found. Same mission still installed - run Play Session again. ($($_.Exception.Message))"
        if (-not $autoRelaunch) { return }
        # Don't infinite-loop on hard failures: stop session host.
        break
      }
    } else {
      # Final Mode B resolve after exit (travel pick may arrive late).
      Invoke-ModeBReloadPath | Out-Null
    }

    # Build next seed for relaunch / next sit-down (Mode B stamps choice first).
    $modeBMsg = if ($script:status.modeB.lastAction -eq "stamp_reload_travel" -and $script:status.modeB.lastHop) {
      "Mode B Reload travel → map $($script:status.modeB.lastHop.mapId) ($($script:status.modeB.lastHop.from)→$($script:status.modeB.lastHop.to)). Building..."
    } else {
      "Building the next mission seed..."
    }
    Write-SessionStatus "build-next" $modeBMsg
    Backup-CampaignState
    & (Join-Path $ScriptDir "build_next_mission_v1.ps1") -Workspace $Workspace

    $manifestPath = Join-Path $Workspace "outbox\next_mission_build_manifest.json"
    if (Test-Path $manifestPath) {
      try {
        $manifest = Get-Content $manifestPath -Raw | ConvertFrom-Json
        $script:status.nextMissionId = $manifest.missionId
      } catch { }
    }

    if (-not $autoRelaunch) {
      Write-SessionStatus "next-ready" "Mission $($script:status.nextMissionId) is built. Run Play Session to continue."
      try { [System.Media.SystemSounds]::Asterisk.Play() } catch { }
      break
    }

    if ($missionsDone -ge $MaxMissions) {
      Write-SessionStatus "session-complete" "Hit MaxMissions=$MaxMissions. Next seed ready: $($script:status.nextMissionId)."
      try { [System.Media.SystemSounds]::Asterisk.Play() } catch { }
      break
    }

    # Mode B / Mode C map travel: auto-relaunch next mission without another click.
    # Mode B uses strategic_link-stamped choice; Mode C is generic external relaunch.
    $relaunchLabel = if ($script:status.modeB.lastAction -eq "stamp_reload_travel") {
      "Mode B Reload path"
    } else {
      "session host"
    }
    Write-SessionStatus "relaunch" "Auto-relaunching next mission $($script:status.nextMissionId) in 3s ($relaunchLabel). Close this window to stop."
    Start-Sleep -Seconds 3
    if (Get-RunningSpring) {
      Write-SessionStatus "waiting" "BAR still running - waiting for exit before relaunch..."
      while (Get-RunningSpring) { Start-Sleep -Seconds 2 }
    }
  }

  if ($script:status.phase -ne "session-complete" -and $script:status.phase -ne "next-ready" -and $script:status.phase -ne "no-result") {
    Write-SessionStatus "session-complete" "Session finished. Missions advanced: $missionsDone. Next: $($script:status.nextMissionId)."
    try { [System.Media.SystemSounds]::Asterisk.Play() } catch { }
  }
} catch {
  $script:status.error = $_.Exception.Message
  Write-SessionStatus "error" $_.Exception.Message
  throw
}
