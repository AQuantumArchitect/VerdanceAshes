# Shared helpers for Verdance cloud BAR bakes.

function Get-CloudConfigPath {
  param([string]$Workspace)
  $primary = Join-Path $Workspace "data\cloud\cloud_config.json"
  if (Test-Path $primary) { return $primary }
  return Join-Path $Workspace "data\cloud\cloud_config.template.json"
}

function Get-CloudConfig {
  param([string]$Workspace)
  $path = Get-CloudConfigPath -Workspace $Workspace
  if (!(Test-Path $path)) { throw "Missing cloud config. Copy data/cloud/cloud_config.template.json to cloud_config.json and fill host/auth." }
  $cfg = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
  if (-not $cfg.host -or $cfg.host -match 'YOUR\.CLOUD') {
    throw "cloud_config.json host is not set. Edit data/cloud/cloud_config.json first."
  }
  return $cfg
}

function Get-CloudConfigOptional {
  param([string]$Workspace)
  $path = Join-Path $Workspace "data\cloud\cloud_config.json"
  if (!(Test-Path $path)) { return $null }
  try {
    return Get-Content -Raw -LiteralPath $path | ConvertFrom-Json
  } catch {
    return $null
  }
}

function Get-SevenMapArchiveNames {
  param([string]$Workspace)
  $poolPath = Join-Path $Workspace "data\map_pool\seven_maps.json"
  $pool = Get-Content -Raw -LiteralPath $poolPath | ConvertFrom-Json
  $names = @()
  foreach ($m in @($pool.maps)) {
    if ($m.archivePattern) { $names += [string]$m.archivePattern }
  }
  return $names
}

function New-SshBaseArgs {
  param($CloudConfig)
  $args = @()
  $port = 22
  if ($CloudConfig.port) { $port = [int]$CloudConfig.port }
  $args += @("-p", "$port")
  $args += @("-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=20")
  if ($CloudConfig.auth -and $CloudConfig.auth.privateKeyPath -and (Test-Path $CloudConfig.auth.privateKeyPath)) {
    $args += @("-i", [string]$CloudConfig.auth.privateKeyPath)
  }
  return $args
}

function Get-SshTarget {
  param($CloudConfig)
  return "$($CloudConfig.user)@$($CloudConfig.host)"
}

function Invoke-RemoteSsh {
  param(
    $CloudConfig,
    [string]$RemoteCommand,
    [switch]$Capture
  )
  $sshArgs = New-SshBaseArgs -CloudConfig $CloudConfig
  $target = Get-SshTarget -CloudConfig $CloudConfig
  $all = @($sshArgs + @($target, $RemoteCommand))
  Write-Host "SSH: $target :: $RemoteCommand"
  if ($Capture) {
    $out = & ssh @all 2>&1
    return $out
  }
  & ssh @all
  if ($LASTEXITCODE -ne 0) { throw "SSH command failed with exit $LASTEXITCODE" }
}

function Copy-ToRemote {
  param(
    $CloudConfig,
    [string]$LocalPath,
    [string]$RemotePath,
    [switch]$Recursive
  )
  $port = 22
  if ($CloudConfig.port) { $port = [int]$CloudConfig.port }
  $scpArgs = @("-P", "$port", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new")
  if ($CloudConfig.auth -and $CloudConfig.auth.privateKeyPath -and (Test-Path $CloudConfig.auth.privateKeyPath)) {
    $scpArgs += @("-i", [string]$CloudConfig.auth.privateKeyPath)
  }
  if ($Recursive) { $scpArgs += "-r" }
  $target = "$(Get-SshTarget -CloudConfig $CloudConfig):$RemotePath"
  Write-Host "SCP -> $target  from $LocalPath"
  & scp @($scpArgs + @($LocalPath, $target))
  if ($LASTEXITCODE -ne 0) { throw "SCP upload failed exit $LASTEXITCODE" }
}

function Copy-FromRemote {
  param(
    $CloudConfig,
    [string]$RemotePath,
    [string]$LocalPath,
    [switch]$Recursive
  )
  $port = 22
  if ($CloudConfig.port) { $port = [int]$CloudConfig.port }
  $scpArgs = @("-P", "$port", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new")
  if ($CloudConfig.auth -and $CloudConfig.auth.privateKeyPath -and (Test-Path $CloudConfig.auth.privateKeyPath)) {
    $scpArgs += @("-i", [string]$CloudConfig.auth.privateKeyPath)
  }
  if ($Recursive) { $scpArgs += "-r" }
  $src = "$(Get-SshTarget -CloudConfig $CloudConfig):$RemotePath"
  Write-Host "SCP <- $src  to $LocalPath"
  & scp @($scpArgs + @($src, $LocalPath))
  if ($LASTEXITCODE -ne 0) { throw "SCP download failed exit $LASTEXITCODE" }
}

function Side-Rgb([string]$Side) {
  switch ($Side) {
    "Cortex" { return "1.0 0.2 0.16" }
    "Legion" { return "0.25 0.85 0.35" }
    default  { return "0.25 0.48 1.0" }
  }
}

function Resolve-StartGrowAI($start, $recipe, $catalog) {
  $profileName = $null
  if ($start.PSObject.Properties["growProfile"] -and $start.growProfile) {
    $profileName = [string]$start.growProfile
  }
  $aiShort = "SimpleAI"
  $barbProfile = $null
  $version = "<not-versioned>"
  $label = "SimpleAI"
  if ($profileName -and $catalog.ContainsKey($profileName)) {
    $gp = $catalog[$profileName]
    if ($gp.aiShortName) { $aiShort = [string]$gp.aiShortName }
    if ($gp.barbProfile) { $barbProfile = [string]$gp.barbProfile }
    if ($gp.version) { $version = [string]$gp.version }
    if ($gp.label) { $label = [string]$gp.label }
  } elseif ($start.PSObject.Properties["aiShortName"] -and $start.aiShortName) {
    $aiShort = [string]$start.aiShortName
    if ($start.PSObject.Properties["barbProfile"] -and $start.barbProfile) {
      $barbProfile = [string]$start.barbProfile
      $version = "stable"
    }
  } elseif ($recipe.PSObject.Properties["aiShortName"] -and $recipe.aiShortName) {
    $aiShort = [string]$recipe.aiShortName
  }
  $side = "Armada"
  if ($start.PSObject.Properties["side"] -and $start.side) { $side = [string]$start.side }
  elseif ($recipe.PSObject.Properties["side"] -and $recipe.side) { $side = [string]$recipe.side }
  return [ordered]@{
    profileName = $profileName
    aiShortName = $aiShort
    barbProfile = $barbProfile
    version = $version
    label = $label
    side = $side
  }
}

function New-ShellBakeStartscript {
  param(
    [string]$Workspace,
    [string]$MapId,
    [string]$OutPath,
    [string]$GameType = 'Verdance Ashes $VERSION',
    [string]$RecipePath = ""
  )
  $recipePath = $RecipePath
  if (-not $recipePath) {
    $recipePath = Join-Path $Workspace "data\base_templates\$MapId\bake_recipe.json"
  }
  if (!(Test-Path $recipePath)) { throw "Missing bake recipe: $recipePath" }
  $recipe = Get-Content -Raw -LiteralPath $recipePath | ConvertFrom-Json
  if (-not $MapId -and $recipe.mapId) { $MapId = [string]$recipe.mapId }
  if (-not $MapId) { $MapId = "unknown_map" }

  $growCatalog = @{}
  $growCatalogPath = Join-Path $Workspace "data\base_templates\grow_profiles.json"
  if (Test-Path $growCatalogPath) {
    $growDoc = Get-Content -Raw -LiteralPath $growCatalogPath | ConvertFrom-Json
    foreach ($prop in $growDoc.profiles.PSObject.Properties) {
      $growCatalog[$prop.Name] = $prop.Value
    }
  }

  $mapName = if ($recipe.mapName) { [string]$recipe.mapName } else { throw "bake_recipe missing mapName" }
  $growFrames = if ($recipe.growFrames) { [int]$recipe.growFrames } else { 27000 }
  $startsAll = @($recipe.starts)
  # Battle farms may list claim pockets that are NOT AI starts (aiStart: false).
  $aiStarts = @()
  foreach ($s in $startsAll) {
    if ($s.PSObject.Properties["aiStart"] -and ($null -ne $s.aiStart) -and -not [bool]$s.aiStart) { continue }
    $aiStarts += $s
  }
  if (-not $aiStarts -or $aiStarts.Count -eq 0) { $aiStarts = $startsAll }
  $teamCount = [Math]::Min([int]$recipe.teamCount, $aiStarts.Count)
  if ($teamCount -lt 1) { throw "bake_recipe has no AI starts" }
  $peaceful = $true
  if ($null -ne $recipe.peacefulCoGrow) { $peaceful = [bool]$recipe.peacefulCoGrow }

  $allyBlocks = New-Object System.Collections.Generic.List[string]
  $teamBlocks = New-Object System.Collections.Generic.List[string]
  $aiBlocks = New-Object System.Collections.Generic.List[string]
  $aiSummary = New-Object System.Collections.Generic.List[string]

  for ($i = 0; $i -lt $teamCount; $i++) {
    $s = $aiStarts[$i]
    $x = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", [double]$s.x)
    $z = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", [double]$s.z)
    $grow = Resolve-StartGrowAI $s $recipe $growCatalog
    $side = [string]$grow.side
    $rgb = Side-Rgb $side

    if ($peaceful) {
      $allyLines = @()
      $allyLines += "    NumAllies=$($teamCount - 1);"
      $aiIdx = 0
      for ($j = 0; $j -lt $teamCount; $j++) {
        if ($j -eq $i) { continue }
        $allyLines += "    Ally$aiIdx=$j;"
        $aiIdx++
      }
      $allyBlocks.Add(@"
  [ALLYTEAM$i]
  {
$($allyLines -join "`r`n")
    StartRectLeft=$x;
    StartRectTop=$z;
    StartRectRight=$([string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", [Math]::Min(0.99, [double]$s.x + 0.08)));
    StartRectBottom=$([string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", [Math]::Min(0.99, [double]$s.z + 0.08)));
  }
"@) | Out-Null
      $teamBlocks.Add(@"
  [TEAM$i]
  {
    TeamLeader=0;
    AllyTeam=$i;
    Handicap=0;
    Side=$side;
    RGBColor=$rgb;
    StartPosX=0;
    StartPosZ=0;
  }
"@) | Out-Null
    } else {
      $allyBlocks.Add(@"
  [ALLYTEAM$i]
  {
    NumAllies=0;
    StartRectLeft=$x;
    StartRectTop=$z;
    StartRectRight=$x;
    StartRectBottom=$z;
  }
"@) | Out-Null
      $teamBlocks.Add(@"
  [TEAM$i]
  {
    TeamLeader=0;
    AllyTeam=$i;
    Handicap=0;
    Side=$side;
    RGBColor=$rgb;
    StartPosX=0;
    StartPosZ=0;
  }
"@) | Out-Null
    }

    $aiName = "$($grow.label)($side $($s.pocketId))"
    $aiShort = [string]$grow.aiShortName
    if ($aiShort -eq "BARb") {
      $prof = if ($grow.barbProfile) { [string]$grow.barbProfile } else { "medium" }
      $ver = if ($grow.version) { [string]$grow.version } else { "stable" }
      $aiBlocks.Add(@"
  [AI$i]
  {
    Name=$aiName;
    ShortName=BARb;
    Team=$i;
    Host=0;
    Version=$ver;
    [OPTIONS]
    {
      profile=$prof;
    }
  }
"@) | Out-Null
      $aiSummary.Add("$($s.pocketId):BARb/$prof/$side") | Out-Null
    } else {
      $aiBlocks.Add(@"
  [AI$i]
  {
    Name=$aiName;
    ShortName=SimpleAI;
    Team=$i;
    Host=0;
  }
"@) | Out-Null
      $aiSummary.Add("$($s.pocketId):SimpleAI/$side") | Out-Null
    }
  }

  $startScript = @"
[GAME]
{
  MapName=$mapName;
  GameType=$GameType;
  GameStartDelay=0;
  StartPosType=2;
  RecordDemo=0;
  MyPlayerName=VerdanceShellBake;
  IsHost=1;
  FixedRNGSeed=$([int]$recipe.fixedRngSeed);
  NumPlayers=1;
  NumUsers=$($teamCount + 1);
  HostIP=127.0.0.1;
  HostPort=0;
  NoHelperAIs=0;

  [MODOPTIONS]
  {
    deathmode=neverend;
    experimentallegionfaction=1;
    va_campaign=0;
    va_shell_bake=1;
    va_shell_bake_frames=$growFrames;
    va_shell_bake_mapid=$MapId;
    debugcommands=1:cheat;
  }

  [PLAYER0]
  {
    Name=VerdanceShellBake;
    Spectator=1;
    Team=0;
    Rank=0;
  }

$($allyBlocks -join "`r`n")
$($teamBlocks -join "`r`n")
$($aiBlocks -join "`r`n")
}
"@

  $parent = Split-Path -Parent $OutPath
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  Set-Content -Encoding ASCII -Path $OutPath -Value $startScript

  return [ordered]@{
    mapId = $MapId
    mapName = $mapName
    growFrames = $growFrames
    teamCount = $teamCount
    peacefulCoGrow = $peaceful
    recipeKind = if ($recipe.recipeKind) { [string]$recipe.recipeKind } else { "co_grow" }
    aiMix = @($aiSummary)
    startscript = $OutPath
    recipePath = $recipePath
    templateId = if ($recipe.templateId -and [string]$recipe.templateId -notmatch "placeholder") { [string]$recipe.templateId } else { "living_shell_v1" }
    simCommanders = "normal"
    occupationCommanders = "decoy"
  }
}

function Convert-InfologToRawDump {
  param(
    [string]$InfologPath,
    [string]$MapId,
    [string]$OutJsonPath,
    [string[]]$AiMix = @()
  )
  if (!(Test-Path $InfologPath)) { throw "Infolog not found: $InfologPath" }
  $lines = Get-Content -LiteralPath $InfologPath
  $unitLines = @($lines | Where-Object { $_ -match 'VA_SHELL_UNIT\s+' })
  $rawUnits = @()
  $mapSizeX = 0; $mapSizeZ = 0
  foreach ($line in $lines) {
    if ($line -match 'VA_SHELL_MAP\s+(\d+)\s+(\d+)') {
      $mapSizeX = [int]$Matches[1]; $mapSizeZ = [int]$Matches[2]
    }
  }
  foreach ($line in $unitLines) {
    if ($line -match 'VA_SHELL_UNIT\s+(\S+)\s+([\d\.\-]+)\s+([\d\.\-]+)\s+(\d+)') {
      $rawUnits += [ordered]@{
        unitDefName = $Matches[1]
        x = [double]$Matches[2]
        z = [double]$Matches[3]
        facing = [int]$Matches[4]
        mapSizeX = $mapSizeX
        mapSizeZ = $mapSizeZ
      }
    }
  }
  $rawObj = [ordered]@{
    schemaVersion = "verdance-shell-raw-dump/1.0"
    mapId = $MapId
    mapSizeX = $mapSizeX
    mapSizeZ = $mapSizeZ
    unitCount = $rawUnits.Count
    units = $rawUnits
    aiMix = @($AiMix)
    source = "cloud"
  }
  $parent = Split-Path -Parent $OutJsonPath
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  ($rawObj | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 -LiteralPath $OutJsonPath
  return [ordered]@{
    unitCount = $rawUnits.Count
    unitLineCount = $unitLines.Count
    rawDump = $OutJsonPath
    armed = ($lines | Where-Object { $_ -match 'VA_SHELL_BAKE_ARMED' }).Count -gt 0
    dumped = ($lines | Where-Object { $_ -match 'VA_SHELL_DUMP_BEGIN' }).Count -gt 0
  }
}
