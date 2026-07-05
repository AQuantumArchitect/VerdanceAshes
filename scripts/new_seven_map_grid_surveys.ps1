param(
  [string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace",
  [int]$GridSize = 8
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

function Add-OrSetProperty {
  param($Object, [string]$Name, $Value)
  if ($Object.PSObject.Properties[$Name]) {
    $Object.$Name = $Value
  } else {
    $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
  }
}

function New-GridZones {
  param([string]$MapId, [int]$GridSize)
  $zones = @()
  for ($row = 0; $row -lt $GridSize; $row++) {
    for ($col = 0; $col -lt $GridSize; $col++) {
      $xMin = $col / $GridSize
      $xMax = ($col + 1) / $GridSize
      $zMin = $row / $GridSize
      $zMax = ($row + 1) / $GridSize
      $tags = @("grid", "survey")
      if ($row -eq 0) { $tags += "north" }
      if ($row -eq ($GridSize - 1)) { $tags += "south" }
      if ($col -eq 0) { $tags += "west" }
      if ($col -eq ($GridSize - 1)) { $tags += "east" }
      if ($row -ge 2 -and $row -le 5 -and $col -ge 2 -and $col -le 5) { $tags += "center" }
      $zones += [ordered]@{
        zoneId = ("{0}_G{1:00}_{2:00}" -f $MapId.ToUpperInvariant(), $row, $col)
        label = ("Grid r{0} c{1}" -f $row, $col)
        role = "survey_cell"
        shape = "rect"
        bounds = [ordered]@{
          xMin = [math]::Round($xMin, 4)
          xMax = [math]::Round($xMax, 4)
          zMin = [math]::Round($zMin, 4)
          zMax = [math]::Round($zMax, 4)
        }
        tags = $tags
      }
    }
  }
  return $zones
}

function Get-EstimatedSize {
  param([string]$MapId)
  switch ($MapId) {
    "all_that_simmers" { return @{ x = 7168; z = 10240 } }
    "greenest_fields" { return @{ x = 8192; z = 8192 } }
    "koom_valley" { return @{ x = 12288; z = 8192 } }
    "tabula" { return @{ x = 8192; z = 7168 } }
    "ancient_bastion" { return @{ x = 16384; z = 8192 } }
    "the_rock_jungle" { return @{ x = 10240; z = 8192 } }
    "eye_of_horus" { return @{ x = 6144; z = 7168 } }
    default { return @{ x = 8192; z = 8192 } }
  }
}

function Get-SurveyLayout {
  param($Map)
  if ($Map.id -eq "all_that_simmers") {
    return [ordered]@{
      allyTeams = @(
        [ordered]@{ id = 0; startRect = @(0.02, 0.02, 0.48, 0.48) },
        [ordered]@{ id = 1; startRect = @(0.52, 0.02, 0.98, 0.48) },
        [ordered]@{ id = 2; startRect = @(0.52, 0.52, 0.98, 0.98) },
        [ordered]@{ id = 3; startRect = @(0.02, 0.52, 0.48, 0.98) },
        [ordered]@{ id = 4; startRect = @(0.36, 0.36, 0.64, 0.64) }
      )
      teams = @(
        [ordered]@{ id = 0; side = "Legion"; allyTeam = 0; base = @(0.14, 0.14); rgb = @(0.25, 0.85, 0.35); label = "Legion BARb Aggressive" },
        [ordered]@{ id = 1; side = "Armada"; allyTeam = 1; base = @(0.82, 0.14); rgb = @(0.25, 0.48, 1.0); label = "Armada SimpleAI Blue" },
        [ordered]@{ id = 2; side = "Cortex"; allyTeam = 2; base = @(0.82, 0.82); rgb = @(1.0, 0.20, 0.16); label = "Cortex SimpleAI Red" },
        [ordered]@{ id = 3; side = "Armada"; allyTeam = 3; base = @(0.14, 0.82); rgb = @(0.10, 0.75, 0.85); label = "Armada SimpleAI Teal" },
        [ordered]@{ id = 4; side = "Armada"; allyTeam = 4; base = @(0.50, 0.50); rgb = @(0.78, 0.14, 0.92); label = "RaptorsAI Center Proxy" }
      )
    }
  }

  $defenderSide = "Armada"
  if ($Map.id -eq "eye_of_horus" -or $Map.id -eq "greenest_fields") { $defenderSide = "Cortex" }
  return [ordered]@{
    allyTeams = @(
      [ordered]@{ id = 0; startRect = @(0.02, 0.02, 0.48, 0.48) },
      [ordered]@{ id = 1; startRect = @(0.52, 0.52, 0.98, 0.98) }
    )
    teams = @(
      [ordered]@{ id = 0; side = "Legion"; allyTeam = 0; base = @(0.16, 0.16); rgb = @(0.25, 0.85, 0.35); label = "Legion BARb Aggressive" },
      [ordered]@{ id = 1; side = $defenderSide; allyTeam = 1; base = @(0.84, 0.84); rgb = @(1.0, 0.20, 0.16); label = "$defenderSide SimpleAI Defender" }
    )
  }
}

function Get-SurveyAi {
  param($Map)
  if ($Map.id -eq "all_that_simmers") {
    return @(
      [ordered]@{ name = "BARbarIAn(Legion Aggressive)"; shortName = "BARb"; team = 0; version = "stable"; options = [ordered]@{ profile = "hard_aggressive" } },
      [ordered]@{ name = "SimpleAI(Armada Blue)"; shortName = "SimpleDefenderAI"; team = 1; version = "<not-versioned>" },
      [ordered]@{ name = "SimpleAI(Cortex Red)"; shortName = "SimpleDefenderAI"; team = 2; version = "<not-versioned>" },
      [ordered]@{ name = "SimpleAI(Armada Teal)"; shortName = "SimpleDefenderAI"; team = 3; version = "<not-versioned>" },
      [ordered]@{ name = "RaptorsDefenseAI(Center)"; shortName = "RaptorsAI"; team = 4; version = "<not-versioned>" }
    )
  }
  return @(
    [ordered]@{ name = "BARbarIAn(Legion Aggressive)"; shortName = "BARb"; team = 0; version = "stable"; options = [ordered]@{ profile = "hard_aggressive" } },
    [ordered]@{ name = "SimpleAI(Defender)"; shortName = "SimpleDefenderAI"; team = 1; version = "<not-versioned>" }
  )
}

function Find-MapArchive {
  param($Config, $Map)
  $mapsDir = Join-Path $Config.barDataRoot "maps"
  $exact = Join-Path $mapsDir ([string]$Map.archivePattern)
  if (Test-Path $exact) { return $exact }
  $stem = ([string]$Map.archivePattern) -replace '\.sd7$', ''
  $candidate = Get-ChildItem -LiteralPath $mapsDir -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "$stem*" -and $_.Name -like "*.sd7" } |
    Select-Object -First 1
  if ($candidate) { return $candidate.FullName }
  return $null
}

function Find-MinimapAsset {
  param($Config, $Map)
  $base = Join-Path $Config.barDataRoot "games\BYAR-Chobby.sdd\LuaMenu\configs\gameConfig\byar"
  $override = Join-Path $base ("minimapOverride\" + [string]$Map.minimapKey + ".jpg")
  if (Test-Path $override) { return $override }
  $thumb = Join-Path $base ("minimapThumbnail\" + [string]$Map.minimapKey + ".png")
  if (Test-Path $thumb) { return $thumb }
  return $null
}

function New-ContactSheet {
  param($Manifest, [string]$OutPath)
  Add-Type -AssemblyName System.Drawing
  $thumbW = 320
  $thumbH = 220
  $labelH = 40
  $cols = 2
  $rows = [math]::Ceiling(@($Manifest.maps).Count / $cols)
  $bmp = [System.Drawing.Bitmap]::new($thumbW * $cols, ($thumbH + $labelH) * $rows)
  $gfx = [System.Drawing.Graphics]::FromImage($bmp)
  $gfx.Clear([System.Drawing.Color]::FromArgb(245, 245, 245))
  $font = [System.Drawing.Font]::new("Segoe UI", 11)
  $smallFont = [System.Drawing.Font]::new("Segoe UI", 8)
  for ($i = 0; $i -lt @($Manifest.maps).Count; $i++) {
    $entry = $Manifest.maps[$i]
    $x = ($i % $cols) * $thumbW
    $y = [math]::Floor($i / $cols) * ($thumbH + $labelH)
    $gfx.FillRectangle([System.Drawing.Brushes]::White, $x, $y, $thumbW, $thumbH + $labelH)
    if ($entry.minimapAssetCopied -and (Test-Path $entry.minimapAssetCopied)) {
      $img = [System.Drawing.Image]::FromFile($entry.minimapAssetCopied)
      $scale = [math]::Min($thumbW / $img.Width, $thumbH / $img.Height)
      $dw = [int]($img.Width * $scale)
      $dh = [int]($img.Height * $scale)
      $dx = $x + [int](($thumbW - $dw) / 2)
      $dy = $y + [int](($thumbH - $dh) / 2)
      $gfx.DrawImage($img, $dx, $dy, $dw, $dh)
      $img.Dispose()
    }
    $gfx.DrawString($entry.title, $font, [System.Drawing.Brushes]::Black, $x + 8, $y + $thumbH + 2)
    $status = if ($entry.archivePresent) { "archive present" } else { "archive missing" }
    $gfx.DrawString($status, $smallFont, [System.Drawing.Brushes]::DimGray, $x + 8, $y + $thumbH + 22)
  }
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutPath) | Out-Null
  $bmp.Save($OutPath, [System.Drawing.Imaging.ImageFormat]::Png)
  $gfx.Dispose()
  $bmp.Dispose()
}

$config = Get-VerdanceConfig -Workspace $Workspace
$poolPath = Join-Path $Workspace "data\map_pool\seven_maps.json"
$pool = Get-Content -Raw -LiteralPath $poolPath | ConvertFrom-Json
$zoneDir = Join-Path $Workspace "data\zone_maps\generated"
$scenarioDir = Join-Path $Workspace "data\scenarios\generated"
$assetDir = Join-Path $Workspace "reports\map_surveys\assets"
New-Item -ItemType Directory -Force -Path $zoneDir, $scenarioDir, $assetDir | Out-Null

$manifestMaps = @()
foreach ($map in @($pool.maps)) {
  $size = Get-EstimatedSize $map.id
  $zoneMapPath = Join-Path $zoneDir ("{0}.grid{1}.zone_map.json" -f $map.id, $GridSize)
  $scenarioPath = Join-Path $scenarioDir ("{0}.grid_survey.json" -f $map.id)
  $archive = Find-MapArchive $config $map
  $minimap = Find-MinimapAsset $config $map
  $copiedMinimap = $null
  if ($minimap) {
    $ext = [System.IO.Path]::GetExtension($minimap)
    $copiedMinimap = Join-Path $assetDir ("{0}{1}" -f $map.id, $ext)
    Copy-Item -Force -LiteralPath $minimap -Destination $copiedMinimap
  }

  $zoneMap = [ordered]@{
    schemaVersion = "verdance-zone-map/0.1"
    mapId = $map.id
    mapName = $map.title
    coordinateSystem = "normalized_to_elmos"
    authoringStatus = "generated_grid_survey_instrument"
    notes = "Temporary $GridSize x $GridSize measurement grid. Use battle occupancy to derive human zone proposals; do not treat these cells as final authored zones."
    zones = New-GridZones $map.id $GridSize
  }
  Save-Json $zoneMap $zoneMapPath

  $layout = Get-SurveyLayout $map
  $scenario = [ordered]@{
    schemaVersion = "verdance-playable-scenario/0.1"
    map = [ordered]@{
      id = $map.id
      name = $map.mapName
      sizeX = $size.x
      sizeZ = $size.z
      sizeStatus = "measured_from_headless_engine"
    }
    zoneMapPath = ("data/zone_maps/generated/{0}.grid{1}.zone_map.json" -f $map.id, $GridSize)
    defaultVariant = "grid_survey"
    notes = "Grid survey scenario generated from the canonical Verdance seven-map pool."
    missionBase = [ordered]@{
      schemaVersion = "0.10-playable"
      campaignId = "verdance_ashes"
      missionNumber = 1000
      pathSignal = "SURVEY"
      title = ("Verdance Grid Survey: " + $map.title)
      zone = $map.title
      objective = [ordered]@{
        id = ($map.id + "_grid_survey")
        kind = "topology_survey"
        requiredFrames = 1800
        description = "Headless BAR-AI grid occupancy survey."
      }
      economy = [ordered]@{ metalIncome = 0; energyIncome = 0; buildPower = 0 }
      graph = [ordered]@{}
      reputation = [ordered]@{}
      companions = @()
    }
    baseRecipes = [ordered]@{}
    layout = $layout
    forces = @()
    variants = @(
      [ordered]@{
        id = "grid_survey"
        label = "Grid Survey"
        notes = $map.baseline
        ai = Get-SurveyAi $map
      }
    )
  }
  Save-Json $scenario $scenarioPath

  $manifestMaps += [ordered]@{
    id = $map.id
    title = $map.title
    mapName = $map.mapName
    archivePresent = [bool]$archive
    archivePath = $archive
    minimapAsset = $minimap
    minimapAssetCopied = $copiedMinimap
    zoneMapPath = $zoneMapPath
    scenarioPath = $scenarioPath
    estimatedSize = $size
    descriptor = $map.descriptor
    campaignForces = $map.campaignForces
  }
}

$manifest = [ordered]@{
  schemaVersion = "verdance-seven-map-grid-survey-manifest/0.1"
  generatedAt = (Get-Date).ToString("s")
  gridSize = $GridSize
  poolPath = $poolPath
  maps = $manifestMaps
}
$manifestPath = Join-Path $Workspace "reports\map_surveys\seven_map_grid_survey_manifest.json"
Save-Json $manifest $manifestPath

$contactSheetPath = Join-Path $Workspace "reports\map_surveys\seven_map_contact_sheet.png"
New-ContactSheet $manifest $contactSheetPath

Write-Host "Generated seven-map grid survey files."
Write-Host "Manifest: $manifestPath"
Write-Host "Contact sheet: $contactSheetPath"
