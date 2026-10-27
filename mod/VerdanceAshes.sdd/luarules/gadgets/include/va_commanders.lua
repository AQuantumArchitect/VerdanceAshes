-- va_commanders.lua: what a commander is, and taking commanders off the field. One definition for
-- every Verdance gadget (the campaign, the Eye's scouts, the suits, the kings) instead of one each.
--
--   local COM = VFS.Include("luarules/gadgets/include/va_commanders.lua")
--   COM.isCommander(unitDefIDOrUnitDef)   -> bool (decoy commanders are not commanders)
--   COM.sweep{ teams = {...} | nil, skipTeams = {[id]=true}, keep = 0, label = "why" } -> removed
--
-- sweep removes quietly (DestroyUnit reclaimed: no wreck, no blast). teams nil = every team but
-- Gaia; keep = how many to leave per team (oldest first in GetTeamUnits order).
local COM = {}

function COM.isCommander(defOrUD)
  local ud = defOrUD
  if type(defOrUD) == "number" then ud = UnitDefs[defOrUD] end
  if type(ud) ~= "table" then return false end
  local cp = ud.customParams or {}
  -- Decoy commanders (armdecom/cordecom/legdecom) look like coms but are occupation swarm farmers.
  if cp.isdecoycommander or cp.decoyfor then return false end
  if cp.iscommander or cp.isCommander or cp.commander then return true end
  local n = string.lower(tostring(ud.name or ud.humanName or ""))
  -- BAR chassis names: armcom*, corcom*, legcom* (avoid "combat"/"comms" false positives).
  if n:find("combat", 1, true) then return false end
  if n:find("decom", 1, true) or n:find("decoy", 1, true) or n == "dummycom" then return false end
  return (n:match("com$") or n:match("^armcom") or n:match("^corcom") or n:match("^legcom")) and true or false
end

function COM.sweep(opts)
  opts = opts or {}
  local gaia = Spring.GetGaiaTeamID and Spring.GetGaiaTeamID() or -1
  local teams = opts.teams or Spring.GetTeamList() or {}
  local skip = opts.skipTeams or {}
  local keep = tonumber(opts.keep) or 0
  local removed = 0
  for _, tid in ipairs(teams) do
    if tid ~= gaia and not skip[tid] then
      local kept = 0
      for _, uid in ipairs(Spring.GetTeamUnits(tid) or {}) do
        if COM.isCommander(Spring.GetUnitDefID(uid)) then
          if kept < keep then
            kept = kept + 1
          else
            Spring.DestroyUnit(uid, false, true)
            removed = removed + 1
          end
        end
      end
    end
  end
  if removed > 0 and opts.label then
    Spring.Echo("VA_COMMANDERS_SWEPT n=" .. removed .. " why=" .. tostring(opts.label))
  end
  return removed
end

return COM
