# Create a dedicated SSH key for BAR cloud (AWS / any OpenSSH host).
# Does not overwrite an existing key unless -Force.
param(
  [string]$KeyPath = "$env:USERPROFILE\.ssh\verdance_bar_aws",
  [string]$Comment = "verdance-bar-aws",
  [switch]$Force
)

$ErrorActionPreference = "Stop"
$dir = Split-Path -Parent $KeyPath
if (!(Test-Path $dir)) {
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

$pub = "$KeyPath.pub"
if ((Test-Path $KeyPath) -and -not $Force) {
  Write-Host "Key already exists: $KeyPath"
  Write-Host "Public key:"
  Get-Content -LiteralPath $pub
  Write-Host ""
  Write-Host "Use -Force to regenerate (update EC2 authorized_keys if you do)."
  return
}

if (Test-Path $KeyPath) {
  Remove-Item -LiteralPath $KeyPath, $pub -Force -ErrorAction SilentlyContinue
}

& ssh-keygen -t ed25519 -f $KeyPath -N '""' -C $Comment
if ($LASTEXITCODE -ne 0) { throw "ssh-keygen failed ($LASTEXITCODE)" }

Write-Host ""
Write-Host "Private key: $KeyPath" -ForegroundColor Green
Write-Host "Public key:  $pub"
Write-Host ""
Write-Host "=== Paste this public key into EC2 OpenSSH authorized_keys ===" -ForegroundColor Cyan
Get-Content -LiteralPath $pub
Write-Host "================================================================"
Write-Host ""
Write-Host "cloud_config.json auth.privateKeyPath should be:"
Write-Host "  $KeyPath"
