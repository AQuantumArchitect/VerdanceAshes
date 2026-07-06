param(
  [string]$Workspace = "",
  [int]$Port = 8765,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CommonPath = Join-Path $ScriptDir "_common.ps1"
if (Test-Path $CommonPath) { . $CommonPath }
if (Get-Command Get-VerdanceWorkspaceRoot -ErrorAction SilentlyContinue) { $Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace }
elseif (-not $Workspace) { $Workspace = Split-Path -Parent $ScriptDir }

function ConvertTo-JsonSafe {
  param($Object, [int]$Depth = 50)
  try { return ($Object | ConvertTo-Json -Depth $Depth -Compress) }
  catch { return '{"ok":false,"error":"JSON serialization failed"}' }
}

function Write-Response {
  param($Context, [string]$Body, [string]$ContentType = "application/json", [int]$StatusCode = 200)
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($Body)
  $Context.Response.StatusCode = $StatusCode
  $Context.Response.ContentType = $ContentType + "; charset=utf-8"
  $Context.Response.ContentLength64 = $bytes.Length
  $Context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
  $Context.Response.OutputStream.Close()
}

function Read-JsonFileLocal {
  param([string]$Path)
  if (-not (Test-Path $Path)) { return $null }
  try { return Get-Content $Path -Raw | ConvertFrom-Json }
  catch { return [pscustomobject]@{ parseError = $_.Exception.Message; raw = (Get-Content $Path -Raw) } }
}

function Read-TextFileLocal {
  param([string]$Path)
  if (-not (Test-Path $Path)) { return $null }
  return Get-Content $Path -Raw
}

function Get-ConfigLocal {
  # Layered config with BAR auto-detection lives in _common.ps1 now.
  try { return Get-VerdanceConfig -Workspace $Workspace }
  catch {
    return [pscustomobject]@{ schemaVersion = "0.8-error"; error = $_.Exception.Message; workspace = $Workspace }
  }
}

function Invoke-ConsoleScript {
  param([string]$ScriptName, [string[]]$ExtraArgs = @())
  $script = Join-Path $ScriptDir $ScriptName
  if (-not (Test-Path $script)) {
    return [pscustomobject]@{ ok = $false; script = $ScriptName; exitCode = -1; stdout = ""; stderr = "Script not found: $script" }
  }
  $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $script, "-Workspace", $Workspace) + $ExtraArgs
  function Quote-ProcessArg([string]$Arg) {
    if ($Arg -match '[\s"]') { return '"' + ($Arg.Replace('"', '\"')) + '"' }
    return $Arg
  }
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = "powershell.exe"
  $psi.Arguments = ($argList | ForEach-Object { Quote-ProcessArg ([string]$_) }) -join " "
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  $p = New-Object System.Diagnostics.Process
  $p.StartInfo = $psi
  [void]$p.Start()
  $stdout = $p.StandardOutput.ReadToEnd()
  $stderr = $p.StandardError.ReadToEnd()
  $p.WaitForExit()
  return [pscustomobject]@{
    ok = ($p.ExitCode -eq 0)
    script = $ScriptName
    exitCode = $p.ExitCode
    stdout = $stdout
    stderr = $stderr
  }
}

function Get-SeedSummary {
  param([string]$SeedPath)
  $txt = Read-TextFileLocal $SeedPath
  if (-not $txt) { return $null }
  $missionId = $null; $missionNumber = $null; $title = $null; $requiredFrames = $null; $schemaVersion = $null
  if ($txt -match 'schemaVersion\s*=\s*"([^"]+)"') { $schemaVersion = $Matches[1] }
  if ($txt -match 'missionId\s*=\s*"([^"]+)"') { $missionId = $Matches[1] }
  if ($txt -match 'missionNumber\s*=\s*([0-9]+)') { $missionNumber = [int]$Matches[1] }
  if ($txt -match 'title\s*=\s*"([^"]+)"') { $title = $Matches[1] }
  if ($txt -match 'requiredFrames\s*=\s*([0-9]+)') { $requiredFrames = [int]$Matches[1] }
  return [pscustomobject]@{
    path = $SeedPath
    exists = $true
    schemaVersion = $schemaVersion
    missionId = $missionId
    missionNumber = $missionNumber
    title = $title
    requiredFrames = $requiredFrames
    preview = (($txt -split "`n") | Select-Object -First 30) -join "`n"
  }
}

function Get-IntentSummary {
  param([string]$IntentPath)
  $intent = Read-JsonFileLocal $IntentPath
  if (-not $intent) { return $null }
  return [pscustomobject]@{
    path = $IntentPath
    schemaVersion = $intent.schemaVersion
    campaignId = $intent.campaignId
    missionId = $intent.missionId
    missionNumber = $intent.missionNumber
    mapId = $intent.mapId
    deploymentZoneId = $intent.deploymentZoneId
    extractionZoneId = $intent.extractionZoneId
    objective = $intent.objective
    objectiveTarget = $intent.objectiveTarget
    expectedEnemyScale = $intent.expectedEnemyScale
    hazardPolicy = $intent.hazardPolicy
    storyReason = $intent.storyReason
    title = $intent.title
    briefing = $intent.briefing
  }
}

function Get-ConsoleStatus {
  $config = Get-ConfigLocal
  $state = Read-JsonFileLocal $config.campaignState
  $result = Read-JsonFileLocal $config.resultInbox
  $ledger = Read-JsonFileLocal $config.processedLedger
  $intentPath = Join-Path $Workspace "outbox\next_mission_intent.json"
  $buildManifestPath = Join-Path $Workspace "outbox\next_mission_build_manifest.json"
  $exports = @()
  if (Test-Path $config.exportDir) {
    $exports = Get-ChildItem -Path $config.exportDir -Filter "verdance_handoff_*.zip" -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 8 |
      ForEach-Object { [pscustomobject]@{ name=$_.Name; fullName=$_.FullName; bytes=$_.Length; lastWriteTime=$_.LastWriteTime.ToString("s") } }
  }
  $stateSummary = $null
  if ($state) {
    $historyCount = 0
    if ($state.PSObject.Properties["history"] -and $state.history) { $historyCount = @($state.history).Count }
    $stateSummary = [pscustomobject]@{
      schemaVersion = $state.schemaVersion
      campaignId = $state.campaignId
      missionNumber = $state.missionNumber
      currentMissionId = $state.currentMissionId
      pathSignal = $state.pathSignal
      historyCount = $historyCount
      graph = $state.graph
      reputation = $state.reputation
      companion = $state.companion
    }
  }
  $resultSummary = $null
  if ($result) {
    $terminal = $false
    if ($result.status -in @("victory", "partial", "defeat", "failed", "aborted")) { $terminal = $true }
    $resultSummary = [pscustomobject]@{
      schemaVersion = $result.schemaVersion
      campaignId = $result.campaignId
      missionId = $result.missionId
      missionNumber = $result.missionNumber
      status = $result.status
      terminal = $terminal
      holdFrames = $result.holdFrames
      requiredFrames = $result.requiredFrames
      pathSignal = $result.pathSignal
    }
  }
  $ledgerSummary = $null
  if ($ledger) {
    $ledgerSummary = [pscustomobject]@{
      schemaVersion = $ledger.schemaVersion
      processedMissionKeyCount = @($ledger.processedMissionKeys).Count
      processedResultCount = @($ledger.processedResults).Count
      latestActiveTelemetry = $ledger.latestActiveTelemetry
      processedMissionKeys = @($ledger.processedMissionKeys)
    }
  }
  return [pscustomobject]@{
    ok = $true
    now = (Get-Date).ToString("s")
    server = [pscustomobject]@{ schemaVersion = "0.7"; port = $Port; workspace = $Workspace }
    health = [pscustomobject]@{
      workspaceExists = (Test-Path $Workspace)
      configExists = (Test-Path (Join-Path $Workspace "verdance_config.json"))
      barSddExists = (Test-Path $config.barSdd)
      infologExists = (Test-Path $config.infolog)
      stateExists = (Test-Path $config.campaignState)
      resultExists = (Test-Path $config.resultInbox)
      seedOutboxExists = (Test-Path $config.seedOutbox)
      seedDestinationExists = (Test-Path $config.seedDestination)
      ledgerExists = (Test-Path $config.processedLedger)
      nextIntentExists = (Test-Path $intentPath)
      nextMissionBuildExists = (Test-Path $buildManifestPath)
    }
    config = $config
    state = $stateSummary
    latestResult = $resultSummary
    ledger = $ledgerSummary
    nextIntent = Get-IntentSummary $intentPath
    nextMissionBuild = Read-JsonFileLocal $buildManifestPath
    seed = Get-SeedSummary $config.seedOutbox
    installedSeed = Get-SeedSummary $config.seedDestination
    session = Read-JsonFileLocal (Join-Path $Workspace "outbox\play_session.status.json")
    exports = @($exports)
  }
}

function Start-DetachedPlaySession {
  $script = Join-Path $ScriptDir "play_session_v1.ps1"
  if (-not (Test-Path $script)) {
    return [pscustomobject]@{ ok = $false; error = "play_session_v1.ps1 not found" }
  }
  $statusPath = Join-Path $Workspace "outbox\play_session.status.json"
  $existing = Read-JsonFileLocal $statusPath
  if ($existing -and $existing.phase -in @("preflight", "building", "in-game", "extracting", "build-next")) {
    # A session may still be live; only block if a spring process really exists.
    $spring = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^spring(-headless)?$' }
    if ($spring) {
      return [pscustomobject]@{ ok = $false; error = "A play session appears to be running (phase: $($existing.phase)). Cancel it first."; session = $existing }
    }
  }
  Start-Process powershell -ArgumentList @(
    "-NoProfile", "-ExecutionPolicy", "Bypass",
    "-File", "`"$script`"", "-Workspace", "`"$Workspace`""
  ) -WindowStyle Hidden
  return [pscustomobject]@{ ok = $true; started = $true; statusPath = $statusPath }
}

function Stop-PlaySession {
  $stopped = @()
  Get-CimInstance Win32_Process |
    Where-Object { $_.Name -match '^powershell' -and $_.CommandLine -match 'play_session_v1\.ps1' } |
    ForEach-Object {
      try { Stop-Process -Id $_.ProcessId -Force; $stopped += "powershell:$($_.ProcessId)" } catch { }
    }
  Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^spring(-headless)?$' } |
    ForEach-Object {
      try { Stop-Process -Id $_.Id -Force; $stopped += "$($_.Name):$($_.Id)" } catch { }
    }
  $statusPath = Join-Path $Workspace "outbox\play_session.status.json"
  $status = Read-JsonFileLocal $statusPath
  if ($status -and $status.PSObject.Properties["phase"]) {
    $status.phase = "cancelled"
    try { $status | ConvertTo-Json | Set-Content -Encoding UTF8 -Path $statusPath } catch { }
  }
  return [pscustomobject]@{ ok = $true; stopped = $stopped }
}

function Get-FilePayload {
  param([string]$Name)
  $config = Get-ConfigLocal
  $map = @{
    state = $config.campaignState
    result = $config.resultInbox
    ledger = $config.processedLedger
    seed = $config.seedOutbox
    installedSeed = $config.seedDestination
    config = (Join-Path $Workspace "verdance_config.json")
    nextIntent = (Join-Path $Workspace "outbox\next_mission_intent.json")
    nextMissionBuild = (Join-Path $Workspace "outbox\next_mission_build_manifest.json")
  }
  if (-not $map.ContainsKey($Name)) { return [pscustomobject]@{ ok=$false; error="Unknown file key: $Name" } }
  $path = $map[$Name]
  if (-not (Test-Path $path)) { return [pscustomobject]@{ ok=$false; path=$path; error="File not found" } }
  return [pscustomobject]@{ ok=$true; name=$Name; path=$path; text=(Get-Content $path -Raw) }
}

$prefix = "http://127.0.0.1:$Port/"
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add($prefix)
try {
  $listener.Start()
} catch {
  Write-Host "Could not start Verdance console on $prefix"
  Write-Host $_.Exception.Message
  Write-Host "Try closing any old Verdance Console PowerShell windows, then run this again."
  exit 1
}

Write-Host "Verdance Companion Console v0.7"
Write-Host "Workspace: $Workspace"
Write-Host "Serving: $prefix"
Write-Host "Close this PowerShell window to stop the console."
if (-not $NoBrowser) { Start-Process $prefix }

while ($listener.IsListening) {
  try {
    $ctx = $listener.GetContext()
    $path = $ctx.Request.Url.AbsolutePath
    $method = $ctx.Request.HttpMethod.ToUpperInvariant()
    if ($path -eq "/" -or $path -eq "/index.html") {
      $htmlPath = Join-Path $Workspace "tools\verdance_companion_console_v0_7.html"
      if (-not (Test-Path $htmlPath)) { $htmlPath = Join-Path (Split-Path -Parent $ScriptDir) "tools\verdance_companion_console_v0_7.html" }
      if (Test-Path $htmlPath) { Write-Response $ctx (Get-Content $htmlPath -Raw) "text/html" 200 }
      else { Write-Response $ctx "Verdance console HTML not found." "text/plain" 500 }
      continue
    }
    if ($path -eq "/api/status") { Write-Response $ctx (ConvertTo-JsonSafe (Get-ConsoleStatus)) ; continue }
    if ($path -eq "/api/sessionStatus") {
      $sessionStatus = Read-JsonFileLocal (Join-Path $Workspace "outbox\play_session.status.json")
      if (-not $sessionStatus) { $sessionStatus = [pscustomobject]@{ phase = "idle" } }
      Write-Response $ctx (ConvertTo-JsonSafe $sessionStatus)
      continue
    }
    if ($path -eq "/api/file") {
      $name = $ctx.Request.QueryString["name"]
      Write-Response $ctx (ConvertTo-JsonSafe (Get-FilePayload $name))
      continue
    }
    if ($method -ne "POST") { Write-Response $ctx (ConvertTo-JsonSafe ([pscustomobject]@{ ok=$false; error="Use POST for action endpoints." })) "application/json" 405; continue }
    if ($path -eq "/api/extract") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "extract_latest_result.ps1")) ; continue }
    if ($path -eq "/api/advance") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "advance_campaign.ps1")) ; continue }
    if ($path -eq "/api/advanceForce") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "advance_campaign.ps1" @("-ForceNext"))) ; continue }
    if ($path -eq "/api/runCycle") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "run_full_cycle.ps1")) ; continue }
    if ($path -eq "/api/advanceV1") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "advance_campaign_v1.ps1" @("-WriteState"))) ; continue }
    if ($path -eq "/api/runCycleV1") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "run_full_cycle_v1.ps1" @("-WriteState"))) ; continue }
    if ($path -eq "/api/playSession") { Write-Response $ctx (ConvertTo-JsonSafe (Start-DetachedPlaySession)) ; continue }
    if ($path -eq "/api/cancelSession") { Write-Response $ctx (ConvertTo-JsonSafe (Stop-PlaySession)) ; continue }
    if ($path -eq "/api/migrateState") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "migrate_state_v1.ps1")) ; continue }
    if ($path -eq "/api/installMod") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "install_mod_archive.ps1")) ; continue }
    if ($path -eq "/api/buildNextMissionV1") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "build_next_mission_v1.ps1")) ; continue }
    if ($path -eq "/api/playNextMissionV1") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "build_next_mission_v1.ps1" @("-Launch"))) ; continue }
    if ($path -eq "/api/createNextMissionSaveV1") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "build_next_mission_v1.ps1" @("-SaveGame"))) ; continue }
    if ($path -eq "/api/processHealth") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "verdance_process_health.ps1")) ; continue }
    if ($path -eq "/api/stopSpring") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "verdance_process_health.ps1" @("-StopSpring"))) ; continue }
    if ($path -eq "/api/stopVerdanceSlop") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "verdance_process_health.ps1" @("-StopAllVerdance"))) ; continue }
    if ($path -eq "/api/export") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "export_for_chatgpt.ps1")) ; continue }
    if ($path -eq "/api/runAndExport") { Write-Response $ctx (ConvertTo-JsonSafe (Invoke-ConsoleScript "run_and_export.ps1")) ; continue }
    if ($path -eq "/api/openWorkspace") { Start-Process $Workspace; Write-Response $ctx (ConvertTo-JsonSafe ([pscustomobject]@{ ok=$true; opened=$Workspace })) ; continue }
    if ($path -eq "/api/openExport") { $c=Get-ConfigLocal; New-Item -ItemType Directory -Force -Path $c.exportDir | Out-Null; Start-Process $c.exportDir; Write-Response $ctx (ConvertTo-JsonSafe ([pscustomobject]@{ ok=$true; opened=$c.exportDir })) ; continue }
    if ($path -eq "/api/shutdown") { Write-Response $ctx (ConvertTo-JsonSafe ([pscustomobject]@{ ok=$true; message="Console shutting down." })); $listener.Stop(); break }
    Write-Response $ctx (ConvertTo-JsonSafe ([pscustomobject]@{ ok=$false; error="Unknown route: $path" })) "application/json" 404
  } catch {
    try { Write-Response $ctx (ConvertTo-JsonSafe ([pscustomobject]@{ ok=$false; error=$_.Exception.Message })) "application/json" 500 } catch { }
  }
}
