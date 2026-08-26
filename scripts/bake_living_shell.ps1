param(
  [string]$Workspace = "",
  [string]$MapId = "greenest_fields",
  [switch]$SkipEngine,
  [switch]$PlaceholderOnly,
  # Headed GPU path: spring.exe renders IconsAtlas; headless often stalls at f~30.
  # Prefer this local path when cloud AWS is not configured; still free (no money seal).
  [switch]$Headed,
  [int]$TimeoutSeconds = 0,
  # 0 = recipe growFrames. Override for short smoke dumps (still real engine units).
  [int]$GrowFrames = 0
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$recipePath = Join-Path $Workspace "data\base_templates\$MapId\bake_recipe.json"
if (!(Test-Path $recipePath)) { throw "Missing bake recipe: $recipePath" }
$recipe = Get-Content -Raw -LiteralPath $recipePath | ConvertFrom-Json

# Always refresh placeholder so eco_raid has a dense shell without headed demos.
$gen = Join-Path $ScriptDir "generate_placeholder_shell.ps1"
& powershell -ExecutionPolicy Bypass -File $gen -Workspace $Workspace -MapId $MapId | Out-Host

if ($PlaceholderOnly) {
  Write-Host "PlaceholderOnly: skipped real AI bake."
  return
}

if ($SkipEngine) {
  Write-Host "SkipEngine: recipe + placeholder ready. Run without -SkipEngine when spring-headless is free."
  return
}

# Grow-profile catalog (SimpleAI sprawl vs BARb rates).
$growCatalog = @{}
$growCatalogPath = Join-Path $Workspace "data\base_templates\grow_profiles.json"
if (Test-Path $growCatalogPath) {
  $growDoc = Get-Content -Raw -LiteralPath $growCatalogPath | ConvertFrom-Json
  foreach ($prop in $growDoc.profiles.PSObject.Properties) {
    $growCatalog[$prop.Name] = $prop.Value
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

function Side-Rgb([string]$Side) {
  switch ($Side) {
    "Cortex" { return "1.0 0.2 0.16" }
    "Legion" { return "0.25 0.85 0.35" }
    default  { return "0.25 0.48 1.0" }
  }
}

$config = Get-VerdanceConfig -Workspace $Workspace
$engineName = if ($Headed) { "spring.exe" } else { "spring-headless.exe" }
$engineDir = Get-BAREngineDir -Config $config -EngineName $engineName
$engine = Join-Path $engineDir $engineName
if (!(Test-Path $engine)) { throw "$engineName not found at $engine" }

$gameType = if ($config.PSObject.Properties["gameType"] -and $config.gameType) { [string]$config.gameType } else { 'Verdance Ashes $VERSION' }
$mapName = if ($recipe.mapName) { [string]$recipe.mapName } else { throw "bake_recipe missing mapName" }
$growFrames = if ($recipe.growFrames) { [int]$recipe.growFrames } else { 27000 }
if ($GrowFrames -gt 0) { $growFrames = [int]$GrowFrames }
if ($TimeoutSeconds -le 0) {
  # Headless can crawl during atlas load; headed GPU is faster past IconsAtlas.
  # Allow ~1s wall per 8 sim frames + pad (headed gets a slightly tighter floor).
  $pad = if ($Headed) { 360 } else { 480 }
  $TimeoutSeconds = [Math]::Max(900, [int]($growFrames / 8) + $pad)
}
$computeLocus = if ($Headed) { "local_headed_gpu" } else { "local_headless" }
Write-Host "Bake locus: $computeLocus engine=$engineName"

$runRoot = Join-Path $Workspace "headless_runs"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = Join-Path $runRoot "shell_bake_${MapId}_$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$scriptPath = Join-Path $runDir "bake_startscript.txt"

$starts = @($recipe.starts)
$teamCount = [Math]::Min([int]$recipe.teamCount, $starts.Count)
if ($teamCount -lt 1) { throw "bake_recipe has no starts" }

# Peaceful co-grow: all AI share AllyTeam 0 so they expand without wiping each other.
$peaceful = $true
if ($null -ne $recipe.peacefulCoGrow) { $peaceful = [bool]$recipe.peacefulCoGrow }

$allyBlocks = New-Object System.Collections.Generic.List[string]
$teamBlocks = New-Object System.Collections.Generic.List[string]
$aiBlocks = New-Object System.Collections.Generic.List[string]
$aiSummary = New-Object System.Collections.Generic.List[string]

if ($peaceful) {
  $allyBlocks.Add(@"
  [ALLYTEAM0]
  {
    NumAllies=0;
  }
"@) | Out-Null
}

for ($i = 0; $i -lt $teamCount; $i++) {
  $s = $starts[$i]
  $x = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", [double]$s.x)
  $z = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", [double]$s.z)
  $grow = Resolve-StartGrowAI $s $recipe $growCatalog
  $side = [string]$grow.side
  $rgb = Side-Rgb $side
  $allyId = if ($peaceful) { 0 } else { $i }

  if (-not $peaceful) {
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
  }

  $teamBlocks.Add(@"
  [TEAM$i]
  {
    TeamLeader=0;
    AllyTeam=$allyId;
    Handicap=0;
    Side=$side;
    RGBColor=$rgb;
    StartPosX=0;
    StartPosZ=0;
  }
"@) | Out-Null

  # Start rects still pin each team when StartPosType=2.
  if ($peaceful) {
    # Encode start position via modoptions-less path: use separate ally start rects
    # only if engine requires them. For StartPosType=2, teams need ally start rects.
    # Re-add per-team allyteams with NumAllies all pointing to group? Simpler: one
    # allyteam but StartPosType=3 with fixed StartPos - keep StartPosType=2 with
    # multiple allyteams that are *allied* to each other.
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

# For peaceful co-grow with StartPosType=2, Spring needs start rects on allyteams.
# Use one allyteam per team but cross-ally so they do not fight.
if ($peaceful) {
  $allyBlocks = New-Object System.Collections.Generic.List[string]
  $teamBlocks = New-Object System.Collections.Generic.List[string]
  for ($i = 0; $i -lt $teamCount; $i++) {
    $s = $starts[$i]
    $x = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", [double]$s.x)
    $z = [string]::Format([System.Globalization.CultureInfo]::InvariantCulture, "{0:0.####}", [double]$s.z)
    $grow = Resolve-StartGrowAI $s $recipe $growCatalog
    $side = [string]$grow.side
    $rgb = Side-Rgb $side
    # Ally everyone else.
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
  }
}

# Spectator host player so AI teams own the field.
$startScript = @"
[GAME]
{
  MapName=$mapName;
  GameType=$gameType;
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

Set-Content -Encoding ASCII -Path $scriptPath -Value $startScript
($aiSummary -join "`n") | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $runDir "ai_mix.txt")

$infolog = $config.infolog
if (Test-Path $infolog) {
  Copy-Item -Force -LiteralPath $infolog -Destination (Join-Path $runDir "infolog.pre.txt")
}

Write-Host "Shell bake starting: map=$mapName teams=$teamCount frames=$growFrames timeout=${TimeoutSeconds}s"
Write-Host "AI mix: $($aiSummary -join ' | ')"
Write-Host "Startscript: $scriptPath"

# Match run_headless_smoke launch contract, but use an *isolated bake write-dir*
# with icons/UI stripped so headless does not hang forever on IconsAtlas at f=30.
# Headed GPU path still disables heavy UI chrome but keeps the real renderer
# (IconsAtlas FBO can complete on GPU where headless stalls atlasRendered=0).
$barDataRoot = if ($config.barDataRoot) { [string]$config.barDataRoot } else { Split-Path -Parent $engineDir }
$bakeWriteDir = Join-Path $runDir "write_dir"
New-Item -ItemType Directory -Force -Path $bakeWriteDir | Out-Null
# Point engine at real games/maps via junction-like copy of critical paths is heavy;
# instead use barDataRoot as write-dir and drop a local springsettings override.
$settingsPath = Join-Path $barDataRoot "springsettings.cfg"
$settingsBak = Join-Path $runDir "springsettings.pre_bake.cfg"
$didSettingsPatch = $false
if (Test-Path $settingsPath) {
  Copy-Item -Force -LiteralPath $settingsPath -Destination $settingsBak
  $settingsText = Get-Content -Raw -LiteralPath $settingsPath
  if ($Headed) {
    # Spring springsettings rejects free-text // comments — use key=value only + tag key.
    $patch = @"

VerdanceShellBakeHeaded = 1
UnitIconsAsUI = 0
UnitIconDist = 99999
MinimapIconScale = 0.1
LuaUI = 0
Fullscreen = 0
WindowBorderless = 0
XResolutionWindowed = 1280
YResolutionWindowed = 720
SplashScreenDir =
"@
    $patchTag = "VerdanceShellBakeHeaded"
  } else {
    $patch = @"

VerdanceShellBakeHeadless = 1
UnitIconsAsUI = 0
UnitIconDist = 99999
MinimapIconScale = 0.1
LuaUI = 0
SplashScreenDir =
"@
    $patchTag = "VerdanceShellBakeHeadless"
  }
  if ($settingsText -notmatch [regex]::Escape($patchTag)) {
    Set-Content -Encoding ASCII -Path $settingsPath -Value ($settingsText.TrimEnd() + "`r`n" + $patch)
    $didSettingsPatch = $true
  }
}

function Quote-ProcessArg([string]$Arg) {
  if ($Arg -match '[\s"]') { return '"' + ($Arg.Replace('"', '\"')) + '"' }
  return $Arg
}
# Prefer isolation so LuaUI state does not fight the main install.
$argLine = (@("--write-dir", $barDataRoot, "--isolation", "--only-local", $scriptPath) |
  ForEach-Object { Quote-ProcessArg ([string]$_) }) -join " "
Write-Host "Engine: $engine"
Write-Host "Args: $argLine"
$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $engine
$psi.WorkingDirectory = $barDataRoot
$psi.Arguments = $argLine
# Headed needs a real window/GPU context; headless stays silent.
$psi.UseShellExecute = $false
$psi.CreateNoWindow = (-not $Headed)
$proc = [System.Diagnostics.Process]::new()
$proc.StartInfo = $psi
[void]$proc.Start()
$ok = $proc.WaitForExit($TimeoutSeconds * 1000)
if (-not $ok) {
  try { $proc.Kill() } catch {}
  if ($didSettingsPatch -and (Test-Path $settingsBak)) {
    Copy-Item -Force -LiteralPath $settingsBak -Destination $settingsPath
  }
  throw "Shell bake timed out after ${TimeoutSeconds}s ($computeLocus). Partial logs in $runDir"
}
Write-Host "$engineName exit code: $($proc.ExitCode)"

if ($didSettingsPatch -and (Test-Path $settingsBak)) {
  Copy-Item -Force -LiteralPath $settingsBak -Destination $settingsPath
  Write-Host "Restored springsettings.cfg after bake."
}

# Isolation write-dir often owns the infolog.
$isoInfolog = Join-Path $barDataRoot "infolog.txt"
if (Test-Path $isoInfolog) {
  Copy-Item -Force -LiteralPath $isoInfolog -Destination (Join-Path $runDir "infolog.txt")
} elseif (Test-Path $infolog) {
  Copy-Item -Force -LiteralPath $infolog -Destination (Join-Path $runDir "infolog.txt")
}

$rawDump = Join-Path $runDir "shell_raw_units.json"
$lines = @()
if (Test-Path (Join-Path $runDir "infolog.txt")) {
  $lines = Get-Content -LiteralPath (Join-Path $runDir "infolog.txt")
}
$unitLines = @($lines | Where-Object { $_ -match 'VA_SHELL_UNIT\s+' })
if ($unitLines.Count -eq 0) {
  Write-Warning "No VA_SHELL_UNIT lines found. Bake gadget may not have run. Placeholder remains usable."
  $unitLines | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $runDir "shell_unit_lines.txt")
  return
}
$unitLines | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $runDir "shell_unit_lines.txt")

# Build a minimal JSON dump for apply_shell_strip.
$rawUnits = @()
$mapSizeX = 0; $mapSizeZ = 0
foreach ($line in $unitLines) {
  if ($line -match 'VA_SHELL_MAP\s+(\d+)\s+(\d+)') {
    $mapSizeX = [int]$Matches[1]; $mapSizeZ = [int]$Matches[2]
  }
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
  aiMix = @($aiSummary)
  computeLocus = $computeLocus
  engineName = $engineName
}
($rawObj | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 -LiteralPath $rawDump

$templateId = if ($recipe.templateId) { [string]$recipe.templateId } else { "armada_t15_v1" }
# Prefer a baked id that is not only "placeholder"
if ($templateId -match "placeholder") {
  $templateId = "living_shell_v1"
}
$strip = Join-Path $ScriptDir "apply_shell_strip.ps1"
$outPath = Join-Path $Workspace "data\base_templates\$MapId\$templateId.json"
& powershell -ExecutionPolicy Bypass -File $strip -Workspace $Workspace -RawDumpPath $rawDump -MapId $MapId -TemplateId $templateId -OutPath $outPath | Out-Host

# Stamp recipe character card so compiler/membrane see real bake status.
if (Test-Path $recipePath) {
  try {
    $recipeStamp = Get-Content -Raw -LiteralPath $recipePath | ConvertFrom-Json
    if ($recipeStamp.characterCard) {
      $cc = $recipeStamp.characterCard
      $cc | Add-Member -NotePropertyName source -NotePropertyValue "bake" -Force
      $cc | Add-Member -NotePropertyName realBakeStatus -NotePropertyValue "baked_$computeLocus" -Force
      $cc | Add-Member -NotePropertyName bakedAt -NotePropertyValue ((Get-Date).ToString("s")) -Force
      $cc | Add-Member -NotePropertyName templatePath -NotePropertyValue $outPath -Force
    }
    if ($recipeStamp.templateId -match "placeholder") {
      $recipeStamp.templateId = $templateId
    }
    ($recipeStamp | ConvertTo-Json -Depth 12) | Set-Content -Encoding UTF8 -LiteralPath $recipePath
  } catch {
    Write-Warning "Recipe stamp skipped: $_"
  }
}

$manifest = [ordered]@{
  ok = $true
  mapId = $MapId
  templateId = $templateId
  growFrames = $growFrames
  rawUnits = $rawUnits.Count
  aiMix = @($aiSummary)
  runDir = $runDir
  templatePath = $outPath
  computeLocus = $computeLocus
  engineName = $engineName
  generatedAt = (Get-Date).ToString("s")
}
($manifest | ConvertTo-Json -Depth 4) | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $runDir "bake_manifest.json")
Write-Host "Shell bake complete: $outPath"
return $outPath
