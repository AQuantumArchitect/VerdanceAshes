-- Verdance IntentResolver — shadow-first policy over BeliefField leaves.
-- Emergency intents override squad doctrine; player orders soften soft kite/bail.
-- Hysteresis keeps intents from flickering every think tick.

local M = {}

-- Doctrine profiles: temperament knobs from hero_codex.json (not separate think scripts).
M.DOCTRINE = {
  phobos = {
    squad = "frontline",
    kiteBias = 0.95,
    bailBias = 0.95,
    craftBias = 0.20,
    pushBias = 0.50,
    flock = true,
  },
  rez = {
    squad = "soak",
    kiteBias = 0.30,
    bailBias = 0.70,
    craftBias = 1.00,
    pushBias = 0.10,
    flock = false,
  },
  skirm = {
    squad = "skirm",
    kiteBias = 1.05,
    bailBias = 1.00,
    craftBias = 0.10,
    pushBias = 0.65,
    flock = false,
  },
  line = {
    squad = "frontline",
    kiteBias = 0.55,
    bailBias = 0.85,
    craftBias = 0.15,
    pushBias = 0.55,
    flock = false,
  },
  -- Brakhov the Kiln: always offense, plod into defenses, no kite/bail.
  kiln = {
    squad = "siege",
    kiteBias = 0.02,
    bailBias = 0.02,
    craftBias = 0.0,
    pushBias = 1.25,
    flock = false,
    preferDefenses = true,
    allowKite = false,
    allowBail = false,
  },
  siege_plod = {
    squad = "siege",
    kiteBias = 0.08,
    bailBias = 0.25,
    craftBias = 0.0,
    pushBias = 1.05,
    flock = false,
    preferDefenses = true,
    allowKite = false,
    allowBail = true,
  },
  arty = {
    squad = "backline",
    kiteBias = 0.85,
    bailBias = 0.80,
    craftBias = 0.0,
    pushBias = 0.20,
    flock = false,
    preferDefenses = true,
    allowKite = true,
    allowBail = true,
  },
  -- Vale Soft: stealth rockets — prefer statics, never brawl, fog first.
  fog_siege = {
    squad = "backline",
    kiteBias = 1.00,
    bailBias = 0.90,
    craftBias = 0.0,
    pushBias = 0.18,
    flock = false,
    preferDefenses = true,
    allowKite = true,
    allowBail = true,
  },
  aa_saint = {
    squad = "soak",
    kiteBias = 0.25,
    bailBias = 0.75,
    craftBias = 0.10,
    pushBias = 0.15,
    flock = false,
  },
  pad = {
    squad = "soak",
    kiteBias = 0.15,
    bailBias = 0.70,
    craftBias = 0.35,
    pushBias = 0.05,
    flock = false,
  },
  dirty = {
    squad = "skirm",
    kiteBias = 0.70,
    bailBias = 0.90,
    craftBias = 0.55,
    pushBias = 0.45,
    flock = false,
  },
  hive = {
    squad = "soak",
    kiteBias = 0.20,
    bailBias = 0.15,
    craftBias = 1.05,
    pushBias = 0.40,
    flock = false,
    allowKite = false,
    allowBail = false,
  },
  constructor = {
    squad = "soak",
    kiteBias = 0.40,
    bailBias = 0.80,
    craftBias = 0.95,
    pushBias = 0.15,
    flock = false,
  },
  eco_heart = {
    squad = "soak",
    kiteBias = 0.05,
    bailBias = 0.60,
    craftBias = 0.50,
    pushBias = 0.0,
    flock = false,
    allowKite = false,
  },
  eyes = {
    squad = "skirm",
    kiteBias = 1.10,
    bailBias = 1.05,
    craftBias = 0.15,
    pushBias = 0.20,
    flock = false,
  },
  default = {
    squad = "frontline",
    kiteBias = 0.70,
    bailBias = 0.95,
    craftBias = 0.30,
    pushBias = 0.45,
    flock = false,
  },
}

-- Enter / leave thresholds (Gummy Attention-style hysteresis).
-- bailScore = pain * bailBias; ~40% HP (pain 0.6) * 0.95 ≈ 0.57 crosses 0.55.
M.ENTER = {
  bail = 0.55,
  kite = 0.52,
  craft = 0.48,
  push = 0.60,
}
M.LEAVE = {
  bail = 0.32,
  kite = 0.32,
  craft = 0.28,
  push = 0.35,
}
M.MIN_CONF = 0.28
-- Below this engage-confidence, skirm prefers circle/kite over push.
M.COMMIT_CONF = 0.45

--[[
  Player-order leaf — dissipative belief, not a wall-clock timer.
  Tune these until click-stick feels right (start ~1s soft authority):

    value(t) ≈ 0.5 + 0.5·e^(-γt) after a full pulse from 1.0
    soft-block while value ≥ ORDERS_SOFT_BLOCK and conf ≥ ORDERS_SOFT_CONF

  γ=1.85 → ~1.2s above 0.58 from a full pulse. Raise γ to let go faster;
  lower γ / raise QUEUE_ETA to stay sticky while the order is still running.
]]
M.ORDERS_GAMMA = 1.85
M.ORDERS_PULSE_VALUE = 1.0
M.ORDERS_PULSE_ETA = 0.92
M.ORDERS_QUEUE_VALUE = 0.78  -- reinforce while a combat cmd is still queued
M.ORDERS_QUEUE_ETA = 0.14
M.ORDERS_SOFT_BLOCK = 0.58
M.ORDERS_SOFT_CONF = 0.18
-- Hard danger: threat high + confident → may kite even under orders.
M.HARD_THREAT = 0.78
M.HARD_THREAT_CONF = 0.45

local function clamp01(v)
  v = tonumber(v) or 0
  if v < 0 then return 0 end
  if v > 1 then return 1 end
  return v
end

function M.profile(kind)
  kind = tostring(kind or "default")
  return M.DOCTRINE[kind] or M.DOCTRINE.default
end

-- Merge generated hero row flags (va_hero_doctrine.lua) onto a profile copy.
-- Spring synced Lua does not expose rawget/_G; callers should set M._heroDoc
-- after Include, and we fall back to VFS.Include only.
function M.setHeroDoctrine(doc)
  if type(doc) == "table" then
    M._heroDoc = doc
  end
end

function M.profileForHero(heroId, fallbackKind)
  local base = M.profile(fallbackKind)
  local HeroDoc = M._heroDoc
  if not HeroDoc and VFS and VFS.Include then
    local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_hero_doctrine.lua")
    if not ok or type(mod) ~= "table" then
      ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_hero_doctrine.lua")
    end
    if ok and type(mod) == "table" then
      M._heroDoc = mod
      HeroDoc = mod
    end
  end
  local row = HeroDoc and HeroDoc.forHero and HeroDoc.forHero(heroId) or nil
  if not row and HeroDoc and HeroDoc.HERO_DOCTRINE then
    row = HeroDoc.HERO_DOCTRINE[tostring(heroId or "")]
  end
  if type(row) ~= "table" then
    return base, tostring(fallbackKind or "default")
  end
  local kind = tostring(row.kind or fallbackKind or "default")
  local merged = {}
  local src = M.profile(kind)
  for k, v in pairs(src) do merged[k] = v end
  if row.preferDefenses ~= nil then merged.preferDefenses = row.preferDefenses and true or false end
  if row.allowBail ~= nil then merged.allowBail = row.allowBail and true or false end
  if row.allowKite ~= nil then merged.allowKite = row.allowKite and true or false end
  if row.verb then merged.verb = tostring(row.verb) end
  return merged, kind
end

local function leaf(beliefs, role)
  local b = beliefs and beliefs[role]
  if type(b) == "table" then
    return clamp01(b.value or b[1] or 0.5), clamp01(b.confidence or b[2] or 0)
  end
  return 0.5, 0
end

-- beliefs: { orders=, threat=, pain=, craft=, hold=, pressure= } each {value,confidence}
-- doctrine: profile table
-- prevIntent: string or nil
-- canCraft: bool (builder/rez)
-- returns intent: bail|kite|craft|push|hold
function M.resolve(beliefs, doctrine, prevIntent, canCraft)
  doctrine = doctrine or M.DOCTRINE.default
  prevIntent = prevIntent or "hold"
  local ordersV, ordersC = leaf(beliefs, "orders")
  local threatV, threatC = leaf(beliefs, "threat")
  local painV, painC = leaf(beliefs, "pain")
  local craftV, craftC = leaf(beliefs, "craft")
  local holdV = leaf(beliefs, "hold")
  local pressureV = leaf(beliefs, "pressure")

  local kiteBias = tonumber(doctrine.kiteBias) or 0.6
  local bailBias = tonumber(doctrine.bailBias) or 0.7
  local craftBias = tonumber(doctrine.craftBias) or 0.3
  local pushBias = tonumber(doctrine.pushBias) or 0.5
  local squad = tostring(doctrine.squad or "frontline")
  local allowBail = doctrine.allowBail
  if allowBail == nil then allowBail = true end
  local allowKite = doctrine.allowKite
  if allowKite == nil then allowKite = true end

  local ordersBlock = ordersV >= M.ORDERS_SOFT_BLOCK and ordersC >= M.ORDERS_SOFT_CONF
  local hardDanger = threatV >= M.HARD_THREAT and threatC >= M.HARD_THREAT_CONF

  local function still(intent, value, leave)
    return prevIntent == intent and value >= leave
  end

  -- 1) Bail — dying / heavy pain (hysteresis). Kiln: allowBail=false.
  if allowBail then
    local bailScore = painV * bailBias
    local bailEnter = M.ENTER.bail
    local bailLeave = M.LEAVE.bail
    if painC >= M.MIN_CONF then
      if still("bail", bailScore, bailLeave) or bailScore >= bailEnter then
        if (not ordersBlock) or bailScore >= 0.85 or hardDanger then
          return "bail"
        end
      end
    end
  end

  -- 2) Kite — clear envelope; soft under orders unless hard danger.
  if allowKite and kiteBias >= 0.12 then
    local kiteScore = math.max(threatV, pressureV * 0.85) * kiteBias
    if threatC >= M.MIN_CONF or still("kite", kiteScore, M.LEAVE.kite) then
      if still("kite", kiteScore, M.LEAVE.kite) or kiteScore >= M.ENTER.kite then
        if hardDanger or (not ordersBlock) then
          return "kite"
        end
      end
    end
  end

  -- 3) Craft — constructors / rez when opportunity is believed.
  if canCraft and craftBias >= 0.4 then
    local craftScore = craftV * craftBias
    if craftC >= M.MIN_CONF or still("craft", craftScore, M.LEAVE.craft) then
      if still("craft", craftScore, M.LEAVE.craft) or craftScore >= M.ENTER.craft then
        if not hardDanger then
          return "craft"
        end
      end
    end
  end

  -- 4) Push — skirm/frontline/siege aggressors.
  if squad == "skirm" or squad == "frontline" or squad == "siege" then
    local engage = (1 - threatV) * 0.5 + (1 - painV) * 0.5
    if squad == "siege" then
      -- Siege plods through pain; threat does not cancel commit.
      engage = 0.55 + (1 - painV) * 0.45
    end
    local pushScore = engage * pushBias * (1 - ordersV * 0.35)
    if threatC < M.COMMIT_CONF and squad == "skirm" then
      if holdV >= 0.45 or ordersBlock then
        return "hold"
      end
    end
    local painGate = (squad == "siege") and 0.92 or 0.45
    if (still("push", pushScore, M.LEAVE.push) or pushScore >= M.ENTER.push)
        and not ordersBlock and painV < painGate then
      return "push"
    end
  end

  -- 5) Hold — player queue / soak / backline / frontline idle.
  if ordersBlock or holdV >= 0.4 or squad == "soak" or squad == "frontline"
      or squad == "backline" then
    return "hold"
  end
  return "hold"
end

return M
