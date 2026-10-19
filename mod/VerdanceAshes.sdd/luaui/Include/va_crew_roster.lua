-- UI mirror: Include synced roster SoT (do not fork hire/mentor tables here).
local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_crew_roster.lua")
if not ok or type(mod) ~= "table" then
  ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_crew_roster.lua")
end
if ok and type(mod) == "table" then
  return mod
end
Spring.Echo("VA_CREW_ROSTER_UI_LOAD_FAIL " .. tostring(mod))
return {
  HEROES = {},
  FACTORIES = {},
  MENTOR_PRODUCTS = {},
  SEAT_CAP = 3,
  isCore = function() return false end,
  get = function() return nil end,
  hireCost = function() return 999 end,
  hireKmCost = function() return 0 end,
  isMentor = function() return false end,
  mentorProducts = function() return nil end,
  defaultAutoPick = function() return {} end,
}
