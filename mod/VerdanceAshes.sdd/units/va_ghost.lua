if not VFS.Include("LuaRules/Configs/va_active.lua") then return {} end -- plain BAR unless the hub launched this
-- The spy hero's Ghost: Armada's radar-invisible spy bot (armspy) as BAR ships it, that can also
-- capture. Cloaked, it walks up to an enemy unit and turns it; capturing is slow on big things
-- (capture time scales with the target's build time) and quick on small ones.
local ok, src = pcall(VFS.Include, "units/ArmBots/T2/armspy.lua")
local def = ok and type(src) == "table" and src.armspy
if type(def) ~= "table" then return {} end
def.cancapture = true
def.capturespeed = 150          -- three times its build power: a Pawn turns in a few seconds
def.customparams = def.customparams or {}
def.customparams.i18nfromunit = "armspy"
return { va_ghost = def }
