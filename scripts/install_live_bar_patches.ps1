param([string]$Workspace = "$env:USERPROFILE\Documents\BAR_Verdance_Workspace")

$ErrorActionPreference = "Stop"
. (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "_common.ps1")

$config = Get-VerdanceConfig -Workspace $Workspace
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

function Backup-File {
  param([string]$Path)
  if (!(Test-Path $Path)) { throw "File not found: $Path" }
  $backup = "$Path.verdance_bak_$stamp"
  Copy-Item -Force -LiteralPath $Path -Destination $backup
  Write-Host "Backup: $backup"
}

function Save-Ascii {
  param([string]$Path, [string]$Text)
  Set-Content -Encoding ASCII -LiteralPath $Path -Value $Text
  Write-Host "Wrote: $Path"
}

$widgetPath = Join-Path $config.barSdd "luaui\Widgets\gui_verdance_campaign.lua"
$gadgetPath = Join-Path $config.barSdd "luarules\gadgets\game_verdance_campaign.lua"

Backup-File $widgetPath
Backup-File $gadgetPath

$widget = Get-Content -Raw -LiteralPath $widgetPath
$widget = $widget -replace 'local function if cmd == "vaexport" then send\("varesult"\) else send\(cmd\) end\s+Spring\.SendLuaRulesMsg\("VA_CMD:" \.\. cmd\)\s+end', @'
local function send(cmd)
  Spring.SendLuaRulesMsg("VA_CMD:" .. cmd)
end
'@
if ($widget -notmatch 'local function send\(cmd\)') {
  throw "Widget patch did not install send(cmd)."
}
Save-Ascii $widgetPath $widget

$gadget = Get-Content -Raw -LiteralPath $gadgetPath

if ($gadget -notmatch 'headlessAutoStart') {
  $gadget = $gadget -replace 'local lastProgressFrame = 0', @'
local lastProgressFrame = 0
local headlessAutoStart = false
local headlessFastWin = false
local headlessQuit = false
local headlessStarted = false
local headlessQuitFrame = nil
local playableSetupSpawned = false
'@
}

if ($gadget -notmatch 'playableSetupSpawned') {
  $gadget = $gadget -replace 'local headlessQuitFrame = nil', @'
local headlessQuitFrame = nil
local playableSetupSpawned = false
'@
}

if ($gadget -notmatch 'local function truthy') {
  $gadget = $gadget -replace 'local function clamp\(x, lo, hi\)\s+if x < lo then return lo end\s+if x > hi then return hi end\s+return x\s+end', @'
local function clamp(x, lo, hi)
  if x < lo then return lo end
  if x > hi then return hi end
  return x
end

local function truthy(v)
  if v == true or v == 1 then return true end
  if type(v) == "string" then
    v = v:lower()
    return v == "1" or v == "true" or v == "yes" or v == "enabled"
  end
  return false
end
'@
}

if ($gadget -notmatch 'finishHeadlessResult') {
  $gadget = $gadget -replace 'local function logResult\(\)\s+local json = resultJson\(\)\s+Spring\.Echo\("VA_RESULT_JSON_COMPACT " \.\. json\)\s+logJsonChunked\("VA_RESULT_JSON", json\)\s+echoStatus\(\)\s+end', @'
local function logResult()
  local json = resultJson()
  Spring.Echo("VA_RESULT_JSON_COMPACT " .. json)
  logJsonChunked("VA_RESULT_JSON", json)
  echoStatus()
end

local function finishHeadlessResult(outcome)
  local req = mission.objective and mission.objective.requiredFrames or 600
  status = outcome or "victory"
  holdFrames = req
  debugAutoProgress = 0
  Spring.SetGameRulesParam("va_hold_frames", holdFrames, { public = true })
  Spring.Echo("VA_HEADLESS_RESULT_READY mission=" .. tostring(mission.missionId) .. " status=" .. status)
  logResult()
  if headlessQuit then
    headlessQuitFrame = Spring.GetGameFrame() + 2
  end
end
'@
}

if ($gadget -notmatch 'va_headless_autostart') {
  $gadget = $gadget -replace 'function gadget:Initialize\(\)\s+mission = readMission\(\)\s+zoneMap = readZoneMap\(\)', @'
function gadget:Initialize()
  mission = readMission()
  zoneMap = readZoneMap()
  local modOptions = Spring.GetModOptions() or {}
  headlessAutoStart = truthy(modOptions.va_headless_autostart)
  headlessFastWin = not (modOptions.va_headless_fastwin == false or modOptions.va_headless_fastwin == 0 or modOptions.va_headless_fastwin == "0")
  headlessQuit = truthy(modOptions.va_headless_quit)
'@
  $gadget = $gadget -replace 'Spring\.Echo\("VA_BRIDGE_LOADED mission=" \.\. tostring\(mission\.missionId\) \.\. " schema=" \.\. tostring\(mission\.schemaVersion or "unknown"\)\)\s+if zoneMap then Spring\.Echo\("VA_ZONES_LOADED mapId=" \.\. tostring\(zoneMap\.mapId or "unknown"\) \.\. " count=" \.\. tostring\(zoneCount\(\)\)\) end', @'
  Spring.Echo("VA_BRIDGE_LOADED mission=" .. tostring(mission.missionId) .. " schema=" .. tostring(mission.schemaVersion or "unknown"))
  if headlessAutoStart then Spring.Echo("VA_HEADLESS_AUTOSTART enabled") end
  if zoneMap then Spring.Echo("VA_ZONES_LOADED mapId=" .. tostring(zoneMap.mapId or "unknown") .. " count=" .. tostring(zoneCount())) end
'@
}

$hasHeadlessGameFrame = $gadget -match 'function gadget:GameFrame\(frame\)\s+if headlessAutoStart and not headlessStarted and frame >= 1 then'
if (-not $hasHeadlessGameFrame) {
  $gadget = $gadget -replace 'function gadget:GameFrame\(frame\)\s+if status == "active" and debugAutoProgress == 1 and frame % 30 == 0 then', @'
function gadget:GameFrame(frame)
  if headlessAutoStart and not headlessStarted and frame >= 1 then
    headlessStarted = true
    startMission()
    if headlessFastWin then
      finishHeadlessResult("victory")
    end
  end

  if headlessQuitFrame and frame >= headlessQuitFrame then
    Spring.Echo("VA_HEADLESS_QUIT")
    Spring.SendCommands("quitforce")
    headlessQuitFrame = nil
  end

  if status == "active" and debugAutoProgress == 1 and frame % 30 == 0 then
'@
}

if ($gadget -notmatch 'function gadget:GameStart\(') {
  $gadget = $gadget -replace 'function gadget:GameFrame\(frame\)', @'
function gadget:GameStart()
  if headlessAutoStart and not headlessStarted then
    headlessStarted = true
    startMission()
    if headlessFastWin then
      finishHeadlessResult("victory")
    end
  end
end

function gadget:GameFrame(frame)
'@
}

if ($gadget -notmatch 'local function spawnPlayableSetup') {
  $gadget = $gadget -replace '(?s)local function spawnCompanions\(\).*?Spring\.Echo\("VA_SPAWN companions=" \.\. tostring\(#mission\.companions\)\)\s+end', @'
$0

local function spawnUnitSpec(spec, teamID, baseX, baseZ, groupX, groupZ)
  if type(spec) ~= "table" then return 0 end
  local defName = spec.unitDefName or spec.def or spec[1]
  if not defName or not UnitDefNames[defName] then
    Spring.Echo("VA_PLAYABLE_MISSING_UNIT " .. tostring(defName))
    return 0
  end
  local count = tonumber(spec.count or 1) or 1
  local spacing = tonumber(spec.spacing or 90) or 90
  local spawned = 0
  local dx = tonumber(spec.dx or spec.x or 0) or 0
  local dz = tonumber(spec.dz or spec.z or 0) or 0
  local facing = tonumber(spec.facing or 0) or 0
  for i = 1, count do
    local row = math.floor((i - 1) / 4)
    local col = (i - 1) % 4
    local x = baseX + groupX + dx + ((col - 1.5) * spacing)
    local z = baseZ + groupZ + dz + (row * spacing)
    local y = Spring.GetGroundHeight(x, z)
    local unitID = Spring.CreateUnit(defName, x, y, z, facing, teamID)
    if unitID then
      spawned = spawned + 1
      Spring.SetUnitRulesParam(unitID, "va_playable_proxy", 1, { public = true })
      if spec.patrolX and spec.patrolZ and CMD and CMD.FIGHT then
        local px = normalizedToElmos(spec.patrolX, Game.mapSizeX or 0)
        local pz = normalizedToElmos(spec.patrolZ, Game.mapSizeZ or 0)
        Spring.GiveOrderToUnit(unitID, CMD.FIGHT, { px, Spring.GetGroundHeight(px, pz), pz }, {})
      end
    end
  end
  return spawned
end

local function spawnPlayableSetup()
  if playableSetupSpawned then
    Spring.Echo("VA_PLAYABLE_SETUP already_spawned")
    return
  end
  local setup = mission and mission.playableSetup
  if not setup or setup.enabled == false then
    Spring.Echo("VA_PLAYABLE_SETUP none")
    return
  end
  playableSetupSpawned = true
  local forces = setup.forces or {}
  local totalSpawned = 0
  for _, force in ipairs(forces) do
    local teamID = tonumber(force.teamID or 0) or 0
    local base = force.base or {}
    local baseX = normalizedToElmos(base.x or 0.5, Game.mapSizeX or 0)
    local baseZ = normalizedToElmos(base.z or 0.5, Game.mapSizeZ or 0)
    local forceSpawned = 0
    for _, group in ipairs(force.groups or {}) do
      local groupX = tonumber(group.dx or group.x or 0) or 0
      local groupZ = tonumber(group.dz or group.z or 0) or 0
      for _, spec in ipairs(group.units or {}) do
        forceSpawned = forceSpawned + spawnUnitSpec(spec, teamID, baseX, baseZ, groupX, groupZ)
      end
    end
    totalSpawned = totalSpawned + forceSpawned
    Spring.Echo("VA_PLAYABLE_FORCE id=" .. tostring(force.id or "?") .. " team=" .. tostring(teamID) .. " units=" .. tostring(forceSpawned))
  end
  Spring.Echo("VA_PLAYABLE_SETUP spawned forces=" .. tostring(#forces) .. " units=" .. tostring(totalSpawned))
end
'@
}

if ($gadget -notmatch 'spawnPlayableSetup\(\)\s+if headlessAutoStart') {
  $gadget = $gadget -replace 'function gadget:GameStart\(\)\s+if headlessAutoStart', @'
function gadget:GameStart()
  spawnPlayableSetup()
  if headlessAutoStart
'@
}

if ($gadget -notmatch 'elseif cmd == "vaspawnlayout"') {
  $gadget = $gadget -replace 'elseif cmd == "vaspawn" then spawnCompanions\(\)', @'
elseif cmd == "vaspawn" then spawnCompanions()
  elseif cmd == "vaspawnlayout" then spawnPlayableSetup()
'@
}

if ($gadget -notmatch 'runVerdanceCommand') {
  $oldRecv = @'
function gadget:RecvLuaMsg(msg, playerID)
  if type(msg) ~= "string" or msg:sub(1, 7) ~= "VA_CMD:" then return end
  local cmd = msg:sub(8)
  if cmd == "vastart" then startMission()
  elseif cmd == "vastatus" then echoStatus()
  elseif cmd == "vaprogress" then progress(300)
  elseif cmd == "vaprogressbig" then progress(99999)
  elseif cmd == "vawin" then status = "victory"; debugAutoProgress = 0; logResult()
  elseif cmd == "vafail" then status = "defeat"; debugAutoProgress = 0; logResult()
  elseif cmd == "vapartial" then status = "partial"; debugAutoProgress = 0; logResult()
  elseif cmd == "vaspawn" then spawnCompanions()
  elseif cmd == "vazones" then echoZones()
  elseif cmd == "varesult" or cmd == "vaexport" then logResult()
  elseif cmd == "vareset" then status = "inactive"; holdFrames = 0; debugAutoProgress = 0; echoStatus()
  else Spring.Echo("VA_UNKNOWN_CMD " .. tostring(cmd)) end
end
'@
  $newRecv = @'
local function runVerdanceCommand(cmd)
  if cmd == "vastart" then startMission()
  elseif cmd == "vastatus" then echoStatus()
  elseif cmd == "vaprogress" then progress(300)
  elseif cmd == "vaprogressbig" then progress(99999)
  elseif cmd == "vawin" then status = "victory"; debugAutoProgress = 0; logResult()
  elseif cmd == "vafail" then status = "defeat"; debugAutoProgress = 0; logResult()
  elseif cmd == "vapartial" then status = "partial"; debugAutoProgress = 0; logResult()
  elseif cmd == "vaspawn" then spawnCompanions()
  elseif cmd == "vazones" then echoZones()
  elseif cmd == "varesult" or cmd == "vaexport" then logResult()
  elseif cmd == "vaheadless" then startMission(); finishHeadlessResult("victory")
  elseif cmd == "vareset" then status = "inactive"; holdFrames = 0; debugAutoProgress = 0; echoStatus()
  else return false end
  return true
end

function gadget:TextCommand(command)
  if type(command) ~= "string" then return false end
  local cmd = command:match("^(%S+)")
  if not cmd then return false end
  if runVerdanceCommand(cmd) then return true end
  return false
end

function gadget:RecvLuaMsg(msg, playerID)
  if type(msg) ~= "string" or msg:sub(1, 7) ~= "VA_CMD:" then return end
  local cmd = msg:sub(8)
  if not runVerdanceCommand(cmd) then
    Spring.Echo("VA_UNKNOWN_CMD " .. tostring(cmd))
  end
end
'@
  if (-not $gadget.Contains($oldRecv)) {
    throw "Could not find original RecvLuaMsg block."
  }
  $gadget = $gadget.Replace($oldRecv, $newRecv)
}

foreach ($required in @("headlessAutoStart", "truthy", "finishHeadlessResult", "VA_HEADLESS_QUIT", "runVerdanceCommand", "spawnPlayableSetup", "vaspawnlayout")) {
  if ($gadget -notmatch [regex]::Escape($required)) {
    throw "Gadget patch missing expected token: $required"
  }
}
if ($gadget -notmatch 'function gadget:GameFrame\(frame\)\s+if headlessAutoStart and not headlessStarted and frame >= 1 then') {
  throw "Gadget patch missing headless GameFrame block."
}

Save-Ascii $gadgetPath $gadget
Write-Host "Live BAR patches installed."
