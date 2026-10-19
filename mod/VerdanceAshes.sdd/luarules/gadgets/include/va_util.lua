-- Tiny shared helpers for Verdance synced gadgets.

local M = {}

function M.truthy(v)
  if v == true or v == 1 then return true end
  if type(v) == "string" then
    v = v:lower()
    return v == "1" or v == "true" or v == "yes" or v == "on"
  end
  return false
end

function M.resolvePlayerTeam()
  local fromRules = tonumber((Spring.GetGameRulesParam("va_player_team")))
  if fromRules and Spring.GetTeamInfo(fromRules, false) then return fromRules end
  local opts = Spring.GetModOptions() or {}
  local fromOpt = tonumber(opts.va_player_team or opts.playerteam)
  if fromOpt and Spring.GetTeamInfo(fromOpt, false) then return fromOpt end
  return 0
end

function M.defName(udOrID)
  if type(udOrID) == "number" then
    local ud = UnitDefs and UnitDefs[udOrID]
    return string.lower(tostring((ud and ud.name) or ""))
  end
  return string.lower(tostring((udOrID and udOrID.name) or ""))
end

return M
