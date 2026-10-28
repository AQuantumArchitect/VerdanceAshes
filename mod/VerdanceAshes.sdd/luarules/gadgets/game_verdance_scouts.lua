-- The Eye of Horus's Armada scouts (verdance.world.eye_story, mission.scoutParties): Simple AI teams in
-- the corners the company did not land in, each with the camp it built in five minutes (placed by the
-- mission builder). The engine's start commander is taken away ("no commander suits"), and at its
-- arrival time (0: already there) each party stands at its camp, then builds as its AI likes. The job
-- itself is a capture of the corner (Python's as_territory_capture); this gadget only brings them in.
function gadget:GetInfo()
  return {
    name = "Verdance Eye Scouts",
    desc = "Armada scout parties on the Eye of Horus",
    author = "Verdance",
    layer = 0,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local parties, scoutTeams
local SWEEP = { [3] = true, [8] = true, [30] = true, [90] = true }

function gadget:Initialize()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  parties = ok and type(data) == "table" and data.scoutParties or nil
  if type(parties) ~= "table" or #parties == 0 then
    gadgetHandler:RemoveGadget(self)
    return
  end
  scoutTeams = {}
  for _, p in ipairs(parties) do
    if p.teamID then scoutTeams[tonumber(p.teamID)] = p end
  end
end

local COM = VFS.Include("luarules/gadgets/include/va_commanders.lua")
local function sweepCommanders()
  local teams = {}
  for teamID in pairs(scoutTeams) do teams[#teams + 1] = teamID end
  COM.sweep({ teams = teams, label = "eye_scouts" })
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

function gadget:GameFrame(frame)
  if SWEEP[frame] then sweepCommanders() end
  local mx, mz = Game.mapSizeX, Game.mapSizeZ
  for _, p in ipairs(parties) do
    if not p.arrived and frame >= math.max(2, (tonumber(p.arriveSeconds) or 0) * 30) then arrive(p, mx, mz) end
  end
end
