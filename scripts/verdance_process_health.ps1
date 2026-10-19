param(
  [string]$Workspace = "",
  [switch]$StopSpring,
  [switch]$StopConsoles,
  [switch]$StopAllVerdance
)

$ErrorActionPreference = "Stop"
if (-not $Workspace) { $Workspace = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path) }

function Get-MatchingProcesses {
  $escapedWorkspace = [regex]::Escape($Workspace)
  Get-CimInstance Win32_Process |
    Where-Object {
      $_.Name -match '^(powershell|powershell_ise|pwsh|spring|spring-headless|BAR|recoil).*\.exe$' -or
      $_.CommandLine -match 'verdance|BAR_Verdance|spring-headless|recoil'
    } |
    ForEach-Object {
      $kind = "other"
      if ($_.Name -match 'spring|recoil|BAR') { $kind = "spring" }
      elseif ($_.CommandLine -match 'verdance_console_server\.ps1|LAUNCH_VERDANCE_CONSOLE|/api/status|127\.0\.0\.1:8765') { $kind = "verdance_console" }
      elseif ($_.CommandLine -match $escapedWorkspace) { $kind = "workspace_powershell" }
      [pscustomobject]@{
        pid = $_.ProcessId
        name = $_.Name
        kind = $kind
        commandLine = $_.CommandLine
      }
    } |
    Sort-Object kind, pid
}

$processes = @(Get-MatchingProcesses)
$toStop = @()
if ($StopAllVerdance) {
  $toStop = @($processes | Where-Object { $_.kind -in @("spring", "verdance_console") })
} else {
  if ($StopSpring) { $toStop += @($processes | Where-Object { $_.kind -eq "spring" }) }
  if ($StopConsoles) { $toStop += @($processes | Where-Object { $_.kind -eq "verdance_console" }) }
}

foreach ($proc in @($toStop | Sort-Object pid -Unique)) {
  try {
    Stop-Process -Id $proc.pid -Force -ErrorAction Stop
    $proc | Add-Member -NotePropertyName stopped -NotePropertyValue $true -Force
  } catch {
    $proc | Add-Member -NotePropertyName stopped -NotePropertyValue $false -Force
    $proc | Add-Member -NotePropertyName stopError -NotePropertyValue $_.Exception.Message -Force
  }
}

$result = [ordered]@{
  ok = $true
  generatedAt = (Get-Date).ToString("s")
  workspace = $Workspace
  stoppedCount = @($toStop).Count
  processes = $processes
}

$result | ConvertTo-Json -Depth 8
