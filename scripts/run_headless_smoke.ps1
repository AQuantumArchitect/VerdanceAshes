param(
  [string]$Workspace = "",
  [string]$MapName = "All That Simmers v1.1.1",
  [int]$TimeoutSeconds = 75
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

$config = Get-VerdanceConfig -Workspace $Workspace
$zoneMapDestination = Install-VerdanceZoneMap -Config $config
if ($zoneMapDestination) {
  Write-Host "Installed zone map to BAR: $zoneMapDestination"
}
$engineDir = Get-BAREngineDir -Config $config -EngineName "spring-headless.exe"
$engine = Join-Path $engineDir "spring-headless.exe"
if (!(Test-Path $engine)) { throw "spring-headless.exe not found at $engine" }
$gameType = if ($config.PSObject.Properties["gameType"] -and $config.gameType) { [string]$config.gameType } else { 'Verdance Ashes $VERSION' }

$runRoot = Join-Path $Workspace "headless_runs"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$scriptPath = Join-Path $runRoot "verdance_headless_$stamp.txt"

$startScript = @"
[GAME]
{
  MapName=$MapName;
  GameType=$gameType;
  GameStartDelay=0;
  StartPosType=0;
  RecordDemo=0;
  MyPlayerName=VerdanceHeadless;
  IsHost=1;
  FixedRNGSeed=1;
  NumPlayers=1;
  NumUsers=1;
  HostIP=127.0.0.1;
  HostPort=0;
  NoHelperAIs=0;

  [MODOPTIONS]
  {
    deathmode=neverend;
    experimentallegionfaction=1;
    va_campaign=1;
    va_headless_autostart=1;
    va_headless_fastwin=1;
    va_headless_quit=1;
    debugcommands=1:cheat|60:luarules vaheadless|300:quitforce;
  }

  [ALLYTEAM0]
  {
    NumAllies=0;
  }

  [TEAM0]
  {
    Side=Armada;
    Handicap=0;
    AllyTeam=0;
    TeamLeader=0;
  }

  [PLAYER0]
  {
    IsFromDemo=0;
    Name=VerdanceHeadless;
    Team=0;
    Spectator=0;
    Rank=0;
  }
}
"@

Set-Content -Encoding ASCII -Path $scriptPath -Value $startScript

$infolog = $config.infolog
if (Test-Path $infolog) {
  $backup = Join-Path $runRoot "infolog_before_headless_$stamp.txt"
  Copy-Item -Force $infolog $backup
}

Write-Host "Verdance headless smoke startscript:"
Write-Host $scriptPath
Write-Host "Running spring-headless..."

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $engine
$psi.WorkingDirectory = $config.barDataRoot
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $false
$psi.RedirectStandardError = $false
$psi.CreateNoWindow = $true
function Quote-ProcessArg([string]$Arg) {
  if ($Arg -match '[\s"]') { return '"' + ($Arg.Replace('"', '\"')) + '"' }
  return $Arg
}
$quotedArgs = @("--write-dir", $config.barDataRoot, "--only-local", $scriptPath) |
  ForEach-Object { Quote-ProcessArg ([string]$_) }
$psi.Arguments = $quotedArgs -join " "

$proc = [System.Diagnostics.Process]::new()
$proc.StartInfo = $psi
[void]$proc.Start()
if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
  try { $proc.Kill() } catch { }
  throw "spring-headless timed out after $TimeoutSeconds seconds. Check $infolog"
}

Write-Host "spring-headless exit code: $($proc.ExitCode)"
if ($proc.ExitCode -ne 0) {
  throw "spring-headless exited with code $($proc.ExitCode). Check $infolog"
}

& (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "extract_latest_result.ps1") -Workspace $Workspace

$result = Get-Content $config.resultInbox -Raw | ConvertFrom-Json
Write-Host "Verdance headless smoke result:"
Write-Host ($result | ConvertTo-Json -Depth 50 -Compress)

if ($result.status -ne "victory") {
  throw "Expected headless smoke status victory, got $($result.status)"
}

Write-Host "Verdance headless smoke passed."
