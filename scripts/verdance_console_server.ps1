param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [int]$Port = 8765,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$CommonPath = Join-Path $ScriptDir "_common.ps1"
if (Test-Path $CommonPath) { . $CommonPath }

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
  $configPath = Join-Path $Workspace "verdance_config.json"
  if (Test-Path $configPath) {
    try { return Get-Content $configPath -Raw | ConvertFrom-Json }
    catch { }
  }
  $barDataRoot = "$env:LOCALAPPDATA\Programs\Beyond-All-Reason\data"
  $barSdd = Join-Path $barDataRoot "games\BAR.sdd"
  return [pscustomobject]@{
    schemaVersion = "0.7-fallback"
    barDataRoot = $barDataRoot
    barSdd = $barSdd
    workspace = $Workspace
    infolog = (Join-Path $barDataRoot "infolog.txt")
    seedDestination = (Join-Path $barSdd "singleplayer\verdance_ashes\generated\va_current.lua")
    resultInbox = (Join-Path $Workspace "inbox\latest_va_result.json")
    campaignState = (Join-Path $Workspace "state\campaign_state.json")
    seedOutbox = (Join-Path $Workspace "outbox\va_current.lua")
    processedLedger = (Join-Path $Workspace "ledger\processed_results.json")
    exportDir = (Join-Path $Workspace "export")
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

function Get-ConsoleStatus {
  $config = Get-ConfigLocal
  $state = Read-JsonFileLocal $config.campaignState
  $result = Read-JsonFileLocal $config.resultInbox
  $ledger = Read-JsonFileLocal $config.processedLedger
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
    }
    config = $config
    state = $stateSummary
    latestResult = $resultSummary
    ledger = $ledgerSummary
    seed = Get-SeedSummary $config.seedOutbox
    installedSeed = Get-SeedSummary $config.seedDestination
    exports = @($exports)
  }
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
