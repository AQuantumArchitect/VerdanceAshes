if not VFS.Include("LuaRules/Configs/va_active.lua") then return {} end -- plain BAR unless the hub launched this
-- Mask's own Decoy Commander: the Verdance armdecom (units/armdecom_tenebrium.lua: captures, leaves a
-- scaled wreck, dies like a builder) plus one thing no other decoy has: a T1 Bot Lab (armlab).
-- A unit type of his own, because BAR's build menu reads a unit type's buildoptions and the occupation
-- shells plant ordinary armdecom eco nodes that must not raise labs.
local ok, src = pcall(VFS.Include, "units/armdecom_tenebrium.lua")
local def = ok and type(src) == "table" and src.armdecom
if type(def) ~= "table" then return {} end
local opts = {}
for _, name in ipairs(def.buildoptions or {}) do opts[#opts + 1] = name end
opts[#opts + 1] = "armlab"
def.buildoptions = opts
def.customparams = def.customparams or {}
def.customparams.i18nfromunit = "armdecom"
def.customparams.va_mask = "1"
return { va_mask = def }
