# Quick SSH connectivity + remote directory check for BAR cloud host.
param(
  [string]$Workspace = ""
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsRoot = Split-Path -Parent $here
. (Join-Path $scriptsRoot "_common.ps1")
. (Join-Path $here "_cloud_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

$cfgPath = Join-Path $Workspace "data\cloud\cloud_config.json"
if (!(Test-Path $cfgPath)) {
  Write-Host "Missing data/cloud/cloud_config.json" -ForegroundColor Red
  Write-Host "Copy data/cloud/cloud_config.aws.template.json -> cloud_config.json and set host + privateKeyPath."
  exit 2
}

try {
  $cloud = Get-CloudConfig -Workspace $Workspace
} catch {
  Write-Host $_.Exception.Message -ForegroundColor Red
  exit 2
}

Write-Host "Config: $($cloud.user)@$($cloud.host):$($cloud.port)  os=$($cloud.remoteOs)" -ForegroundColor Cyan
if ($cloud.auth.privateKeyPath) {
  if (Test-Path $cloud.auth.privateKeyPath) {
    Write-Host "Key: $($cloud.auth.privateKeyPath) OK"
  } else {
    Write-Host "Key MISSING: $($cloud.auth.privateKeyPath)" -ForegroundColor Red
    exit 2
  }
}

Write-Host "=== SSH hostname ==="
try {
  $out = Invoke-RemoteSsh -CloudConfig $cloud -RemoteCommand "hostname" -Capture
  Write-Host ($out | Out-String)
} catch {
  Write-Host "SSH failed: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "Checks: instance Running, SG allows your IP:22, OpenSSH installed, key in administrators_authorized_keys."
  exit 1
}

Write-Host "=== Remote dirs ==="
$root = [string]$cloud.remoteRoot
$probe = "powershell -NoProfile -Command `"@('$root','$($cloud.remoteBarData)','$($cloud.remoteJobs)','$($cloud.remoteResults)') | ForEach-Object { if (Test-Path `$_) { \"OK `$_\" } else { \"MISSING `$_\" } }`""
try {
  $dirs = Invoke-RemoteSsh -CloudConfig $cloud -RemoteCommand $probe -Capture
  Write-Host ($dirs | Out-String)
} catch {
  Write-Host "Dir probe failed (SSH ok but remote command error): $($_.Exception.Message)" -ForegroundColor Yellow
}

Write-Host "=== SSH OK — next: Sync-CloudBarRuntime / Invoke-CloudShellBake ===" -ForegroundColor Green
exit 0
