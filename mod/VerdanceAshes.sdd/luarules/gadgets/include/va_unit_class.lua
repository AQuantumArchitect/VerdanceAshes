-- Shared unit classifiers (rez bot, decoy, commander). Behavior + Tnb + UI can Include.

local M = {}

local function nameOf(ud)
  return string.lower(tostring((ud and ud.name) or ""))
end

function M.isRezBot(ud)
  if not ud then return false end
  if ud.canResurrect then return true end
  local n = nameOf(ud)
  if n == "legrezbot" or n:find("rezbot", 1, true) or n:find("zagreus", 1, true) then
    return true
  end
  local cp = ud.customParams or {}
  return cp.canresurrect == "1" or cp.canresurrect == true
end

function M.isDecoyDef(ud)
  if not ud then return false end
  local cp = ud.customParams or {}
  if cp.isdecoycommander or cp.decoyfor then return true end
  local n = nameOf(ud)
  return n == "armdecom" or n == "cordecom" or n == "legdecom"
end

function M.isCommanderDef(ud)
  if not ud then return false end
  local cp = ud.customParams or {}
  if cp.iscommander == "1" or cp.iscommander == true or cp.isCommander then
    return true
  end
  local n = nameOf(ud)
  return n == "armcom" or n == "corcom" or n == "legcom"
end

function M.isCommanderOrDecoy(unitID, ud)
  if unitID and Spring.GetUnitRulesParam then
    local tag = Spring.GetUnitRulesParam(unitID, "va_decoy_node")
    if tag == 1 or tag == true or tag == "1" then return true end
    local role = Spring.GetUnitRulesParam(unitID, "va_force_role")
    if role == "decoy_farmer" or role == "autonomous_decoy_farmer" then return true end
  end
  if not ud and unitID and Spring.GetUnitDefID then
    local dID = Spring.GetUnitDefID(unitID)
    ud = dID and UnitDefs[dID]
  end
  if M.isDecoyDef(ud) or M.isCommanderDef(ud) then return true end
  return false
end

return M
