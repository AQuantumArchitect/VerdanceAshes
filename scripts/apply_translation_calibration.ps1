param(
  [string]$Workspace = "",
  [int]$DensityDivisor = 0,
  [int]$AvDisparityDivisor = 0,
  [string]$CalibrationData = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

if ($CalibrationData) {
  if (!(Test-Path $CalibrationData)) { throw "CalibrationData not found: $CalibrationData" }
  $calib = Get-Content -Raw -LiteralPath $CalibrationData | ConvertFrom-Json
  if ($DensityDivisor -le 0 -and $calib.proposedTanhDivisor) {
    $DensityDivisor = [int]$calib.proposedTanhDivisor
  }
  if ($AvDisparityDivisor -le 0 -and $calib.proposedAvDisparityDivisor) {
    $AvDisparityDivisor = [int]$calib.proposedAvDisparityDivisor
  }
  if ($AvDisparityDivisor -le 0 -and $calib.stats -and $calib.stats.p50) {
    $AvDisparityDivisor = [math]::Max(500, [int]([double]$calib.stats.p50 / 2.0))
  }
}

if ($DensityDivisor -le 0) { throw "DensityDivisor must be provided or present in CalibrationData." }
if ($AvDisparityDivisor -le 0) { $AvDisparityDivisor = [math]::Max(500, [int]($DensityDivisor / 2)) }

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace
# The gadget source of truth is the workspace mod tree (junction-installed into BAR).
$gadgetPath = Join-Path $Workspace "mod\VerdanceAshes.sdd\luarules\gadgets\game_verdance_campaign.lua"
if (!(Test-Path $gadgetPath)) { throw "Verdance gadget not found: $gadgetPath" }

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = "$gadgetPath.verdance_calibration_bak_$stamp"
Copy-Item -Force -LiteralPath $gadgetPath -Destination $backup

$lua = Get-Content -Raw -LiteralPath $gadgetPath
$lua = $lua -replace 'matrix\[k\]\[k\] = math\.tanh\(\(z\.av \+ z\.bp \+ z\.dp\) / [0-9.]+\)', "matrix[k][k] = math.tanh((z.av + z.bp + z.dp) / $DensityDivisor.0)"
$lua = $lua -replace 'matrix\[i\]\[j\] = BASE_COUPLING \* \(1\.0 - math\.tanh\(math\.abs\(zones\[i\]\.av - zones\[j\]\.av\) / [0-9.]+\)\)', "matrix[i][j] = BASE_COUPLING * (1.0 - math.tanh(math.abs(zones[i].av - zones[j].av) / $AvDisparityDivisor.0))"

if ($lua -notmatch " / $DensityDivisor\.0\)") { throw "Failed to apply density divisor." }
if ($lua -notmatch " / $AvDisparityDivisor\.0\)\)") { throw "Failed to apply AV disparity divisor." }

Set-Content -Encoding ASCII -LiteralPath $gadgetPath -Value $lua

Write-Host "Applied Verdance translation calibration."
Write-Host "Backup: $backup"
Write-Host "Density divisor: $DensityDivisor"
Write-Host "AV disparity divisor: $AvDisparityDivisor"
