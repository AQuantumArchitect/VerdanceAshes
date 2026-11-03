-- Who owns a zone: the one rule, shared by every Verdance gadget (Python: verdance.world.claim).
--
-- Owner call (2026-10-29): presence is AV + DV, the metal in a side's armed units and armed
-- structures standing in the zone. A side owns the zone when
--     1500 < (AV+DV)self > 3 * SUM(AV+DV)others
-- and nobody meeting that changes nothing. Every zone the company owns is an extraction point.
-- The company and its allies in the match do not contest each other (M.holder).
local M = { NEED = 1500, DOMINANCE = 3 }

-- row: { faction = presence }; allies: the company's allies in the match, { faction = true }.
-- The company and its allies do not contest each other (owner call, 2026-11-02): the Null Mercs
-- compete against Armada but not against the player, and the player not against them. Neither
-- lends presence to the other. When the company and an ally both qualify, the company holds it.
-- Returns the owner (or nil) and its presence (or the best presence when nobody owns it).
function M.holder(row, need, dominance, allies)
  need = tonumber(need) or M.NEED
  if need <= 0 then need = M.NEED end
  dominance = tonumber(dominance) or M.DOMINANCE
  allies = allies or {}
  local function inBloc(f) return f == "ashwalkers" or allies[f] == true end
  local vals, best = {}, 0
  for faction, v in pairs(row or {}) do
    v = tonumber(v) or 0
    vals[faction] = v
    if v > best then best = v end
  end
  local leader, lv = nil, 0
  for f, v in pairs(vals) do
    local hostile = 0
    for g, w in pairs(vals) do
      if g ~= f and not (inBloc(f) and inBloc(g)) then hostile = hostile + w end
    end
    if v > need and v > dominance * hostile then
      if f == "ashwalkers" then return f, v end
      if v > lv or (v == lv and leader and tostring(f) < tostring(leader)) then leader, lv = f, v end
    end
  end
  if not leader then return nil, best end
  return leader, lv
end

-- Allies don't contest (owner-proxy call, 2026-11-02): a faction allied with the company in the
-- match (the Null Mercs, when they fight beside it) is left out of the company's "everyone else",
-- and does not count for the company either. Before this, mercs following the company into the
-- objective zone made the hold impossible (mission 1, 2026-11-02: need 3871 -> 27751).
-- allies: { faction = true }. Returns the row without them.
function M.withoutAllies(row, allies)
  if not allies or next(allies) == nil then return row end
  local out = {}
  for faction, v in pairs(row or {}) do
    if faction == "ashwalkers" or not allies[faction] then out[faction] = v end
  end
  return out
end

-- The company's: "ashwalkers" (the gadgets' name for the player team in a presence row).
function M.ours(row, need, dominance, allies)
  return M.holder(row, need, dominance, allies) == "ashwalkers"
end

return M
