param(
  [string]$Workspace = "",
  [switch]$Copy,
  [switch]$Remove
)

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

$Workspace = Get-VerdanceWorkspaceRoot -Workspace $Workspace

function Resolve-InstalledBarGame([string]$BarDataRoot) {
  # $null when BAR is a developer checkout (games\BAR.sdd, whose name is 'Beyond All Reason $VERSION').
  # Otherwise the newest rapid 'Beyond All Reason test-N-hash' this machine has downloaded: rapid's
  # versions.gz names each package (tag,md5,deps,name) and packages\<md5>.sdp is there when installed.
  if (Test-Path (Join-Path $BarDataRoot "games\BAR.sdd\modinfo.lua")) { return $null }
  $best = $null; $bestN = -1
  $pkgDir = Join-Path $BarDataRoot "packages"
  foreach ($vg in @(Get-ChildItem (Join-Path $BarDataRoot "rapid") -Recurse -Filter "versions.gz" -ErrorAction SilentlyContinue |
                    Where-Object { $_.Directory.Name -eq "byar" })) {
    $fs = [System.IO.File]::OpenRead($vg.FullName)
    try {
      $gz = New-Object System.IO.Compression.GZipStream($fs, [System.IO.Compression.CompressionMode]::Decompress)
      $rd = New-Object System.IO.StreamReader($gz)
      while ($null -ne ($line = $rd.ReadLine())) {
        $f = $line.Split(",")
        if ($f.Count -lt 4) { continue }
        $name = $f[3]
        if ($name -notmatch '^Beyond All Reason test-(\d+)-') { continue }
        $n = [int]$Matches[1]
        if ($n -gt $bestN -and (Test-Path (Join-Path $pkgDir ($f[1] + ".sdp")))) { $best = $name; $bestN = $n }
      }
    } finally { $fs.Dispose() }
  }
  if (-not $best) {
    Write-Warning ("No installed Beyond All Reason found under " + $BarDataRoot + " (no games\BAR.sdd, no rapid package). " +
                   "Launch BAR once from its own launcher so it downloads the game, then run SETUP.bat again.")
  }
  return $best
}
$config = Get-VerdanceConfig -Workspace $Workspace

# Dev repo keeps the mod at <workspace>\mod\; the release package keeps it
# at the package root, next to the workspace folder.
$modSourceCandidates = @(
  (Join-Path $Workspace "mod\VerdanceAshes.sdd"),
  (Join-Path (Split-Path -Parent $Workspace) "VerdanceAshes.sdd")
)
$modSource = $modSourceCandidates | Where-Object { Test-Path (Join-Path $_ "modinfo.lua") } | Select-Object -First 1
if (-not $modSource) {
  throw "Mod source not found or missing modinfo.lua. Looked in: $($modSourceCandidates -join '; ')"
}
$modDest = $config.modSdd
$gamesDir = Split-Path -Parent $modDest
if (!(Test-Path $gamesDir)) { throw "BAR games directory not found: $gamesDir" }

if ($Remove) {
  if (Test-Path $modDest) {
    $item = Get-Item -LiteralPath $modDest -Force
    if ($item.LinkType) {
      # Junction/symlink: remove the link only, never the target contents.
      $item.Delete()
    } else {
      Remove-Item -Recurse -Force -LiteralPath $modDest
    }
    Write-Host "Removed $modDest"
  } else {
    Write-Host "Nothing installed at $modDest"
  }
  return
}

if (Test-Path $modDest) {
  $existing = Get-Item -LiteralPath $modDest -Force
  if ($existing.LinkType -eq "Junction" -and -not $Copy) {
    $target = $existing.Target
    if ($target -eq $modSource) {
      Write-Host "Junction already installed: $modDest -> $modSource"
      return
    }
    $existing.Delete()
  } elseif ($Copy) {
    if ($existing.LinkType) { $existing.Delete() }
    else { Remove-Item -Recurse -Force -LiteralPath $modDest }
  } else {
    # Plain directory in the way of a junction install
    Remove-Item -Recurse -Force -LiteralPath $modDest
  }
}

if ($Copy) {
  Copy-Item -Recurse -Force -LiteralPath $modSource -Destination $modDest
  Write-Host "Copied mod archive: $modSource -> $modDest"
  # The mutator depends on Beyond All Reason. modinfo.lua says 'Beyond All Reason $VERSION', which is
  # the name of a developer checkout (data\games\BAR.sdd) and of nothing else: a BAR installed from
  # beyondallreason.info gets the game through rapid, named e.g. 'Beyond All Reason test-31774-68ba3b1'.
  # So the installed copy is stamped with the BAR this machine actually has (every Drop re-runs this,
  # so a BAR update is picked up). The workspace's own modinfo.lua is never touched.
  $barGame = Resolve-InstalledBarGame -BarDataRoot (Split-Path -Parent $gamesDir)
  if ($barGame) {
    $modinfo = Join-Path $modDest "modinfo.lua"
    $text = [System.IO.File]::ReadAllText($modinfo)
    $stamped = $text.Replace("'Beyond All Reason `$VERSION'", "'" + $barGame + "'")
    [System.IO.File]::WriteAllText($modinfo, $stamped, (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "Mutator depends on: $barGame"
  } else {
    Write-Host "Mutator depends on: Beyond All Reason `$VERSION (developer checkout data\games\BAR.sdd)"
  }
} else {
  New-Item -ItemType Junction -Path $modDest -Target $modSource | Out-Null
  Write-Host "Installed junction: $modDest -> $modSource"
}
