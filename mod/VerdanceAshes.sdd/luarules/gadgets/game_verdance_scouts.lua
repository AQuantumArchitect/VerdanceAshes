-- The Eye of Horus's Armada scouts (verdance.world.eye_story, mission.scoutParties): Simple AI teams in
-- the corners the company did not land in, each with the camp it built in five minutes (placed by the
-- mission builder). The engine's start commander is taken away ("no commander suits"), and at its
-- arrival time (0: already there) each party stands at its camp, then builds as its AI likes. On a
-- Cortex contract (hunt_scouts) the job is done once every party is in and no scout constructor lives.
function gadget:GetInfo()
  return {
    name = "Verdance Eye Scouts",
    desc = "Armada scout parties on the Eye of Horus; the hunt_scouts objective",
    author = "Verdance",
    layer = 0,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local parties, scoutTeams, isHunt
local SWEEP = { [3] = true, [8] = true, [30] = true, [90] = true }
local CHECK_EVERY = 90

function gadget:Initialize()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  parties = ok and type(data) == "table" and data.scoutParties or nil
  if type(parties) ~= "table" or #parties == 0 then
    gadgetHandler:RemoveGadget(self)
    return
  end
  local obj = data.objective or data.objectiveTarget or {}
  isHunt = tostring(obj.kind or data.objectiveKind or "") == "hunt_scouts"
  scoutTeams = {}
  for _, p in ipairs(parties) do
    if p.teamID then scoutTeams[tonumber(p.teamID)] = p end
  end
end

local function isCommander(ud)
  local cp = ud and ud.customParams or {}
  return cp.iscommander or cp.isdecoycommander
end

local function sweepCommanders()
  for teamID in pairs(scoutTeams) do
    for _, uid in ipairs(Spring.GetTeamUnits(teamID) or {}) do
      if isCommander(UnitDefs[Spring.GetUnitDefID(uid)]) then
        Spring.DestroyUnit(uid, false, true)
      end
    end
  end
end

local function arrive(p, mx, mz)
  local x, z = tonumber(p.x) or 0.5, tonumber(p.z) or 0.5
  if x <= 1.5 then x = x * mx end
  if z <= 1.5 then z = z * mz end
  local n = 0
  for _, u in ipairs(p.units or {}) do
    local def = u.unitDefName or u.def
    if def and UnitDefNames[def] then
      for i = 1, tonumber(u.count) or 1 do
        local a = (n * 2.39996)
        local ux, uz = x + math.cos(a) * (40 + 12 * n), z + math.sin(a) * (40 + 12 * n)
        local uid = Spring.CreateUnit(def, ux, Spring.GetGroundHeight(ux, uz), uz, 0, tonumber(p.teamID))
        if uid then
          Spring.SetUnitRulesParam(uid, "va_force_role", "scout_party", { public = true })
          n = n + 1
        end
      end
    end
  end
  p.arrived = true
  Spring.Echo("VA_EYE_SCOUTS_ARRIVE team=" .. tostring(p.teamID) .. " zone=" .. tostring(p.zoneId) .. " units=" .. n)
end

local function scoutsLeft()
  -- constructors: mobile builders (con bots, con vehicles, con aircraft), not factories or nano towers
  local builders = 0
  for teamID in pairs(scoutTeams) do
    for _, uid in ipairs(Spring.GetTeamUnits(teamID) or {}) do
      local ud = UnitDefs[Spring.GetUnitDefID(uid)]
      if ud and not isCommander(ud) and ud.isBuilder and ud.canMove and not ud.isBuilding then
        builders = builders + 1
      end
    end
  end
  return builders
end

function gadget:GameFrame(frame)
  if SWEEP[frame] then sweepCommanders() end
  local mx, mz = Game.mapSizeX, Game.mapSizeZ
  local allArrived = true
  for _, p in ipairs(parties) do
    if not p.arrived then
      if frame >= math.max(2, (tonumber(p.arriveSeconds) or 0) * 30) then arrive(p, mx, mz) else allArrived = false end
    end
  end
  if isHunt and allArrived and frame % CHECK_EVERY == 0 then
    local builders = scoutsLeft()
    Spring.SetGameRulesParam("va_scout_builders_left", builders, { public = true })
    if builders == 0 and GG.VA_ObjectiveComplete then
      Spring.Echo("VA_EYE_SCOUTS_STOPPED frame=" .. frame)
      GG.VA_ObjectiveComplete("scouts_stopped")
      gadgetHandler:RemoveGadget(self)
    end
  end
end
