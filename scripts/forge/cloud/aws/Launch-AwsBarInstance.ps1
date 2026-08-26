# Optional: launch the BAR Windows EC2 via AWS CLI (after account + key + aws configure).
# First-time operators may prefer the console; this encodes our recommended knobs.
param(
  [string]$Region = "us-east-1",
  [string]$InstanceType = "t3.xlarge",
  [string]$KeyName = "verdance-bar-aws",
  [string]$InstanceName = "verdance-bar-bake",
  [int]$VolumeGiB = 100,
  [string]$SecurityGroupName = "verdance-bar-ssh",
  [string]$LocalPublicKeyPath = "$env:USERPROFILE\.ssh\verdance_bar_aws.pub",
  [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
  throw "AWS CLI not found. Install: winget install -e --id Amazon.AWSCLI  then  aws configure"
}

Write-Host "Region=$Region InstanceType=$InstanceType KeyName=$KeyName" -ForegroundColor Cyan

# Resolve caller public IP for security group lock-down
$myIp = $null
try {
  $myIp = (Invoke-RestMethod -Uri "https://checkip.amazonaws.com" -TimeoutSec 15).Trim()
} catch {
  Write-Host "Could not auto-detect public IP; security group will need manual My-IP rules." -ForegroundColor Yellow
}

if ($WhatIf) {
  Write-Host "WhatIf: would launch Windows Server 2022 $InstanceType in $Region, SG $SecurityGroupName, ${VolumeGiB}GB, IP=$myIp"
  return
}

# Ensure key pair exists (import local pubkey if needed)
$keyExists = $false
try {
  aws ec2 describe-key-pairs --region $Region --key-names $KeyName 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) { $keyExists = $true }
} catch { $keyExists = $false }

if (-not $keyExists) {
  if (!(Test-Path $LocalPublicKeyPath)) {
    throw "Missing public key $LocalPublicKeyPath — run New-BarCloudSshKey.ps1 first."
  }
  Write-Host "Importing key pair $KeyName from $LocalPublicKeyPath"
  aws ec2 import-key-pair --region $Region --key-name $KeyName --public-key-material "fileb://$LocalPublicKeyPath"
  if ($LASTEXITCODE -ne 0) { throw "import-key-pair failed" }
}

# Security group
$vpcId = aws ec2 describe-vpcs --region $Region --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text
if (-not $vpcId -or $vpcId -eq "None") { throw "No default VPC in $Region — create a VPC or pick another region." }

$sgId = aws ec2 describe-security-groups --region $Region --filters "Name=group-name,Values=$SecurityGroupName" "Name=vpc-id,Values=$vpcId" --query "SecurityGroups[0].GroupId" --output text 2>$null
if (-not $sgId -or $sgId -eq "None") {
  Write-Host "Creating security group $SecurityGroupName"
  $sgId = aws ec2 create-security-group --region $Region --group-name $SecurityGroupName --description "Verdance BAR bake SSH/RDP" --vpc-id $vpcId --query GroupId --output text
}

if ($myIp) {
  $cidr = "$myIp/32"
  Write-Host "Authorizing SSH/RDP from $cidr"
  aws ec2 authorize-security-group-ingress --region $Region --group-id $sgId --protocol tcp --port 22 --cidr $cidr 2>$null
  aws ec2 authorize-security-group-ingress --region $Region --group-id $sgId --protocol tcp --port 3389 --cidr $cidr 2>$null
} else {
  Write-Host "WARNING: open console and restrict SG $sgId to your IP for 22 and 3389." -ForegroundColor Yellow
}

# Latest Windows Server 2022 English AMI (owner Amazon)
$ami = aws ec2 describe-images --region $Region --owners amazon `
  --filters "Name=name,Values=Windows_Server-2022-English-Full-Base-*" "Name=state,Values=available" `
  --query "sort_by(Images,&CreationDate)[-1].ImageId" --output text
if (-not $ami -or $ami -eq "None") { throw "Could not resolve Windows Server 2022 AMI in $Region" }
Write-Host "AMI: $ami"

$ud = @"
<powershell>
# Lightweight first-boot: enable OpenSSH Server; full bootstrap still recommended via Bootstrap-AwsBarHost.ps1
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 -ErrorAction SilentlyContinue
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path 'C:\verdance_cloud' | Out-Null
</powershell>
"@
$udPath = Join-Path $env:TEMP "verdance-bar-userdata.txt"
Set-Content -LiteralPath $udPath -Value $ud -Encoding ASCII

$blockDev = "DeviceName=/dev/sda1,Ebs={VolumeSize=$VolumeGiB,VolumeType=gp3,DeleteOnTermination=true}"

Write-Host "Launching instance..."
$iid = aws ec2 run-instances --region $Region `
  --image-id $ami `
  --instance-type $InstanceType `
  --key-name $KeyName `
  --security-group-ids $sgId `
  --block-device-mappings $blockDev `
  --user-data "file://$udPath" `
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$InstanceName},{Key=project,Value=verdance-bar}]" `
  --query "Instances[0].InstanceId" --output text

if ($LASTEXITCODE -ne 0 -or -not $iid) { throw "run-instances failed" }
Write-Host "InstanceId: $iid" -ForegroundColor Green

Write-Host "Waiting for running..."
aws ec2 wait instance-running --region $Region --instance-ids $iid
$ip = aws ec2 describe-instances --region $Region --instance-ids $iid --query "Reservations[0].Instances[0].PublicIpAddress" --output text
Write-Host "Public IP: $ip" -ForegroundColor Green
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Wait ~3-5 min for Windows + user-data OpenSSH."
Write-Host "  2. RDP once if needed: get Administrator password via EC2 console (decrypt with key pair)."
Write-Host "  3. Copy Bootstrap-AwsBarHost.ps1 and run elevated with your public key."
Write-Host "  4. Set data/cloud/cloud_config.json host=$ip"
Write-Host "  5. powershell -File scripts/cloud/Test-CloudSsh.ps1"
Write-Host ""
Write-Host "Stop when idle:  aws ec2 stop-instances --region $Region --instance-ids $iid"
Write-Host "Start later:     aws ec2 start-instances --region $Region --instance-ids $iid"

# Write a local pointer (not secrets)
$wsHint = "C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace\outbox\aws_bar_instance.latest.json"
$info = @{
  schemaVersion = "verdance-aws-instance/1.0"
  region = $Region
  instanceId = $iid
  instanceType = $InstanceType
  publicIp = $ip
  keyName = $KeyName
  securityGroupId = $sgId
  name = $InstanceName
  launchedAt = (Get-Date).ToString("o")
} | ConvertTo-Json
Set-Content -LiteralPath $wsHint -Value $info -Encoding UTF8
Write-Host "Wrote $wsHint"
