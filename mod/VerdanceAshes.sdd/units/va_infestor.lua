if not VFS.Include("LuaRules/Configs/va_active.lua") then return {} end -- plain BAR unless the hub launched this
-- The Infestor Hive's own Infestor: BAR's leginfestor, which only ever prints more of itself, plus the
-- Goblin (leggob) (owner, 2026-10-26). It prints its own kind (va_infestor), so a hive grown in the field
-- prints Goblins too. A unit type of its own, because BAR's build menu reads a unit type's buildoptions.
local ok, src = pcall(VFS.Include, "units/Legion/Bots/T2 Bots/leginfestor.lua")
local def = ok and type(src) == "table" and src.leginfestor
if type(def) ~= "table" then return {} end
def.buildoptions = { "va_infestor", "leggob" }
def.customparams = def.customparams or {}
def.customparams.i18nfromunit = "leginfestor"
def.customparams.va_infestor = "1"
return { va_infestor = def }
