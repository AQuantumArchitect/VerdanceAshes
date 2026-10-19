-- Pure Tenebrium stake formula. Synced gate + UI build cards both Include this.
-- Combat (including T3 heavies) is free; only build-power / named stakes cost Tnb.

local M = {}

M.BP_PER_TNB = 150

-- Explicit stakes (including free = 0). Keep names lowercase UnitDef.name.
M.EXPLICIT = {
  armvp = 1, corvp = 1, legvp = 1,
  armnanotc = 1, cornanotc = 1, legnanotc = 1,
  -- Experimental foundries (build-power structures)
  armshltx = 7, armshltxuw = 7,
  corgant = 7, corgantuw = 7,
  leggant = 7, leggantuw = 7,
  legapt3 = 7,
}

-- Eco converters never drop a Tnb shard on death (even if costOf > 0).
M.STRUCTURE_NO_DROP = {
  armmakr = true, cormakr = true, legeconv = true,
  armmmkr = true, cormmkr = true, legadveconv = true,
  armmmkrt3 = true, cormmkrt3 = true,
}

local function unitDefName(ud)
  return string.lower(tostring((ud and ud.name) or ""))
end

function M.unitDefName(ud)
  return unitDefName(ud)
end

--- Stake charged at AllowUnitCreation / shown on build cards.
--- @param unitDefID number
--- @param opts table|nil { amountPerDecoy = number, bpPerTnb = number }
function M.costOf(unitDefID, opts)
  opts = opts or {}
  local ud = unitDefID and UnitDefs and UnitDefs[unitDefID]
  if not ud then return 0 end
  local n = unitDefName(ud)
  local cp = ud.customParams or {}

  -- Occupation decoy farmers: stake for the shard they leave.
  if cp.isdecoycommander or cp.decoyfor
      or n == "armdecom" or n == "cordecom" or n == "legdecom" then
    return tonumber(opts.amountPerDecoy) or 1
  end

  -- customParams override (mission / unitdef stamp)
  local stamped = tonumber(cp.va_tnb_cost or cp.tenebrium_cost or cp.tnb_cost)
  if stamped ~= nil then
    return math.max(0, math.floor(stamped))
  end

  -- Rez bots themselves never stake.
  if ud.canResurrect or n == "legrezbot" or n:find("rezbot", 1, true) or n:find("zagreus", 1, true) then
    return 0
  end

  if M.EXPLICIT[n] ~= nil then
    return M.EXPLICIT[n]
  end
  if n:find("shltx", 1, true) then return 7 end
  if n == "legapt3" or n:match("gant$") or n:match("gantuw$") then return 7 end

  -- Commandos / mando line: capture builders — always 1 even if BP is odd.
  if n:find("mando", 1, true) or n:find("commando", 1, true) then
    return 1
  end

  local bp = tonumber(ud.buildSpeed or 0) or 0
  if bp <= 0 then
    return 0
  end
  local per = tonumber(opts.bpPerTnb) or M.BP_PER_TNB
  if per <= 0 then per = M.BP_PER_TNB end
  return math.max(1, math.ceil(bp / per))
end

--- Shard amount on death; eco converters drop nothing.
function M.dropOf(unitDefID, opts)
  local ud = unitDefID and UnitDefs and UnitDefs[unitDefID]
  if not ud then return 0 end
  local n = unitDefName(ud)
  if M.STRUCTURE_NO_DROP[n] then return 0 end
  if n:find("mmkr", 1, true) or n:find("adveconv", 1, true) then return 0 end
  if n:find("makr", 1, true) or n == "legeconv" then return 0 end
  return M.costOf(unitDefID, opts)
end

return M
