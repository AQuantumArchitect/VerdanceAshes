if not VFS.Include("LuaRules/Configs/va_active.lua") then return {} end -- plain BAR unless the hub launched this
-- The Queen's Nest: the one hive the raptor queen sleeps under. Kill it and she wakes (the other
-- hives can burn; raptor_spawner_defense.lua). Four times a roost's health, a bigger body (the
-- campaign gadget scales the model and its collision box), and the queen-nest widget paints it
-- and calls it out the first time the company sees it.
local ok, src = pcall(VFS.Include, "units/other/raptors/Structures/raptor_hive.lua")
local def = ok and type(src) == "table" and src.raptor_hive
if type(def) ~= "table" then return {} end
def.health = (tonumber(def.health) or 50000) * 4
def.collisionvolumescales = "134 240 134"
def.footprintx, def.footprintz = 9, 9
def.yardmap = string.rep("ooooooooo ", 9):sub(1, -2)
def.customparams = def.customparams or {}
def.customparams.i18nfromunit = "raptor_hive"
def.customparams.va_queen_nest = 1
return { va_queen_nest = def }
