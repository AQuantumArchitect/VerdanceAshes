param(
  [string]$Workspace = "",
  [switch]$Copy,
  [switch]$Remove
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace

# Dev repo keeps the mod at <workspace>\mod\; the release package keeps it
# at the package root, next to the workspace folder.
$modSourceCandidates = @(
  (Join-Path $Workspace "mod\VerdanceAshes.sdd"),
  (Join-Path (Split-Path -Parent $Workspace) "VerdanceAshes.sdd")
)
$modSource = $modSourceCandidates | Where-Object { Test-Path (Join-Path $_ "modinfo.lua") } | Select-Object -First 1
if (-not $modSource) {
  throw "Mod source not found or missing modinfo.lua. Looked in: $($modSourceCandidates -join '; ')"
}
$modDest = $config.modSdd
$gamesDir = Split-Path -Parent $modDest
if (!(Test-Path $gamesDir)) { throw "BAR games directory not found: $gamesDir" }

if ($Remove) {
  if (Test-Path $modDest) {
    $item = Get-Item -LiteralPath $modDest -Force
    if ($item.LinkType) {
      # Junction/symlink: remove the link only, never the target contents.
      $item.Delete()
    } else {
      Remove-Item -Recurse -Force -LiteralPath $modDest
    }
    Write-Host "Removed $modDest"
  } else {
    Write-Host "Nothing installed at $modDest"
  }
  return
}

if (Test-Path $modDest) {
  $existing = Get-Item -LiteralPath $modDest -Force
  if ($existing.LinkType -eq "Junction" -and -not $Copy) {
    $target = $existing.Target
    if ($target -eq $modSource) {
      Write-Host "Junction already installed: $modDest -> $modSource"
      return
    }
    $existing.Delete()
  } elseif ($Copy) {
    if ($existing.LinkType) { $existing.Delete() }
    else { Remove-Item -Recurse -Force -LiteralPath $modDest }
  } else {
    # Plain directory in the way of a junction install
    Remove-Item -Recurse -Force -LiteralPath $modDest
  }
}

if ($Copy) {
  Copy-Item -Recurse -Force -LiteralPath $modSource -Destination $modDest
  Write-Host "Copied mod archive: $modSource -> $modDest"
} else {
  New-Item -ItemType Junction -Path $modDest -Target $modSource | Out-Null
  Write-Host "Installed junction: $modDest -> $modSource"
}
