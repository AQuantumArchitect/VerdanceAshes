<#
.SYNOPSIS
  Play one campaign mission in BAR with the session recorded, then file the record
  and advance the campaign.

.DESCRIPTION
  The overnight AI matrix measured, per run, where units went (zone-to-zone
  crossings), what each zone was worth over time, and how the mission ended. A
  human session emitted none of that: the sampler and both export markers sat
  behind a profiling predicate that also disables the HUD, runs the sim at 20x and
  grants an instant win, so there was no setting under which a person could play a
  measured mission.

  This runs the real playable path -- full UI, normal speed, waves and beats on,
  real win/loss -- with tracking armed alongside it, then harvests the infolog into
  the same shape the AI runs produced, so the two are directly comparable.

  Safe to interrupt. Alt-F4 mid-mission still leaves a usable flow record; only the
  outcome is lost, and the harvest says so rather than inventing one.

  ASCII only in this file (PowerShell 5.1 parses BOM-less UTF-8 as ANSI).
#>
param(
  [string]$Workspace = "",
  # The campaign only moves if the result is written back. -NoAdvance plays the same
  # mission again next time, which is what you want while tuning one encounter.
  [switch]$NoAdvance,
  # Wall-clock ceiling on waiting for BAR to exit. Only bounds the wait, never the
  # session: if it trips, the record is harvested from however far the log got.
  [int]$TimeoutMinutes = 240,
  [switch]$SkipModInstall,
  # Opt in to repairing springsettings.cfg in place (a backup is written first).
  # Off by default: this file is the player's own BAR config, not ours to rewrite
  # without being asked. Without it a poisoned config is reported and refused.
  [switch]$RepairConfig
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $scriptDir "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$startedAt = Get-Date

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "  == $Message" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "  ============================================================"
Write-Host "   VERDANCE'S ASHES  -  TRACKED PLAYTEST"
Write-Host "  ============================================================"
Write-Host "   Workspace: $Workspace"
Write-Host ""

# ---- 1. nothing already running ------------------------------------------------
$running = @(Get-Process -Name "spring", "spring-headless" -ErrorAction SilentlyContinue)
if ($running.Count -gt 0) {
  throw ("BAR is already running (pid $($running[0].Id)). Close it first: this session " +
         "would share one infolog with it and the record would interleave.")
}

# ---- 1b. springsettings not poisoned by a profiling run ------------------------
# Spring.SetConfigInt writes THROUGH to springsettings.cfg unless its third
# argument (useOverlay) is true. The headless probe gadgets set LuaUI=0 and
# UnitIconDist=99999 to dodge an icon-atlas stall, and every one of those writes
# used to persist -- so a survey batch would silently disable LuaUI for every
# later GUI session. LuaUI=0 means no widgets at all: no HUD, no recorder, and
# nothing in game to say why. Fixed at source, but an already-poisoned config
# stays poisoned until someone edits the file, so check before spending a session.
Write-Step "Checking BAR config"
$barCfg = Join-Path (Get-VerdanceConfig -Workspace $Workspace).barDataRoot "springsettings.cfg"
if (Test-Path -LiteralPath $barCfg) {
  $cfgLines = @(Get-Content -LiteralPath $barCfg)
  $badLuaUi = @($cfgLines | Where-Object { $_ -match '^\s*LuaUI\s*=\s*0\s*$' }).Count -gt 0
  $badIcons = @($cfgLines | Where-Object { $_ -match '^\s*UnitIconDist\s*=\s*99999\s*$' }).Count -gt 0
  if ($badLuaUi -or $badIcons) {
    if ($RepairConfig) {
      $cfgBackup = "$barCfg.verdance_{0}.bak" -f (Get-Date -Format "yyyyMMdd_HHmmss")
      Copy-Item -LiteralPath $barCfg -Destination $cfgBackup
      $fixed = foreach ($l in $cfgLines) {
        if ($l -match '^\s*LuaUI\s*=\s*0\s*$') { continue }
        elseif ($l -match '^\s*UnitIconDist\s*=\s*99999\s*$') { "UnitIconDist = 160" }
        else { $l }
      }
      Set-Content -LiteralPath $barCfg -Value $fixed -Encoding ascii
      Write-Host "     Repaired. Backup: $cfgBackup"
    } else {
      # Warn, do not block. Measured against the engine's own <User Config> dump
      # in infolog.txt: UnitIconDist IS an enumerated engine variable and 99999
      # really does push unit icons out of range, which is a genuine handicap in
      # an RTS but not a broken session. "LuaUI" is NOT enumerated by the engine
      # at all -- it is an unrecognised key that nothing reads, so LuaUI = 0 is
      # inert. An earlier version of this guard hard-threw on both and refused to
      # start over a setting with no effect.
      if ($badLuaUi) {
        Write-Host "     Note: an inert 'LuaUI = 0' is in springsettings.cfg."
        Write-Host "     The engine does not read that key; -RepairConfig tidies it."
      }
      if ($badIcons) {
        Write-Warning ("UnitIconDist = 99999 is set in $barCfg -- a past headless run " +
                       "left it there, and it pushes unit icons out of range for the " +
                       "whole session. Re-run with -RepairConfig to restore 160 (a " +
                       "backup is written first). Continuing.")
      }
    }
  } else {
    Write-Host "     Clean."
  }
} else {
  Write-Warning "No springsettings.cfg at $barCfg; skipping the check."
}

# ---- 2. quarantine any stale result --------------------------------------------
# advance_campaign has no freshness check: it reads inbox\latest_va_result.json and
# applies whatever mission number it finds. The overnight AI probes leave results
# from mission 1100 in there, which would jump the campaign to 1101.
Write-Step "Clearing stale results"
$inboxResult = Join-Path $Workspace "inbox\latest_va_result.json"
if (Test-Path -LiteralPath $inboxResult) {
  $quarantine = Join-Path $Workspace "inbox\quarantine"
  New-Item -ItemType Directory -Force -Path $quarantine | Out-Null
  $moved = Join-Path $quarantine ("latest_va_result_{0}.json" -f (Get-Date -Format "yyyyMMdd_HHmmss"))
  Move-Item -LiteralPath $inboxResult -Destination $moved
  Write-Host "     Moved a pre-existing result aside: $moved"
} else {
  Write-Host "     None present."
}

# ---- 3. mod install ------------------------------------------------------------
# A prior hub "Drop into battle" replaces the junction with a full copy, at which
# point gadget edits stop reaching BAR and the session silently runs old code.
if (-not $SkipModInstall) {
  Write-Step "Installing mod"
  & (Join-Path $scriptDir "install_mod_archive.ps1") -Workspace $Workspace | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Mod install failed ($LASTEXITCODE)." }
}

# ---- 4. mission intent ---------------------------------------------------------
Write-Step "Resolving next mission"
$intentPath = Join-Path $Workspace "outbox\next_mission_intent.json"
if (!(Test-Path -LiteralPath $intentPath)) {
  & (Join-Path $scriptDir "advance_campaign_v1.ps1") -Workspace $Workspace -IntentOnly | Out-Host
}
if (!(Test-Path -LiteralPath $intentPath)) { throw "No mission intent at $intentPath." }
$intent = Get-Content -Raw -LiteralPath $intentPath | ConvertFrom-Json
$mapId = [string]$intent.mapId
$missionId = [string]$intent.missionId
Write-Host "     Mission: $missionId   Map: $mapId"

# ---- 5. build and launch, tracked ----------------------------------------------
# va_play_track arms the dense sampler (orders by class, economy, army centroid) and
# the zone-flow sampler. It deliberately does NOT touch the profiling predicate --
# doing so would disable the HUD and make the session unplayable.
Write-Step "Building and launching"
# 450 frames = 15s between recorded snapshots. The gadget's own default is 150 (5s),
# which over a 30-minute mission is 360 full occupancy packets -- a multi-megabyte
# record rewritten every few seconds for no extra insight. The zone-flow SAMPLER is
# separately pinned at 150 inside the gadget, because crossing counts depend on
# observation rate and have to match the AI matrix; only the export cadence changes.
$trackOptions = "va_play_track=1;va_dev_sample_period=450"
& (Join-Path $scriptDir "build_next_mission_v1.ps1") `
  -Workspace $Workspace -Launch -ExtraModOptions $trackOptions | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Mission build/launch failed ($LASTEXITCODE)." }

# ---- 6. assert the modoption actually reached the startscript ------------------
# Silent failure mode: a passthrough that gets dropped produces a perfectly normal
# session that measures nothing, and you only find out after playing it.
$startScript = Join-Path $Workspace ("playable_runs\verdance_playable_{0}_alpha_player.txt" -f $mapId)
if (Test-Path -LiteralPath $startScript) {
  $ss = Get-Content -Raw -LiteralPath $startScript
  if ($ss -notmatch 'va_play_track\s*=') {
    throw ("va_play_track never reached [MODOPTIONS] in $startScript. " +
           "This session would not be tracked; aborting before you spend time on it.")
  }
  Write-Host "     Verified va_play_track in the startscript."
} else {
  Write-Warning "Could not find $startScript to verify tracking. Continuing."
}

# ---- 7. launch manifest --------------------------------------------------------
$launchPath = Join-Path $Workspace "playable_runs\latest_launch.json"
if (!(Test-Path -LiteralPath $launchPath)) { throw "No launch manifest at $launchPath." }
$launch = Get-Content -Raw -LiteralPath $launchPath | ConvertFrom-Json
$barPid = [int]$launch.pid
$baseline = [long]$launch.infologBaselineLength
Write-Host "     BAR pid $barPid, infolog baseline $baseline bytes."

# ---- 8. wait for the session to end --------------------------------------------
Write-Step "Playing"
Write-Host "     Waiting for BAR to exit. Play the mission; this window stays open."
Write-Host "     To end a mission cleanly without finishing it, type in chat:"
Write-Host "        /luarules vawin     /luarules vafail     /luarules vapartial"
Write-Host ""
$deadline = (Get-Date).AddMinutes($TimeoutMinutes)
$timedOut = $false
while ($true) {
  $proc = Get-Process -Id $barPid -ErrorAction SilentlyContinue
  if (-not $proc) { break }
  if ((Get-Date) -gt $deadline) { $timedOut = $true; break }
  Start-Sleep -Seconds 5
}
if ($timedOut) {
  Write-Warning "Still running after $TimeoutMinutes minute(s). Harvesting what exists so far."
} else {
  Write-Host "     BAR exited."
}
$elapsed = [int]((Get-Date) - $startedAt).TotalSeconds

# ---- 9. harvest ----------------------------------------------------------------
# Two paths to the same record. The recorder widget writes the session from inside
# the client while it is still running, which is the one that survives a crash and
# needs nothing from this script. The infolog harvest is the fallback for when the
# widget did not load (a stale mod copy, widgets disabled) -- it reads the same
# packets back out of the log after the fact.
Write-Step "Harvesting the session"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = Join-Path (Join-Path $Workspace "human_runs") "session_$stamp"
$py = Get-VerdancePython $Workspace
$clientOk = $false
try {
  & $py (Join-Path $Workspace "tools\collect_client_sessions_v1.py") `
    --workspace $Workspace --no-analyse | Out-Host
  $clientOk = ($LASTEXITCODE -eq 0)
} catch {
  Write-Warning "In-client session collection failed: $_"
}

if ($clientOk) {
  Write-Host "     Recorded in-client by the recorder widget."
} else {
  Write-Host "     No in-client record found; falling back to the infolog harvest."
  & (Join-Path $scriptDir "harvest_human_run_v1.ps1") `
    -Workspace $Workspace -RunDir $runDir -MapId $mapId `
    -MapTitle ([string]$intent.mapTitle) -ElapsedSeconds $elapsed `
    -BaselineLength $baseline | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Harvest failed ($LASTEXITCODE)." }
}

# Spring writes a replay of every match. It is the only full-fidelity record of what
# the player actually did, and the next session does not overwrite it, so keep a
# pointer to the one that belongs to this run.
try {
  $config = Get-VerdanceConfig -Workspace $Workspace
  $demoDir = Join-Path $config.barDataRoot "demos"
  if (Test-Path -LiteralPath $demoDir) {
    $demo = Get-ChildItem -LiteralPath $demoDir -Filter "*.sdfz" |
      Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($demo -and $demo.LastWriteTime -ge $startedAt) {
      Copy-Item -LiteralPath $demo.FullName -Destination (Join-Path $runDir $demo.Name)
      Write-Host "     Replay: $($demo.Name)"
    }
  }
} catch {
  Write-Warning "Could not copy the replay: $_"
}

# ---- 10. advance the campaign ---------------------------------------------------
if ($NoAdvance) {
  Write-Step "Not advancing (-NoAdvance): the same mission will come up again."
} else {
  Write-Step "Advancing the campaign"
  # Snapshot first. This is the one step that mutates campaign state, and a bad
  # result should be undoable without unpicking it by hand.
  $statePath = Join-Path $Workspace "state\campaign_state.json"
  if (Test-Path -LiteralPath $statePath) {
    $backupDir = Join-Path $Workspace "state\backups"
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    $backup = Join-Path $backupDir "campaign_state_$stamp.json"
    Copy-Item -LiteralPath $statePath -Destination $backup
    Write-Host "     State backed up to $backup"
  }
  & (Join-Path $scriptDir "run_full_cycle_v1.ps1") -Workspace $Workspace -WriteState | Out-Host
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "Campaign advance returned $LASTEXITCODE. State backup is above if you need it."
  }
}

# ---- 11. compare against the AI runs --------------------------------------------
Write-Step "Analysing"
$suite = Join-Path $Workspace "reports\map_surveys\latest_human_suite.json"
& $py (Join-Path $Workspace "tools\ai_duel_zone_flow_v1.py") `
  --workspace $Workspace --suite $suite `
  --out-json (Join-Path $Workspace "reports\human_zone_flow.latest.json") `
  --out-md (Join-Path $Workspace "reports\human_zone_flow.latest.md") | Out-Host

Write-Host ""
Write-Host "  ============================================================"
Write-Host "   Session filed."
Write-Host "     Record:   $runDir"
Write-Host "     Analysis: reports\human_zone_flow.latest.md"
Write-Host "  ============================================================"
Write-Host ""
