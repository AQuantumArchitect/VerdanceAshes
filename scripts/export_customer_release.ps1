# DEPRECATED: use scripts\ship.ps1
param([string]$Workspace = "", [string]$Version = "", [string]$DestRoot = "", [switch]$SkipZip)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "DEPRECATED export_customer_release.ps1 -> ship.ps1" -ForegroundColor Yellow
$args = @{ Workspace = $Workspace }
if ($Version) { $args.Version = $Version }
if ($SkipZip) { $args.SkipZip = $true }
if ($DestRoot) { $args.InstallToMyGames = $true }
& (Join-Path $here "ship.ps1") @args
