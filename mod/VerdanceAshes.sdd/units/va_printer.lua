if not VFS.Include("LuaRules/Configs/va_active.lua") then return {} end -- plain BAR unless the hub launched this
-- Sister Lumen's Printer: Cortex's T2 repair vehicle (corvac), which BAR keeps in its files but
-- ships with 1 build power. Ours works: 200 build power, so it actually keeps her patched.
local ok, src = pcall(VFS.Include, "units/CorVehicles/T2/corvac.lua")
local def = ok and type(src) == "table" and src.corvac
if type(def) ~= "table" then return {} end
def.workertime = 200
def.customparams = def.customparams or {}
def.customparams.i18nfromunit = "corvac"
return { va_printer = def }
