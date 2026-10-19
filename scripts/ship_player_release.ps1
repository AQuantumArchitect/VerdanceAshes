# DEPRECATED: use scripts\ship.ps1
param([string]$Workspace = "", [string]$Version = "", [string]$DestRoot = "", [switch]$SkipSetup, [switch]$SkipPython)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "DEPRECATED ship_player_release.ps1 -> ship.ps1" -ForegroundColor Yellow
$a = @{ Workspace = $Workspace }
if ($Version) { $a.Version = $Version }
if ($SkipPython) { $a.SkipPython = $true }
if ($DestRoot) { $a.InstallToMyGames = $true }
& (Join-Path $here "ship.ps1") @a
