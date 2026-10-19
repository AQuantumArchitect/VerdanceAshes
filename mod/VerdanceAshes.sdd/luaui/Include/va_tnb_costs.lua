-- UI wrapper around shared Tnb stake formula (synced gate SoT).
-- Colors live here; costOf/dropOf come from luarules/gadgets/include/va_tnb_cost.lua.

local M = {}

local Shared = nil
do
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_tnb_cost.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_tnb_cost.lua")
  end
  if ok and type(mod) == "table" then Shared = mod end
end

M.BP_PER_TNB = (Shared and Shared.BP_PER_TNB) or 150
M.EXPLICIT = (Shared and Shared.EXPLICIT) or {}
M.STRUCTURE_NO_DROP = (Shared and Shared.STRUCTURE_NO_DROP) or {}

function M.costOf(unitDefID)
  if Shared and Shared.costOf then
    return Shared.costOf(unitDefID, { bpPerTnb = M.BP_PER_TNB, amountPerDecoy = 1 })
  end
  return 0
end

function M.dropOf(unitDefID)
  if Shared and Shared.dropOf then
    return Shared.dropOf(unitDefID, { bpPerTnb = M.BP_PER_TNB, amountPerDecoy = 1 })
  end
  return M.costOf(unitDefID)
end

-- Purple Tnb ink (matches objectives HUD).
M.COLOR = "\255\200\160\255"
M.COLOR_DISABLED = "\255\120\100\140"

return M
