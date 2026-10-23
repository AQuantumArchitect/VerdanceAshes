# Runs the mission builder's enemy-base functions (pulled out of build_next_mission_v1.ps1 by
# PowerShell's own parser) against a campaign state and a base template, and prints what a drop
# would place. tests/test_company_you.py uses it for the vivarium rule.
param([string]$Script, [string]$StatePath, [string]$TemplatePath, [string]$Before = "", [string]$MapId = "greenest_fields")
$t=$null;$e=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile($Script,[ref]$t,[ref]$e)
$want=@("Get-ScarredZoneSet","Get-ScarSuppressSet","Get-DestroyedHighValuePockets","Build-LivingShellFromTemplate")
$fns=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]}, $true)
foreach($f in $fns){ Invoke-Expression $f.Extent.Text }
$state = Get-Content -Raw $StatePath | ConvertFrom-Json
$tpl = Get-Content -Raw $TemplatePath | ConvertFrom-Json
$sc = Get-ScarredZoneSet -State $state -MapId $MapId
$hv = Get-DestroyedHighValuePockets -State $state -MapId $MapId
$ss = Get-ScarSuppressSet -State $state -MapId $MapId
$total = @($tpl.units).Count
$p = Build-LivingShellFromTemplate -Template $tpl -TeamId 1 -PrimaryZoneId "GF_SE_PLATEAU" -PrimaryCenter @(0.8,0.8) -ScarredZones $sc -DestroyedHvPockets $hv -ScarSuppress $ss
$byZone=@{}
foreach($u in @($p.units)){ $z=[string]$u.zoneId; if(-not $z){$z="?"}; $byZone[$z]=1+[int]$byZone[$z] }
"$Before template units=$total kept=$(@($p.units).Count)"
"scar reasons: " + (($sc.Keys | Sort-Object | ForEach-Object { "$_=$($sc[$_].reason)" }) -join ", ")
"kept by zone: " + (($byZone.Keys | Sort-Object | ForEach-Object { "$_=$($byZone[$_])" }) -join ", ")
