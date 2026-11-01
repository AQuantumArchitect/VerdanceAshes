<#
  tools/release.ps1 - build ONE game from a clean, tagged commit and push it to itch.

  Usage (PowerShell, from anywhere):
    .\tools\release.ps1 -Channel windows            # build + push
    .\tools\release.ps1 -Channel windows -DryRun    # build only, no push
    .\tools\release.ps1 -Channel windows -AllowUntagged -DryRun   # test build

  Needs: butler on PATH, BUTLER_API_KEY in the environment (never printed),
  and the engine path below (or env GODOT4 / UNITY_EDITOR).
  Version = the git tag on HEAD (git tag v1.2.3). Settings live in RELEASE.md + the block below.
#>
param(
  [Parameter(Mandatory=$true)][string]$Channel,
  [switch]$DryRun,
  [switch]$AllowUntagged
)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
# Git from Windows PowerShell 5.1 under ErrorActionPreference Stop: a native command's stderr becomes a
# terminating error once it is redirected, so "git describe ... 2>$null" on an untagged HEAD, or any
# git that prints a warning (the build PC's "Empty last update token"), killed the script. Output
# is returned, stderr dropped, and $LASTEXITCODE says how git ended.
function Invoke-GitQuiet {
  $saved = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { & git @args 2>$null } finally { $ErrorActionPreference = $saved }
}


# ---- per-game config (keep in sync with RELEASE.md) -------------------------
$ItchTarget   = 'aquantumarchitect/verdances-ashwalkers'
$Channels = @{
  windows = @{ Kind='script'; Script='scripts/ship.ps1'; ScriptArgs=@('-SkipZip','-OutDir','export\dist\release'); BuiltDir='export/dist/release'; Out='build/release/windows' }
}
# -----------------------------------------------------------------------------

if (-not $Channels.ContainsKey($Channel)) { throw "Unknown channel '$Channel'. Known: $($Channels.Keys -join ', ')" }
$C = $Channels[$Channel]

Push-Location $Root
try {
  $dirty = Invoke-GitQuiet status --porcelain --untracked-files=no
  if ($dirty -and -not $AllowUntagged) { throw "Working tree has uncommitted changes. Commit first; releases ship only committed code." }
  $Version = Invoke-GitQuiet describe --tags --exact-match
  if (-not $Version) {
    if (-not $AllowUntagged) { throw "HEAD has no tag. Tag it first, e.g.: git tag v0.3.1" }
    $Version = (Invoke-GitQuiet describe --tags --always --dirty) + '-untagged'
  }
  $Out = Join-Path $Root $C.Out
  if (Test-Path $Out) { Remove-Item $Out -Recurse -Force }
  New-Item -ItemType Directory -Force $Out | Out-Null
  Write-Host "== $ItchTarget`:$Channel  version $Version  ->  $Out"

  switch ($C.Kind) {
    'godot' {
      $godot = if ($env:GODOT4) { $env:GODOT4 } else { $GodotExe }
      if (-not (Test-Path $godot)) { throw "Godot $GodotVersion not found at $godot (set env GODOT4)" }
      & $godot --headless --path $Root --import | Out-Null
      & $godot --headless --path $Root --export-release $C.Preset (Join-Path $Out $C.File)
      if ($LASTEXITCODE -ne 0) { throw "Godot export failed ($LASTEXITCODE)" }
    }
    'unity' {
      $unity = if ($env:UNITY_EDITOR) { $env:UNITY_EDITOR } else { $UnityExe }
      if (-not (Test-Path $unity)) { throw "Unity $UnityVersion not found at $unity (set env UNITY_EDITOR)" }
      $log = Join-Path $Root 'Logs\release-build.log'
      $p = Start-Process $unity -ArgumentList @('-batchmode','-quit','-projectPath',"`"$Root`"",'-executeMethod',$C.Method,'-logFile',"`"$log`"") -Wait -PassThru
      if ($p.ExitCode -ne 0) { throw "Unity build failed ($($p.ExitCode)); see $log" }
      Copy-Item (Join-Path $Root $C.BuiltDir '*') $Out -Recurse -Force
    }
    'static' {
      $src = Join-Path $Root $C.Source
      if ($C.Include) { foreach ($i in $C.Include) { Copy-Item (Join-Path $src $i) $Out -Recurse -Force } }
      else { Copy-Item (Join-Path $src '*') $Out -Recurse -Force }
    }
    'script' {
      & (Join-Path $Root $C.Script) @($C.ScriptArgs)
      if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "Build script failed ($LASTEXITCODE)" }
      Copy-Item (Join-Path $Root $C.BuiltDir '*') $Out -Recurse -Force
    }
    default { throw "Unknown kind $($C.Kind)" }
  }
  Set-Content -Path (Join-Path $Out 'VERSION.txt') -Value "$Version`n$(Invoke-GitQuiet rev-parse HEAD)"
  if ($C.Check -and -not (Test-Path (Join-Path $Out $C.Check))) { throw "Build output is missing $($C.Check)" }

  if ($DryRun) { Write-Host "DryRun: built $Out, not pushed."; return }
  if (-not $env:BUTLER_API_KEY) { throw "BUTLER_API_KEY is not set" }
  butler push $Out "$ItchTarget`:$Channel" --userversion $Version
  if ($LASTEXITCODE -ne 0) { throw "butler push failed" }
  Write-Host "Pushed $Version. Now download it from itch, play 2 minutes, then update 'Last verified build' in RELEASE.md."
} finally { Pop-Location }
