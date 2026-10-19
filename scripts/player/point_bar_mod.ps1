# Point BAR's VerdanceAshes.sdd junction at deployed (My Games) or workspace mod.
# Playtests must load deployed Lua; workspace edits stay invisible until SHIP/repoint.
param(
  [ValidateSet("Deployed", "Workspace", "Status")]
  [string]$Mode = "Status",
  [string]$Workspace = ""
)

$ErrorActionPreference = "Stop"
$PlayerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptsDir = Split-Path -Parent $PlayerDir
. (Join-Path $ScriptsDir "_common.ps1")

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
$config = Get-VerdanceConfig -Workspace $Workspace
$modDest = [string]$config.modSdd
$gamesDir = Split-Path -Parent $modDest
if (-not (Test-Path $gamesDir)) {
  throw "BAR games directory not found: $gamesDir"
}

$deployedMod = Join-Path $env:USERPROFILE "Documents\My Games\VerdanceAshes\mod\VerdanceAshes.sdd"
$workspaceMod = Join-Path $Workspace "mod\VerdanceAshes.sdd"

function Get-LinkTarget([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) { return $null }
  $item = Get-Item -LiteralPath $Path -Force
  if ($item.LinkType) {
    $t = $item.Target
    if ($t -is [array]) { return [string]$t[0] }
    return [string]$t
  }
  return $null
}

function Write-Status {
  $target = Get-LinkTarget $modDest
  $exists = Test-Path -LiteralPath $modDest
  $kind = "missing"
  if ($exists) {
    $item = Get-Item -LiteralPath $modDest -Force
    $kind = if ($item.LinkType) { $item.LinkType } else { "directory" }
  }
  Write-Host "BAR mod path:  $modDest"
  Write-Host "Kind:          $kind"
  Write-Host "Points at:     $(if ($target) { $target } else { '(n/a — plain dir or missing)' })"
  Write-Host "Deployed mod:  $deployedMod  $(if (Test-Path $deployedMod) { '[ok]' } else { '[missing]' })"
  Write-Host "Workspace mod: $workspaceMod $(if (Test-Path $workspaceMod) { '[ok]' } else { '[missing]' })"
  if ($target) {
    $normT = [IO.Path]::GetFullPath($target)
    $normD = if (Test-Path $deployedMod) { [IO.Path]::GetFullPath($deployedMod) } else { "" }
    $normW = if (Test-Path $workspaceMod) { [IO.Path]::GetFullPath($workspaceMod) } else { "" }
    if ($normD -and ($normT -eq $normD)) {
      Write-Host "Mode:          DEPLOYED (playtest truth)"
      return "Deployed"
    }
    if ($normW -and ($normT -eq $normW)) {
      Write-Host "Mode:          WORKSPACE (dev live-edit)"
      return "Workspace"
    }
    Write-Host "Mode:          CUSTOM"
    return "Custom"
  }
  Write-Host "Mode:          UNKNOWN"
  return "Unknown"
}

function Set-Junction([string]$Source) {
  if (-not (Test-Path (Join-Path $Source "modinfo.lua"))) {
    throw "Mod source missing modinfo.lua: $Source"
  }
  $sourceFull = (Resolve-Path -LiteralPath $Source).Path
  if (Test-Path -LiteralPath $modDest) {
    $existing = Get-Item -LiteralPath $modDest -Force
    if ($existing.LinkType) {
      $cur = Get-LinkTarget $modDest
      if ($cur) {
        $curFull = [IO.Path]::GetFullPath($cur)
        if ($curFull -eq $sourceFull) {
          Write-Host "Already pointed: $modDest -> $sourceFull"
          return
        }
      }
      $existing.Delete()
    } else {
      # Never delete a non-link directory's contents blindly if it looks like a full copy —
      # but BAR games slot must be a junction for this workflow.
      Remove-Item -Recurse -Force -LiteralPath $modDest
    }
  }
  New-Item -ItemType Junction -Path $modDest -Target $sourceFull | Out-Null
  Write-Host "Pointed BAR mod: $modDest -> $sourceFull"
}

switch ($Mode) {
  "Status" {
    $null = Write-Status
  }
  "Deployed" {
    if (-not (Test-Path $deployedMod)) {
      throw "Deployed mod missing. Run SHIP.bat -InstallToMyGames first: $deployedMod"
    }
    Set-Junction $deployedMod
    $null = Write-Status
  }
  "Workspace" {
    if (-not (Test-Path $workspaceMod)) {
      throw "Workspace mod missing: $workspaceMod"
    }
    Set-Junction $workspaceMod
    $null = Write-Status
  }
}
