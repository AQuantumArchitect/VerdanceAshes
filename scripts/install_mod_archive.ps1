param(
  [string]$Workspace = "",
  [switch]$Copy,
  [switch]$Remove
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace

$modSource = Join-Path $Workspace "mod\VerdanceAshes.sdd"
if (!(Test-Path (Join-Path $modSource "modinfo.lua"))) {
  throw "Mod source not found or missing modinfo.lua: $modSource"
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
