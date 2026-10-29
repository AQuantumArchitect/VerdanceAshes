-- Who owns a zone: the one rule, shared by every Verdance gadget (Python: verdance.world.claim).
--
-- Owner call (2026-10-29): presence is AV + DV, the metal in a side's armed units and armed
-- structures standing in the zone. A side owns the zone when
--     1500 < (AV+DV)self > 3 * SUM(AV+DV)others
-- and nobody meeting that changes nothing. Every zone the company owns is an extraction point.
local M = { NEED = 1500, DOMINANCE = 3 }

-- row: { faction = presence }. Returns the owner (or nil) and the leader's presence.
function M.holder(row, need, dominance)
  need = tonumber(need) or M.NEED
  if need <= 0 then need = M.NEED end
  dominance = tonumber(dominance) or M.DOMINANCE
  local leader, best, total = nil, 0, 0
  for faction, v in pairs(row or {}) do
    v = tonumber(v) or 0
    total = total + v
    if v > best or (v == best and leader and tostring(faction) < tostring(leader)) then leader, best = faction, v end
  end
  if not leader or best <= need or best <= dominance * (total - best) then return nil, best end
  return leader, best
end

-- The company's: "ashwalkers" (the gadgets' name for the player team in a presence row).
function M.ours(row, need, dominance)
  return M.holder(row, need, dominance) == "ashwalkers"
end

return M
