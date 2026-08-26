# Package a battle-farm shell bake (e.g. Koom 1v1 BARb hard_agg → T2 mid claim).
# Offline-safe: builds startscript + queue entry. Run via cloud or local headless later.
param(
  [string]$Workspace = "",
  [string]$RecipePath = "",
  [string]$MapId = "koom_valley",
  [string]$BundleName = ""
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "_common.ps1")
. (Join-Path $here "cloud\_cloud_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace

if (-not $RecipePath) {
  $RecipePath = Join-Path $Workspace "data\base_templates\$MapId\bake_recipe_t2_battle_1v1.json"
}
if (!(Test-Path $RecipePath)) { throw "Missing battle recipe: $RecipePath" }

$recipe = Get-Content -Raw -LiteralPath $RecipePath | ConvertFrom-Json
if ($recipe.mapId) { $MapId = [string]$recipe.mapId }
$templateId = if ($recipe.templateId) { [string]$recipe.templateId } else { "living_t2_mid_v1" }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
if (-not $BundleName) { $BundleName = "battle_farm_${MapId}_$stamp" }
$bundleRoot = Join-Path $Workspace "headless_runs\cloud\$BundleName"
$jobDir = Join-Path $bundleRoot "jobs\$MapId"
New-Item -ItemType Directory -Force -Path $jobDir | Out-Null

$gameType = if ($config.PSObject.Properties["gameType"] -and $config.gameType) { [string]$config.gameType } else { 'Verdance Ashes $VERSION' }
$scriptPath = Join-Path $jobDir "bake_startscript.txt"
$meta = New-ShellBakeStartscript -Workspace $Workspace -MapId $MapId -OutPath $scriptPath -GameType $gameType -RecipePath $RecipePath
($meta | ConvertTo-Json -Depth 6) | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $jobDir "job_meta.json")
Copy-Item -Force -LiteralPath $RecipePath -Destination (Join-Path $jobDir "bake_recipe.json")

$filterT2 = Join-Path $Workspace "data\base_templates\strip_filter_t2_battle.json"
$queue = [ordered]@{
  schemaVersion = "verdance-battle-farm-queue/1.0"
  bundleName = $BundleName
  notes = "Battle farm: normal coms in sim, T2 strip filter + decoy occupation after harvest."
  jobs = @(
    [ordered]@{
      mapId = $MapId
      mapName = $meta.mapName
      growFrames = $meta.growFrames
      teamCount = $meta.teamCount
      templateId = $templateId
      recipeKind = $meta.recipeKind
      peacefulCoGrow = $meta.peacefulCoGrow
      aiMix = $meta.aiMix
      startscriptRel = "jobs/$MapId/bake_startscript.txt"
      recipeRel = "jobs/$MapId/bake_recipe.json"
      stripFilter = "strip_filter_t2_battle.json"
      stripFilterPath = $filterT2
      timeoutSeconds = [Math]::Max(1800, [int]($meta.growFrames / 6) + 600)
      simCommanders = "normal"
      occupationCommanders = "decoy"
    }
  )
}
($queue | ConvertTo-Json -Depth 8) | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $bundleRoot "queue.json")
($queue | ConvertTo-Json -Depth 8) | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $Workspace "outbox\battle_farm_bundle.latest.json")

Write-Host "Battle farm package: $bundleRoot"
Write-Host "  AI mix: $($meta.aiMix -join ' | ')"
Write-Host "  frames=$($meta.growFrames) peaceful=$($meta.peacefulCoGrow) template=$templateId"
Write-Host "Next: cloud Invoke-CloudShellBake (or local bake) then:"
Write-Host "  apply_shell_strip.ps1 -RawDumpPath <dump> -MapId $MapId -TemplateId $templateId -RecipePath `"$RecipePath`" -FilterPath `"$filterT2`""
return $bundleRoot
