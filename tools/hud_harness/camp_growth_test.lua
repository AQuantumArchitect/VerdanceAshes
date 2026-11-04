-- Run with Lua 5.4 from the workspace root. The camp grown while the company was away
-- (mission.campGrowth) stands round the home pad on buildable ground, two eco per laser tower,
-- and never on the pad itself.
local created, echoes, removed = {}, {}, false
Game = { mapSizeX = 8192, mapSizeZ = 8192 }
UnitDefNames = { legsolar = { id = 1 }, legwin = { id = 2 }, leglht = { id = 3 } }
local water = function(x, z) return x > 3000 end          -- east of x=3000 is sea: nothing builds there
Spring = {
  Echo = function(s) echoes[#echoes + 1] = s end,
  GetGroundHeight = function(x, z) return water(x, z) and -20 or 50 end,
  TestBuildOrder = function(defID, x, y, z)
    if water(x, z) then return 0 end
    for _, u in ipairs(created) do if (u.x - x) ^ 2 + (u.z - z) ^ 2 < 90 ^ 2 then return 0 end end
    return 2
  end,
  CreateUnit = function(defID, x, y, z, facing, team) created[#created + 1] = { def = defID, x = x, z = z, team = team }; return #created end,
}
VFS = { Include = function(path)
  if path:find("va_active") then return true end
  if path:find("va_current") then return { campGrowth = { count = 9 }, balance = { playerTeamID = 0 } } end
  if path:find("va_pad_current") then return { x = 0.25, z = 0.25 } end
end }
gadgetHandler = { IsSyncedCode = function() return true end, RemoveGadget = function() removed = true end }
gadget = {}
dofile("mod/VerdanceAshes.sdd/luarules/gadgets/game_verdance_camp_growth.lua")
gadget:Initialize()
gadget:GameFrame(10)
assert(#created == 0, "nothing before the field has spawned")
gadget:GameFrame(45)
assert(#created == 9, "all nine placed, got " .. #created)
local n = { 0, 0, 0 }
for _, u in ipairs(created) do
  n[u.def] = n[u.def] + 1
  local d = math.sqrt((u.x - 2048) ^ 2 + (u.z - 2048) ^ 2)
  assert(d >= 639, "the pad stays clear")
  assert(u.x <= 3000, "never in the sea")
  assert(u.team == 0, "the company's own")
end
assert(n[1] + n[2] == 6 and n[3] == 3, "two eco per laser tower")
assert(removed and echoes[#echoes]:find("placed=9/9", 1, true), echoes[#echoes])
print("ok: the camp grown while away stands round the pad on buildable ground")
