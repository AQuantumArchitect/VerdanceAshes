function Get-VerdanceWorkspaceRoot {
  param([string]$Workspace)
  if ($Workspace) { return (Resolve-Path $Workspace).Path }
  if ($env:VERDANCE_WORKSPACE -and (Test-Path $env:VERDANCE_WORKSPACE)) {
    return (Resolve-Path $env:VERDANCE_WORKSPACE).Path
  }
  # scripts\ lives directly under the workspace root
  return Split-Path -Parent $PSScriptRoot
}

function Get-BAREngineDirs {
  # Every engine\<version>\ folder under a BAR data root that holds spring.exe (newest name last).
  param([string]$BarDataRoot)
  if (-not $BarDataRoot) { return @() }
  $engineRoot = Join-Path $BarDataRoot "engine"
  if (!(Test-Path $engineRoot)) { return @() }
  return @(Get-ChildItem $engineRoot -Directory -ErrorAction SilentlyContinue |
    Where-Object { Test-Path (Join-Path $_.FullName "spring.exe") } |
    Sort-Object Name)
}

function Test-BARDataRoot {
  # A usable BAR data root: the folder exists and at least one engine\*\spring.exe is installed.
  param([string]$BarDataRoot)
  if (-not $BarDataRoot -or !(Test-Path $BarDataRoot)) { return $false }
  return ((Get-BAREngineDirs -BarDataRoot $BarDataRoot).Count -gt 0)
}

function Get-SteamLibraryRoots {
  # Steam install dir (registry, then the usual folders) plus every library in libraryfolders.vdf.
  $steamRoots = @()
  foreach ($key in @("HKCU:\Software\Valve\Steam", "HKLM:\SOFTWARE\WOW6432Node\Valve\Steam", "HKLM:\SOFTWARE\Valve\Steam")) {
    try {
      $props = Get-ItemProperty -Path $key -ErrorAction Stop
      foreach ($name in @("SteamPath", "InstallPath")) {
        if ($props.PSObject.Properties[$name] -and $props.$name) { $steamRoots += [string]$props.$name }
      }
    } catch {}
  }
  if (${env:ProgramFiles(x86)}) { $steamRoots += (Join-Path ${env:ProgramFiles(x86)} "Steam") }
  if ($env:ProgramFiles) { $steamRoots += (Join-Path $env:ProgramFiles "Steam") }
  $libs = @()
  foreach ($root in $steamRoots) {
    if (-not $root) { continue }
    $root = $root -replace "/", "\"
    if (!(Test-Path $root)) { continue }
    $libs += $root
    $vdf = Join-Path $root "steamapps\libraryfolders.vdf"
    if (Test-Path $vdf) {
      try {
        $text = Get-Content -Raw $vdf
        foreach ($m in [regex]::Matches($text, '"path"\s+"([^"]+)"')) {
          $libs += ($m.Groups[1].Value -replace "\\\\", "\")
        }
      } catch {}
    }
  }
  return @($libs | Where-Object { $_ } | Select-Object -Unique)
}

function Get-BARDataRootCandidates {
  # Detection order: the standard installer, Program Files, then Steam libraries (both folder spellings).
  $c = @()
  if ($env:LOCALAPPDATA) { $c += (Join-Path $env:LOCALAPPDATA "Programs\Beyond-All-Reason\data") }
  if ($env:ProgramFiles) { $c += (Join-Path $env:ProgramFiles "Beyond-All-Reason\data") }
  if (${env:ProgramFiles(x86)}) { $c += (Join-Path ${env:ProgramFiles(x86)} "Beyond-All-Reason\data") }
  foreach ($lib in (Get-SteamLibraryRoots)) {
    foreach ($name in @("Beyond All Reason", "Beyond-All-Reason")) {
      $c += (Join-Path $lib "steamapps\common\$name\data")
    }
  }
  return @($c | Where-Object { $_ } | Select-Object -Unique)
}

function Get-ConfiguredBARDataRoot {
  # verdance_config.json barDataRoot is authoritative when it names a folder that exists.
  param([string]$Workspace)
  if (-not $Workspace) { return $null }
  $configPath = Join-Path $Workspace "verdance_config.json"
  if (!(Test-Path $configPath)) { return $null }
  try {
    $cfg = Get-Content $configPath -Raw | ConvertFrom-Json
    if ($cfg.PSObject.Properties["barDataRoot"] -and $cfg.barDataRoot -and (Test-Path $cfg.barDataRoot)) {
      return [string]$cfg.barDataRoot
    }
  } catch {}
  return $null
}

function Find-BARDataRoot {
  # Order: verdance_config.json -> BAR_DATA_ROOT env -> detected roots that have an engine
  # -> detected roots that merely exist (BAR installed but never launched; the caller
  # tells the player to launch BAR once so it installs an engine). $null when nothing.
  param([string]$Workspace)
  $configured = Get-ConfiguredBARDataRoot -Workspace $Workspace
  if ($configured) { return $configured }
  if ($env:BAR_DATA_ROOT -and (Test-Path $env:BAR_DATA_ROOT)) { return $env:BAR_DATA_ROOT }
  $candidates = Get-BARDataRootCandidates
  foreach ($candidate in $candidates) {
    if (Test-BARDataRoot -BarDataRoot $candidate) { return $candidate }
  }
  foreach ($candidate in $candidates) {
    if (Test-Path (Join-Path $candidate "games")) { return $candidate }
  }
  return $null
}

function Assert-BARDataRoot {
  # Throws a player-readable message when $BarDataRoot is not a usable BAR data root.
  param([string]$BarDataRoot)
  if (-not $BarDataRoot -or !(Test-Path $BarDataRoot)) {
    throw "No Beyond All Reason data directory found. Install BAR first (https://www.beyondallreason.info), then run SETUP.bat and enter the path to its 'data' folder when asked."
  }
  if (!(Test-Path (Join-Path $BarDataRoot "games"))) {
    throw "'$BarDataRoot' does not look like a BAR data directory (no games\ folder). It is usually ...\Beyond-All-Reason\data."
  }
  if (-not (Test-BARDataRoot -BarDataRoot $BarDataRoot)) {
    throw "No engine with spring.exe found under $BarDataRoot\engine. Launch BAR once so it installs an engine, then run SETUP.bat again."
  }
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
    $detected = Find-BARDataRoot -Workspace $Workspace
    if (-not $detected) { throw "Could not locate a Beyond All Reason data directory. Run SETUP.bat (it asks for the path when it cannot detect BAR), or set barDataRoot in verdance_config.json / the BAR_DATA_ROOT environment variable." }
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

function Test-VerdancePythonExe {
  # True when $Path exists, is not the Microsoft Store stub (WindowsApps), and runs as Python 3.10+.
  param([string]$Path)
  if (-not $Path) { return $false }
  $Path = $Path.Trim()
  if (!(Test-Path -LiteralPath $Path)) { return $false }
  if ($Path -match 'WindowsApps') { return $false }
  try {
    & $Path -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}

function Get-VerdancePython {
  param([string]$Workspace)
  # Same order as app\bin\_env.bat, so PLAY/SETUP/SHIP agree on one interpreter:
  #   runtime\python (ship embed) -> VERDANCE_PY / VERDANCE_PYTHON -> py -3 -> python / python3 on PATH.
  # Every candidate is run before it is accepted; the WindowsApps Store stub never qualifies.
  if (-not $Workspace) { $Workspace = Get-VerdanceWorkspaceRoot }
  if ($Workspace) {
    $embedded = Join-Path $Workspace "runtime\python\python.exe"
    if (Test-VerdancePythonExe $embedded) { return $embedded }
  }
  foreach ($envName in @("VERDANCE_PY", "VERDANCE_PYTHON")) {
    $v = [Environment]::GetEnvironmentVariable($envName)
    if (Test-VerdancePythonExe $v) { return $v.Trim() }
  }
  if (Get-Command py -ErrorAction SilentlyContinue) {
    try {
      $exe = & py -3 -c "import sys; print(sys.executable)" 2>$null
      if ($exe -and (Test-VerdancePythonExe ([string]$exe))) { return ([string]$exe).Trim() }
    } catch {}
  }
  foreach ($name in @("python", "python3")) {
    foreach ($cmd in @(Get-Command $name -All -ErrorAction SilentlyContinue)) {
      if ($cmd.Source -and (Test-VerdancePythonExe $cmd.Source)) { return $cmd.Source }
    }
  }
  throw "No working Python 3.10+ found. Install Python 3.10 or newer from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), or use the SHIP zip, which embeds Python under runtime\python\."
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
  # The seed files are written ASCII; carry anything else (an em dash, a name with an accent)
  # as Lua decimal byte escapes of its UTF-8, so it reaches BAR intact instead of as "?".
  if ($escaped -match '[^\x00-\x7F]') {
    $sb = New-Object System.Text.StringBuilder
    foreach ($b in [System.Text.Encoding]::UTF8.GetBytes($escaped)) {
      if ($b -lt 128) { [void]$sb.Append([char]$b) } else { [void]$sb.Append('\' + $b) }
    }
    $escaped = $sb.ToString()
  }
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
