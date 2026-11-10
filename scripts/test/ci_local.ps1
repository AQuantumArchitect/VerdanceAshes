# Local CI: what .github/workflows/ci.yml does, on this PC, with the real Umwelt pin.
# GitHub Actions minutes are scarce, so this is the gate before every push to master.
#   scripts\test\ci.bat              hub tests + ship dry run
#   scripts\test\ci.bat -TestsOnly   hub tests only
# Needs export\venv and export\cache\umwelt (scripts\test\autopilot.bat makes both the first time).
param([switch]$TestsOnly)
$ErrorActionPreference = "Stop"
$ws = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ws
$py = Join-Path $ws "export\venv\Scripts\python.exe"
$umwelt = Join-Path $ws "export\cache\umwelt"
if (-not (Test-Path $py)) { throw "export\venv is missing: run scripts\test\autopilot.bat once (or py -3.12 -m venv export\venv; pip install numpy scipy playwright)" }
if (-not (Test-Path (Join-Path $umwelt ".git"))) { throw "export\cache\umwelt is missing: run scripts\test\autopilot.bat once (it clones Umwelt at the pin)" }

$pinJson = Get-Content -Raw "tools\umwelt_pin.json" | ConvertFrom-Json
$pin = $pinJson.commit
if ($pinJson.repo -match '@') { throw "tools\umwelt_pin.json repo must be a public URL with no token." }
$env:GIT_TERMINAL_PROMPT = "0"
# Public snapshot: no token, and not a fast-forward of a private cache.
git -C $umwelt remote set-url origin $pinJson.repo
git -c credential.helper= -c http.extraheader= -C $umwelt fetch -q origin "+refs/tags/$($pinJson.tag):refs/tags/$($pinJson.tag)"
if ($LASTEXITCODE -ne 0) { throw "Could not fetch $($pinJson.tag) from $($pinJson.repo) (public, no token)." }
git -C $umwelt checkout -q --detach $pin
if ($LASTEXITCODE -ne 0) { throw "Umwelt commit $pin is not in $($pinJson.repo)." }
$head = (git -C $umwelt rev-parse HEAD).Trim()
if ($head -ne $pin) { throw "Umwelt checkout is $head, tools\umwelt_pin.json pins $pin." }
$env:UMWELT_SRC = Join-Path $umwelt "src"

$results = [ordered]@{}
Write-Host "=== hub tests (Umwelt $($pin.Substring(0,7)))"
& $py tests\run_tests.py
$results["hub tests"] = $LASTEXITCODE

if (-not $TestsOnly) {
  Write-Host "=== ship dry run"
  & powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ship.ps1 -SkipPython -SkipZip
  $results["ship dry run"] = $LASTEXITCODE
  if ($LASTEXITCODE -eq 0) {
    $v = ((Get-Content -Raw VERSION).Trim() -split "[\r\n]+")[0].Trim()
    & $py tools\check_ship_dryrun_v1.py "export/dist/VerdanceAshes_v$v"
    $results["staged build check"] = $LASTEXITCODE
  }
}

Write-Host ""
Write-Host "=== local CI ($((git log --oneline -1).Trim()))"
$bad = 0
foreach ($k in $results.Keys) {
  $ok = $results[$k] -eq 0
  if (-not $ok) { $bad++ }
  Write-Host ("  {0,-20} {1}" -f $k, $(if ($ok) { "PASS" } else { "FAIL (exit $($results[$k]))" }))
}
exit $bad
