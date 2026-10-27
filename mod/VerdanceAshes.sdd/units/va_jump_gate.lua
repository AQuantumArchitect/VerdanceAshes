if not VFS.Include("LuaRules/Configs/va_active.lua") then return {} end -- plain BAR unless the hub launched this
-- The Spire Gate: the Rock Jungle's way out (finale C, the Spire Jump). Armada's Experimental Gantry
-- body (armshltx) as a structure that builds nothing: game_verdance_jump_gate.lua stands its frame
-- unfinished on the spires for the company to finish, powers it from four advanced fusions, and
-- ports the named heroes off the jungle while the raptors come for them.
local ok, src = pcall(VFS.Include, "units/ArmBuildings/LandFactories/armshltx.lua")
local def = ok and type(src) == "table" and src.armshltx
if type(def) ~= "table" then return {} end
def.builder = false
def.buildoptions = nil
def.workertime = nil
def.canbeassisted = true
def.health = 24000
def.energystorage = 20000
def.customparams = def.customparams or {}
def.customparams.i18nfromunit = "armshltx"
def.customparams.va_jump_gate = 1
def.customparams.unitgroup = "util"
return { va_jump_gate = def }
