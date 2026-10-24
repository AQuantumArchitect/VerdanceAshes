# Runs the mission builder's set-piece functions (Add-StandingWar, Add-Kings, Add-WildDens; pulled
# out of build_next_mission_v1.ps1 by PowerShell's own parser) against an intent, and prints the
# teams, AIs, alliances and forces a drop would field, as JSON. tests/test_theaters.py uses it.
param([string]$Script, [string]$IntentPath, [switch]$MercsAllied)
$t = $null; $e = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$t, [ref]$e)
$fns = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $true)
foreach ($f in $fns) { Invoke-Expression $f.Extent.Text }
# the faction tables are top-level assignments
$tables = $ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and $n.Left.Extent.Text -in @('$FACTION', '$MERC') }, $false)
foreach ($a in $tables) { Invoke-Expression $a.Extent.Text }
$intent = Get-Content -Raw $IntentPath | ConvertFrom-Json
$mercsAllied = [bool]$MercsAllied
$maxHazard = 0.4
$script:nextTeam = 1; $script:nextAllyTeam = 1
$script:allyTeams = @(); $script:teams = @(); $script:ai = @(); $script:forces = @(); $script:alliances = @()
$script:baseRecipes = @{}; $script:wildTeamID = $null; $script:primaryEnemyTeamID = $null; $script:primaryEnemySide = $null
$script:kings = @()
$theater = $intent.theater
if ($theater -and [string]$theater.kind -eq "kings_showdown") { Add-Kings $theater }
elseif ($theater -and [string]$theater.kind -eq "standing_war") { Add-StandingWar $theater }
Add-WildDens
[ordered]@{
  teams = @($script:teams); ai = @($script:ai); alliances = @($script:alliances); forces = @($script:forces)
  recipes = $script:baseRecipes; kings = @($script:kings); primaryEnemyTeamID = $script:primaryEnemyTeamID
} | ConvertTo-Json -Depth 12 -Compress
