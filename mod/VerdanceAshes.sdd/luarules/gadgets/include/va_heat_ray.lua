-- The Halberd's heat ray: how much of the company's energy bank it is running on, and what that
-- does to a pulse. Pure arithmetic, so the gadget and the tests read the same curve.
--
-- The bank is the fraction of energy the team is holding, measured against a bank no smaller than
-- BANK_FLOOR (a two-solar store that is "full" is still a small store). Every pulse draws DRAW of
-- that bank, so a fuller, deeper economy buys a harder, longer, farther ray, and a Solarium
-- feeding the bank keeps it there.

local M = {}

M.UNIT = "va_halberd"
M.BANK_FLOOR = 4000

M.DRAW = 0.06            -- of the bank, taken from the team on every pulse
M.DAMAGE = { 0.55, 2.20 } -- × the weapon's damage, bank empty .. bank full
M.RANGE = { 0.85, 1.40 }  -- × the weapon's range
M.BURN_SECONDS = { 0.4, 3.0 } -- how long the target keeps burning after a pulse
M.BURN_RATE = 0.20       -- of the pulse's damage, per second of burn

local function clamp(v, lo, hi)
  if v < lo then return lo end
  if v > hi then return hi end
  return v
end

local function lerp(range, t)
  return range[1] + (range[2] - range[1]) * t
end

-- 0 (empty) .. 1 (full) for a team holding `energy` of `storage`.
function M.charge(energy, storage)
  energy = tonumber(energy) or 0
  storage = tonumber(storage) or 0
  return clamp(energy / math.max(storage, M.BANK_FLOOR), 0, 1)
end

-- What one pulse draws from the team: a share of the (floored) bank.
function M.draw(storage)
  return M.DRAW * math.max(tonumber(storage) or 0, M.BANK_FLOOR)
end

-- The ray at a given charge: multipliers for damage and range, seconds of burn, burn damage/second
-- as a fraction of the baseline pulse.
function M.at(charge)
  local c = clamp(tonumber(charge) or 0, 0, 1)
  local damage = lerp(M.DAMAGE, c)
  return {
    charge = c,
    damage = damage,
    range = lerp(M.RANGE, c),
    burnSeconds = lerp(M.BURN_SECONDS, c),
    burnRate = M.BURN_RATE * damage, -- × baseline damage = burn damage per second
  }
end

return M
