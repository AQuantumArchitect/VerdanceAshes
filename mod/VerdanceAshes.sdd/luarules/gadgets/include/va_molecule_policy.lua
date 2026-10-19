-- Verdance molecule policy (Stage 4) — soft blend hand doctrine toward D(u).
-- Modoption / GameRulesParam: va_molecule_policy = off | shadow | soft
-- Default: off. Soft α from va_molecule_doctrine.lua (SOFT_ALPHA ≈ 0.28).
-- BeliefField + player orders unchanged. Kiln/hive hard gates stay hand overrides.

local M = {}

M.MODE_OFF = "off"
M.MODE_SHADOW = "shadow"
M.MODE_SOFT = "soft"
M.DEFAULT_ALPHA = 0.28

local MoleculeDoc = nil

local function loadMoleculeDoc()
  if MoleculeDoc then return MoleculeDoc end
  if VFS and VFS.Include then
    local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_molecule_doctrine.lua")
    if not ok or type(mod) ~= "table" then
      ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_molecule_doctrine.lua")
    end
    if ok and type(mod) == "table" then
      MoleculeDoc = mod
    end
  end
  return MoleculeDoc
end

local function clamp(v, lo, hi)
  v = tonumber(v) or 0
  if v < lo then return lo end
  if v > hi then return hi end
  return v
end

local function copyDoc(src)
  local out = {}
  if type(src) ~= "table" then return out end
  for k, v in pairs(src) do
    out[k] = v
  end
  return out
end

function M.normalizeMode(raw)
  local s = string.lower(tostring(raw or "off"))
  if s == "soft" or s == "1" or s == "true" or s == "on" then
    return M.MODE_SOFT
  end
  if s == "shadow" or s == "log" then
    return M.MODE_SHADOW
  end
  return M.MODE_OFF
end

--- Resolve mode: GameRulesParam overrides modoption when set.
--- Default soft (vibe seal / YOLO play path). Rollback: va_molecule_policy=off.
function M.resolveMode(modOptions)
  local fromRules = nil
  if Spring and Spring.GetGameRulesParam then
    fromRules = Spring.GetGameRulesParam("va_molecule_policy")
  end
  if fromRules ~= nil and tostring(fromRules) ~= "" then
    return M.normalizeMode(fromRules)
  end
  local opts = modOptions or (Spring and Spring.GetModOptions and Spring.GetModOptions()) or {}
  local raw = opts.va_molecule_policy or opts.va_moleculepolicy
  if raw == nil or tostring(raw) == "" then
    return M.MODE_SOFT
  end
  return M.normalizeMode(raw)
end

function M.derivedFor(heroId)
  local doc = loadMoleculeDoc()
  if not doc or not doc.forHero then return nil end
  return doc.forHero(heroId)
end

function M.alpha()
  local doc = loadMoleculeDoc()
  local a = doc and tonumber(doc.SOFT_ALPHA) or M.DEFAULT_ALPHA
  return clamp(a, 0.15, 0.35)
end

--- Soft-blend numeric biases toward D(u). Hard gates always from hand.
function M.blend(hand, derived, alpha)
  local out = copyDoc(hand)
  if type(derived) ~= "table" then
    return out
  end
  alpha = clamp(alpha or M.alpha(), 0.15, 0.35)
  local keys = { "kiteBias", "bailBias", "craftBias", "pushBias" }
  for i = 1, #keys do
    local k = keys[i]
    local h = tonumber(hand and hand[k])
    local d = tonumber(derived[k])
    if h ~= nil and d ~= nil then
      out[k] = h * (1 - alpha) + d * alpha
    elseif d ~= nil then
      out[k] = d
    end
  end
  -- Sacred hard gates from hand/codex
  if hand then
    if hand.allowBail ~= nil then out.allowBail = hand.allowBail and true or false end
    if hand.allowKite ~= nil then out.allowKite = hand.allowKite and true or false end
    if hand.preferDefenses == true then out.preferDefenses = true end
    if hand.squad then out.squad = hand.squad end
    if hand.flock ~= nil then out.flock = hand.flock end
    if hand.verb then out.verb = hand.verb end
  end
  -- Identity floors
  if out.allowKite == false then
    out.kiteBias = math.min(tonumber(out.kiteBias) or 0, 0.15)
  end
  if out.allowBail == false then
    out.bailBias = math.min(tonumber(out.bailBias) or 0, 0.15)
  end
  if hand and tostring(hand.kind or "") == "kiln" then
    out.pushBias = math.max(tonumber(out.pushBias) or 0, 1.10)
    out.preferDefenses = true
  end
  out._moleculeSoft = true
  out._moleculeAlpha = alpha
  return out
end

--- Pick doctrine for resolve given mode.
-- off: hand unchanged
-- soft: blended
-- shadow: hand for live act; caller may also resolve with blend for log
function M.apply(hand, heroId, mode)
  mode = M.normalizeMode(mode)
  if mode ~= M.MODE_SOFT then
    return hand, mode, nil
  end
  local der = M.derivedFor(heroId)
  if not der then
    return hand, mode, nil
  end
  return M.blend(hand, der, M.alpha()), mode, der
end

return M
