# Headed GPU living-shell bake — unblocks IconsAtlas hang on local headless.
# Prefer AWS cloud for unattended multi-map; use this when GPU seat is free.
param(
  [string]$Workspace = "",
  [string]$MapId = "the_rock_jungle",
  [switch]$SkipEngine,
  [switch]$PlaceholderOnly,
  [int]$TimeoutSeconds = 0,
  [int]$GrowFrames = 0
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
# Do not use $args (automatic variable) — splat a dedicated list.
$invokeArgs = [System.Collections.Generic.List[string]]::new()
$invokeArgs.AddRange([string[]]@(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", (Join-Path $here "bake_living_shell.ps1"),
  "-Headed",
  "-MapId", $MapId
))
if ($Workspace) { $invokeArgs.AddRange([string[]]@("-Workspace", $Workspace)) }
if ($SkipEngine) { [void]$invokeArgs.Add("-SkipEngine") }
if ($PlaceholderOnly) { [void]$invokeArgs.Add("-PlaceholderOnly") }
if ($TimeoutSeconds -gt 0) { $invokeArgs.AddRange([string[]]@("-TimeoutSeconds", "$TimeoutSeconds")) }
if ($GrowFrames -gt 0) { $invokeArgs.AddRange([string[]]@("-GrowFrames", "$GrowFrames")) }

Write-Host "Headed GPU shell bake: map=$MapId (IconsAtlas path via spring.exe)"
& powershell @($invokeArgs.ToArray())
exit $LASTEXITCODE
