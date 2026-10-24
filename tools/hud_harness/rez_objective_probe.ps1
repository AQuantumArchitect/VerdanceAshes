# Runs the mission builder's Get-RezObjective (pulled out of build_next_mission_v1.ps1 by
# PowerShell's own parser) on recruits + wound zones from a JSON file; prints the pick's heroId.
param([string]$Script, [string]$CasePath)
$t = $null; $e = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$t, [ref]$e)
$f = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq "Get-RezObjective" }, $true)
Invoke-Expression $f.Extent.Text
$case = Get-Content -Raw $CasePath | ConvertFrom-Json
$pick = Get-RezObjective @($case.recruits) @($case.wound)
[ordered]@{ heroId = $(if ($pick) { [string]$pick.heroId } else { $null }) } | ConvertTo-Json -Compress
