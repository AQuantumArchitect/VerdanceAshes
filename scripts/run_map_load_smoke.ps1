param(
  [string]$Workspace = "",
  [string]$MapName = "All That Simmers v1.1.1",
  [int]$TimeoutSeconds = 75
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")
$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

$config = Get-VerdanceConfig -Workspace $Workspace
$engineDir = Get-BAREngineDir -Config $config -EngineName "spring-headless.exe"
$engine = Join-Path $engineDir "spring-headless.exe"
if (!(Test-Path $engine)) { throw "spring-headless.exe not found at $engine" }
$gameType = if ($config.PSObject.Properties["gameType"] -and $config.gameType) { [string]$config.gameType } else { 'Verdance Ashes $VERSION' }

$runRoot = Join-Path $Workspace "headless_runs"
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$runDir = Join-Path $runRoot "map_smoke_$stamp"
New-Item -ItemType Directory -Force -Path $runDir | Out-Null
$scriptPath = Join-Path $runDir "load_smoke.txt"

$startScript = @"
[GAME]
{
  MapName=$MapName;
  GameType=$gameType;
  GameStartDelay=0;
  StartPosType=0;
  RecordDemo=0;
  MyPlayerName=VerdanceSmoke;
  IsHost=1;
  FixedRNGSeed=1;
  NumPlayers=1;
  NumUsers=1;
  HostIP=127.0.0.1;
  HostPort=0;
  NoHelperAIs=0;

  [MODOPTIONS]
  {
    debugcommands=30:quitforce;
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
    Name=VerdanceSmoke;
    Team=0;
    Spectator=0;
    Rank=0;
  }
}
"@

Set-Content -Encoding ASCII -Path $scriptPath -Value $startScript

$infolog = $config.infolog
if (Test-Path $infolog) {
  Copy-Item -Force $infolog (Join-Path $runDir "infolog_before.txt")
}

Write-Host "Running map smoke for: $MapName"
Write-Host "Startscript: $scriptPath"

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
$psi.Arguments = (@("--write-dir", $config.barDataRoot, "--only-local", $scriptPath) | ForEach-Object { Quote-ProcessArg ([string]$_) }) -join " "

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

$summary = [ordered]@{
  generatedAt = (Get-Date).ToString("s")
  mapName = $MapName
  timeoutSeconds = $TimeoutSeconds
  exitCode = $proc.ExitCode
  scriptPath = $scriptPath
  infolog = $infolog
}
$summaryPath = Join-Path $runDir "summary.json"
$summary | ConvertTo-Json -Depth 10 | Set-Content -Encoding UTF8 -Path $summaryPath
Write-Host "Map smoke passed."
Write-Host "Summary: $summaryPath"
