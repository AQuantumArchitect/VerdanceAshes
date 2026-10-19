-- UI mirror: Include synced strategic links SoT (generated data lives under luarules).
local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_strategic_links.lua")
if not ok or type(mod) ~= "table" then
  ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_strategic_links.lua")
end
if ok and type(mod) == "table" then
  return mod
end
return {}
