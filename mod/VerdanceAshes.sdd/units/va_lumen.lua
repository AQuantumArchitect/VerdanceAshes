if not VFS.Include("LuaRules/Configs/va_active.lua") then return {} end -- plain BAR unless the hub launched this
-- Sister Lumen: Armada's T2 construction vehicle (armacv), as BAR ships it, building only
-- the Prude (armgmm) and the Pulsar (armanni). A unit type of her own, because BAR's build
-- menu reads a unit type's buildoptions; trimming one unit's commands does not reach it.
local ok, src = pcall(VFS.Include, "units/ArmVehicles/T2/armacv.lua")
local def = ok and type(src) == "table" and src.armacv
if type(def) ~= "table" then return {} end
def.buildoptions = { "armgmm", "armanni" }
def.customparams = def.customparams or {}
def.customparams.i18nfromunit = "armacv"
return { va_lumen = def }
