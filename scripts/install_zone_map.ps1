param([string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace")

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

$config = Get-VerdanceConfig -Workspace $Workspace
$destination = Install-VerdanceZoneMap -Config $config
Write-Host "Installed zone map to BAR: $destination"
