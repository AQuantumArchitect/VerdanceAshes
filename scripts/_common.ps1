function Get-VerdanceWorkspaceRoot {
  param([string]$Workspace)
  if ($Workspace) { return (Resolve-Path $Workspace).Path }
  if ($env:VERDANCE_WORKSPACE -and (Test-Path $env:VERDANCE_WORKSPACE)) {
    return (Resolve-Path $env:VERDANCE_WORKSPACE).Path
  }
  # scripts\ lives directly under the workspace root
  return Split-Path -Parent $PSScriptRoot
}

function Find-BARDataRoot {
  if ($env:BAR_DATA_ROOT -and (Test-Path $env:BAR_DATA_ROOT)) { return $env:BAR_DATA_ROOT }
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Beyond-All-Reason\data"),
    "C:\Program Files\Beyond-All-Reason\data",
    (Join-Path ${env:ProgramFiles(x86)} "Steam\steamapps\common\Beyond All Reason\data")
  )
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path (Join-Path $candidate "engine"))) { return $candidate }
  }
  return $null
}

function Get-VerdanceConfig {
  param([string]$Workspace)
  $Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
  $configPath = Join-Path $Workspace "verdance_config.json"
  $config = if (Test-Path $configPath) {
    Get-Content $configPath -Raw | ConvertFrom-Json
  } else {
    [pscustomobject]@{ schemaVersion = "0.8-autodetect" }
  }

  function Set-DefaultProp($Object, [string]$Name, $Value) {
    if (-not $Object.PSObject.Properties[$Name] -or -not $Object.$Name) {
      if ($Object.PSObject.Properties[$Name]) { $Object.$Name = $Value }
      else { $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value }
    }
  }

  Set-DefaultProp $config "workspace" $Workspace
  if (-not ($config.PSObject.Properties["barDataRoot"] -and $config.barDataRoot -and (Test-Path $config.barDataRoot))) {
    $detected = Find-BARDataRoot
    if (-not $detected) { throw "Could not locate a Beyond All Reason data directory. Set barDataRoot in verdance_config.json or the BAR_DATA_ROOT environment variable." }
    Set-DefaultProp $config "barDataRoot" $detected
    if ($config.PSObject.Properties["barDataRoot"]) { $config.barDataRoot = $detected }
  }

  # BAR-side derived paths
  Set-DefaultProp $config "barSdd" (Join-Path $config.barDataRoot "games\BAR.sdd")
  Set-DefaultProp $config "infolog" (Join-Path $config.barDataRoot "infolog.txt")
  Set-DefaultProp $config "modSdd" (Join-Path $config.barDataRoot "games\VerdanceAshes.sdd")
  Set-DefaultProp $config "gameType" 'Verdance Ashes $VERSION'
  Set-DefaultProp $config "seedDestination" (Join-Path $config.modSdd "singleplayer\verdance_ashes\generated\va_current.lua")

  # Workspace-side derived paths
  Set-DefaultProp $config "resultInbox" (Join-Path $Workspace "inbox\latest_va_result.json")
  Set-DefaultProp $config "campaignState" (Join-Path $Workspace "state\campaign_state.json")
  Set-DefaultProp $config "seedOutbox" (Join-Path $Workspace "outbox\va_current.lua")
  Set-DefaultProp $config "processedLedger" (Join-Path $Workspace "ledger\processed_results.json")
  Set-DefaultProp $config "exportDir" (Join-Path $Workspace "export")
  Set-DefaultProp $config "zoneMap" (Join-Path $Workspace "data\zone_maps\greenest_fields.zone_map.json")

  return $config
}

function Get-BAREngineDir {
  param($Config, [string]$EngineName = "spring.exe")
  if ($Config.PSObject.Properties["engineDir"] -and $Config.engineDir -and (Test-Path (Join-Path $Config.engineDir $EngineName))) {
    return $Config.engineDir
  }
  $engineRoot = Join-Path $Config.barDataRoot "engine"
  if (!(Test-Path $engineRoot)) { throw "No engine directory under $($Config.barDataRoot)" }
  $dirs = Get-ChildItem $engineRoot -Directory | Where-Object { Test-Path (Join-Path $_.FullName $EngineName) } | Sort-Object Name -Descending
  if (-not $dirs) { throw "No engine folder containing $EngineName under $engineRoot" }
  return $dirs[0].FullName
}

function Get-VerdancePython {
  param([string]$Workspace)
  # Prefer explicit env (PLAY/_env.bat sets VERDANCE_PY)
  foreach ($envName in @("VERDANCE_PY", "VERDANCE_PYTHON")) {
    $v = [Environment]::GetEnvironmentVariable($envName)
    if ($v -and (Test-Path $v)) { return $v }
  }
  if ($Workspace) {
    $embedded = Join-Path $Workspace "runtime\python\python.exe"
    if (Test-Path $embedded) { return $embedded }
  }
  # Prefer full python.exe over WindowsApps stub when possible
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source -and ($cmd.Source -notmatch 'WindowsApps')) {
    return $cmd.Source
  }
  $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
  if ($pyLauncher) {
    try {
      $exe = & py -3 -c "import sys; print(sys.executable)" 2>$null
      if ($exe -and (Test-Path $exe.Trim())) { return $exe.Trim() }
    } catch {}
  }
  if ($cmd) { return $cmd.Source }
  throw "No Python interpreter found. Install Python 3 or place an embeddable Python at runtime\python\."
}

function Get-BARInfolog {
  param([string]$Workspace)
  $config = Get-VerdanceConfig -Workspace $Workspace
  return $config.infolog
}

function Clamp-Number {
  param([double]$Value, [double]$Min, [double]$Max)
  if ($Value -lt $Min) { return $Min }
  if ($Value -gt $Max) { return $Max }
  return $Value
}

function Get-MissionNumberFromId {
  param([string]$MissionId)
  if ($MissionId -match 'va_(\d+)') { return [int]$Matches[1] }
  return 1
}

function Get-ResultMissionNumber {
  param($Result)
  if ($Result.PSObject.Properties['missionNumber'] -and $Result.missionNumber) { return [int]$Result.missionNumber }
  return Get-MissionNumberFromId ([string]$Result.missionId)
}

function Format-LuaNumber {
  param([double]$Value)
  return ([string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", $Value))
}

function Is-TerminalVerdanceStatus {
  param([string]$Status)
  return ($Status -in @("victory", "partial", "defeat", "failed", "aborted"))
}

function New-VerdanceResultKey {
  param($Result)
  $campaign = if ($Result.campaignId) { [string]$Result.campaignId } else { "verdance_ashes" }
  $missionId = if ($Result.missionId) { [string]$Result.missionId } else { "va_unknown" }
  $missionNumber = Get-ResultMissionNumber $Result
  return "$campaign|$missionId|$missionNumber"
}

function Get-StringSha256 {
  param([string]$Text)
  $sha = [System.Security.Cryptography.SHA256]::Create()
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
  $hash = $sha.ComputeHash($bytes)
  return ([System.BitConverter]::ToString($hash)).Replace("-", "").ToLowerInvariant()
}

function Get-ResultHash {
  param($Result)
  $compact = $Result | ConvertTo-Json -Depth 30 -Compress
  return Get-StringSha256 $compact
}

function Ensure-Obj {
  param($Parent, [string]$Name)
  if (-not $Parent.PSObject.Properties[$Name]) {
    $Parent | Add-Member -NotePropertyName $Name -NotePropertyValue ([pscustomobject]@{})
  }
}

function Ensure-ArrayProp {
  param($Parent, [string]$Name)
  if (-not $Parent.PSObject.Properties[$Name]) {
    $Parent | Add-Member -NotePropertyName $Name -NotePropertyValue @()
  }
}

function Read-JsonOrDefault {
  param([string]$Path, $Default)
  if (Test-Path $Path) { return Get-Content $Path -Raw | ConvertFrom-Json }
  return $Default
}

function Save-Json {
  param($Object, [string]$Path)
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
  $Object | ConvertTo-Json -Depth 50 | Set-Content -Encoding UTF8 $Path
}

function ConvertTo-LuaStringLiteral {
  param([string]$Value)
  if ($null -eq $Value) { return '""' }
  $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
  $escaped = $escaped.Replace("`r", '\r').Replace("`n", '\n').Replace("`t", '\t')
  return '"' + $escaped + '"'
}

function ConvertTo-LuaKey {
  param([string]$Key)
  if ($Key -match '^[A-Za-z_][A-Za-z0-9_]*$') { return $Key }
  return '[' + (ConvertTo-LuaStringLiteral $Key) + ']'
}

function ConvertTo-LuaLiteral {
  param($Value, [int]$Indent = 0)
  $pad = " " * $Indent
  $childPad = " " * ($Indent + 2)

  if ($null -eq $Value) { return "nil" }
  if ($Value -is [string]) { return ConvertTo-LuaStringLiteral $Value }
  if ($Value -is [bool]) {
    if ($Value) { return "true" }
    return "false"
  }
  if ($Value -is [byte] -or $Value -is [int16] -or $Value -is [int32] -or $Value -is [int64] -or $Value -is [single] -or $Value -is [double] -or $Value -is [decimal]) {
    return Format-LuaNumber ([double]$Value)
  }
  if ($Value -is [System.Collections.IDictionary]) {
    $parts = @()
    foreach ($key in $Value.Keys) {
      $parts += $childPad + (ConvertTo-LuaKey ([string]$key)) + " = " + (ConvertTo-LuaLiteral $Value[$key] ($Indent + 2))
    }
    if ($parts.Count -eq 0) { return "{}" }
    return "{`n" + ($parts -join ",`n") + "`n$pad}"
  }
  if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {
    $parts = @()
    foreach ($item in @($Value)) {
      $parts += $childPad + (ConvertTo-LuaLiteral $item ($Indent + 2))
    }
    if ($parts.Count -eq 0) { return "{}" }
    return "{`n" + ($parts -join ",`n") + "`n$pad}"
  }
  if ($Value.PSObject -and $Value.PSObject.Properties) {
    $parts = @()
    foreach ($prop in $Value.PSObject.Properties) {
      $parts += $childPad + (ConvertTo-LuaKey $prop.Name) + " = " + (ConvertTo-LuaLiteral $prop.Value ($Indent + 2))
    }
    if ($parts.Count -eq 0) { return "{}" }
    return "{`n" + ($parts -join ",`n") + "`n$pad}"
  }
  return ConvertTo-LuaStringLiteral ([string]$Value)
}

function Install-VerdanceZoneMap {
  param($Config)
  if (-not $Config.zoneMap) { return $null }
  if (!(Test-Path $Config.zoneMap)) { throw "No zone map JSON at $($Config.zoneMap)" }

  $zoneMap = Get-Content $Config.zoneMap -Raw | ConvertFrom-Json
  $generatedDir = Split-Path -Parent $Config.seedDestination
  $zoneMapDestination = Join-Path $generatedDir "zone_map_current.lua"
  $lua = "return " + (ConvertTo-LuaLiteral $zoneMap 0) + "`n"
  New-Item -ItemType Directory -Force -Path $generatedDir | Out-Null
  Set-Content -Encoding ASCII -Path $zoneMapDestination -Value $lua
  return $zoneMapDestination
}
