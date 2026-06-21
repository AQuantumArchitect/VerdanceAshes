function Get-VerdanceConfig {
  param([string]$Workspace)
  if (-not $Workspace) { $Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace" }
  $configPath = Join-Path $Workspace "verdance_config.json"
  if (!(Test-Path $configPath)) { throw "No verdance_config.json at $configPath. Run install_v06.bat first." }
  return Get-Content $configPath -Raw | ConvertFrom-Json
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
