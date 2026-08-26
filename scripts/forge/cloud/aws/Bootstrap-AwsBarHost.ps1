# Run ON the AWS Windows EC2 host as Administrator (RDP or first SSH).
# Prepares OpenSSH, firewall, and Verdance BAR remote directories.
#
# Optional:
#   -PublicKeyPath  path to a .pub file already on the box
#   -PublicKey      inline public key string
#   -InstallTailscale  install Tailscale for yurt mesh Phase 2

param(
  [string]$RemoteRoot = "C:\verdance_cloud",
  [string]$PublicKeyPath = "",
  [string]$PublicKey = "",
  [switch]$InstallTailscale
)

$ErrorActionPreference = "Stop"

function Assert-Admin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $p = New-Object Security.Principal.WindowsPrincipal($id)
  if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run this script in an elevated (Administrator) PowerShell."
  }
}

Assert-Admin
Write-Host "== Bootstrap AWS BAR host ==" -ForegroundColor Cyan
Write-Host "RemoteRoot: $RemoteRoot"

# --- Directories ---
$dirs = @(
  $RemoteRoot,
  (Join-Path $RemoteRoot "bar_data"),
  (Join-Path $RemoteRoot "bar_data\engine"),
  (Join-Path $RemoteRoot "bar_data\maps"),
  (Join-Path $RemoteRoot "bar_data\games"),
  (Join-Path $RemoteRoot "jobs"),
  (Join-Path $RemoteRoot "results"),
  (Join-Path $RemoteRoot "scripts")
)
foreach ($d in $dirs) {
  New-Item -ItemType Directory -Force -Path $d | Out-Null
}
Write-Host "Directories ready under $RemoteRoot"

# --- OpenSSH Server ---
Write-Host "== OpenSSH Server ==" -ForegroundColor Cyan
$cap = Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'
if ($cap -and $cap.State -ne 'Installed') {
  Write-Host "Installing OpenSSH.Server..."
  Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 | Out-Null
} else {
  Write-Host "OpenSSH.Server already present (or capability query skipped)."
  try {
    Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 -ErrorAction SilentlyContinue | Out-Null
  } catch {}
}

Start-Service sshd -ErrorAction SilentlyContinue
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd
Write-Host "sshd status: $((Get-Service sshd).Status)"

# Firewall
if (-not (Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -DisplayName "OpenSSH Server (sshd)" `
    -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
}
Write-Host "Firewall: SSH 22 allowed (still restrict at AWS security group to your IP)."

# --- Authorized keys for Administrators ---
# Windows OpenSSH: administrators use ProgramData path with restricted ACL.
$pubText = $PublicKey
if (-not $pubText -and $PublicKeyPath -and (Test-Path $PublicKeyPath)) {
  $pubText = (Get-Content -Raw -LiteralPath $PublicKeyPath).Trim()
}
if (-not $pubText) {
  Write-Host "No -PublicKey / -PublicKeyPath given." -ForegroundColor Yellow
  Write-Host "After copying your .pub to the box, re-run with -PublicKeyPath, or append manually to:"
  Write-Host "  C:\ProgramData\ssh\administrators_authorized_keys"
} else {
  $authKeys = "C:\ProgramData\ssh\administrators_authorized_keys"
  $existing = ""
  if (Test-Path $authKeys) { $existing = Get-Content -Raw -LiteralPath $authKeys }
  if ($existing -notlike "*$($pubText.Split(' ')[1])*") {
    Add-Content -LiteralPath $authKeys -Value $pubText
    Write-Host "Appended public key to $authKeys"
  } else {
    Write-Host "Public key already present in $authKeys"
  }
  # Required ACL for Windows OpenSSH admin keys
  icacls $authKeys /inheritance:r | Out-Null
  icacls $authKeys /grant "SYSTEM:(F)" | Out-Null
  icacls $authKeys /grant "BUILTIN\Administrators:(F)" | Out-Null
  Write-Host "ACL fixed on administrators_authorized_keys"
}

# Prefer pubkey auth
$sshdConfig = "C:\ProgramData\ssh\sshd_config"
if (Test-Path $sshdConfig) {
  $cfg = Get-Content -LiteralPath $sshdConfig
  $cfg = $cfg | ForEach-Object {
    if ($_ -match '^\s*#?\s*PubkeyAuthentication') { 'PubkeyAuthentication yes' }
    elseif ($_ -match '^\s*#?\s*PasswordAuthentication') { 'PasswordAuthentication yes' }
    else { $_ }
  }
  Set-Content -LiteralPath $sshdConfig -Value $cfg
  Restart-Service sshd
  Write-Host "sshd_config: PubkeyAuthentication yes (password still allowed for recovery)."
}

# Marker for local tooling
$marker = @{
  schemaVersion = "verdance-aws-bar-host/1.0"
  bootstrappedAt = (Get-Date).ToString("o")
  remoteRoot = $RemoteRoot
  computerName = $env:COMPUTERNAME
  os = [string](Get-CimInstance Win32_OperatingSystem).Caption
} | ConvertTo-Json
Set-Content -LiteralPath (Join-Path $RemoteRoot "host_bootstrap.json") -Value $marker -Encoding UTF8
Write-Host "Wrote $RemoteRoot\host_bootstrap.json"

if ($InstallTailscale) {
  Write-Host "== Tailscale (yurt mesh Phase 2) ==" -ForegroundColor Cyan
  winget install -e --id Tailscale.Tailscale --accept-source-agreements --accept-package-agreements
  Write-Host "Launch Tailscale and log into the same tailnet as Wargen (lukespooner4@)."
  Write-Host "Then register MagicDNS in yurt board/aws.toml."
}

Write-Host ""
Write-Host "== DONE ==" -ForegroundColor Green
Write-Host "From Wargen, set cloud_config.json host to this instance's public IPv4,"
Write-Host "privateKeyPath to your private key, user Administrator, then:"
Write-Host "  powershell -File scripts\cloud\Test-CloudSsh.ps1"
Write-Host "  powershell -File scripts\cloud\Invoke-CloudShellBake.ps1 -MapIds the_rock_jungle"
