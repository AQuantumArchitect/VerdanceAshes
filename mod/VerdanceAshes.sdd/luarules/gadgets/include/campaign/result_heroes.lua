-- campaign/result_heroes.lua: the result's hero parts: hero states and outcomes, who was recruited, the named dead and wounded, companions
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: heroStatesJson, resultHeroFields
-- Uses: field_recruits, hero_spawn, heroes, state

-- Several cold-path helpers below are gadget-env globals (no `local`): the main
-- chunk rides Lua 5.1's 200-local cap, and each global here frees one slot.
function heroStatesJson()
  local parts = {}
  for id, rec in pairs(heroes) do
    parts[#parts + 1] = jstr(id) .. ':{' .. table.concat({
      '"name":' .. jstr(rec.name or id),
      '"state":' .. jstr(rec.state or "alive"),
      '"missionCritical":' .. tostring(rec.missionCritical == true),
    }, ',') .. '}'
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

local function heroResultsJson()
  local parts = {}
  for id, rec in pairs(heroes) do
    -- a pair's partner ("verse#1") is not a campaign hero: the lead reports for the pair
    if not tostring(id):find("#", 1, true) then
      -- peakXp is sticky across death; export max so campaign never loses farmed XP.
      local xpOut = math.max(tonumber(rec.peakXp) or 0, tonumber(rec.lastXp) or 0)
      parts[#parts + 1] = jstr(id) .. ':{' .. table.concat({
        '"status":' .. jstr(rec.result or (rec.everDown and "wounded" or "survived")),
        '"wasDown":' .. tostring(rec.everDown == true),
        '"xp":' .. jnum(xpOut, 4),
        '"level":' .. tostring(tonumber(rec.level) or 1),
        '"rank":' .. jstr(HeroTags.normalizeRank(rec.rank or "Green")),
        '"recruited":' .. tostring(rec.recruited == true),
        '"fieldRecruit":' .. tostring(rec.wasFieldRecruit == true or rec.recruited == true),
      }, ',') .. '}'
    end
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

local function recruitedHeroIdsJson()
  local parts = {}
  for _, id in ipairs(VA_FIELD_RECRUIT.recruited or {}) do
    parts[#parts + 1] = jstr(id)
  end
  -- Also pick up any hero flagged recruited without list push (safety).
  for id, rec in pairs(heroes) do
    if rec.recruited then
      local seen = false
      for _, x in ipairs(VA_FIELD_RECRUIT.recruited or {}) do
        if x == id then seen = true; break end
      end
      if not seen then parts[#parts + 1] = jstr(id) end
    end
  end
  return '[' .. table.concat(parts, ',') .. ']'
end

-- DCO-01 / WO-006: named character outcomes for the story engine characters{} registry.
-- Maps gadget hero FSM results onto namedOutcomes: dead | recovered | wounded.
local function namedOutcomesJson()
  local parts = {}
  for id, rec in pairs(heroes) do
    -- Wild field recruits who never joined are not company casualties.
    if rec.wasFieldRecruit and not rec.recruited then
      -- skip
    else
    local raw = rec.result or (rec.everDown and "wounded" or "survived")
    if raw == "survived" and rec.everDown then raw = "recovered" end
    local outcome = nil
    local cause = rec.diedHow or ""
    if raw == "dead" then
      outcome = "dead"
      if cause == "" then cause = "wreck_destroyed" end
    elseif raw == "recovered" then
      outcome = "recovered"
      cause = "reclaimed_friendly"
    elseif raw == "wounded" then
      -- recovered in-match via rez vs left wounded at game end
      if rec.everDown and rec.state == "alive" then
        outcome = "recovered"
        cause = "reclaimed_friendly"
      else
        outcome = "wounded"
        if cause == "" then cause = "match_end_wreck" end
      end
    end
    if outcome then
      parts[#parts + 1] = '{' .. table.concat({
        '"charId":' .. jstr(id),
        '"outcome":' .. jstr(outcome),
        '"cause":' .. jstr(cause),
      }, ',') .. '}'
      Spring.Echo("VA_NAMED_" .. string.upper(outcome == "dead" and "DEAD" or (outcome == "recovered" and "RECOVERED" or "WOUNDED"))
        .. " " .. id .. (cause ~= "" and (" cause=" .. cause) or ""))
    end
    end -- wasFieldRecruit skip else
  end
  return '[' .. table.concat(parts, ',') .. ']'
end

-- The heroes and companions: each hero's outcome, who joined this sortie, the named dead and
-- wounded, the companion count, and a commander suit won in the field.
local function companionCounts()
  local total = 0
  local alive = 0
  if mission and mission.companions then total = #mission.companions end
  if total == 0 then return 0, 0 end
  for _, comp in ipairs(mission.companions) do
    if comp._unitID and Spring.ValidUnitID(comp._unitID) and not Spring.GetUnitIsDead(comp._unitID) then
      alive = alive + 1
    elseif not comp._unitID then
      alive = alive + 1
    end
  end
  return alive, total
end

local function primaryCompanionJson()
  local c = mission and mission.companions and mission.companions[1] or {}
  return table.concat({
    '"id":' .. jstr(c.id or ""),
    '"displayName":' .. jstr(c.displayName or ""),
    '"unitDefName":' .. jstr(c.unitDefName or ""),
    '"xp":' .. jnum(c.xp or 0, 4),
    '"morale":' .. jnum(c.morale or 0, 2),
    '"loyalty":' .. jnum(c.loyalty or 0, 2),
    '"stress":' .. jnum(c.stress or 0, 2),
    '"autonomy":' .. jnum(c.autonomy or 0, 4),
    '"commandMode":' .. jstr(c.commandMode or "hybrid")
  }, ',')
end

function resultHeroFields(c)
  local alive, total = companionCounts()
  return {
    '"heroResults":' .. heroResultsJson(),
    '"recruitedHeroIds":' .. recruitedHeroIdsJson(),
    '"namedOutcomes":' .. namedOutcomesJson(),
    '"companionsAlive":' .. jnum(alive),
    '"companionsTotal":' .. jnum(total),
    '"primaryCompanion":{' .. primaryCompanionJson() .. '}',
    -- a commander suit won in the field, from game_verdance_suits.lua (verdance.campaign.suits)
    '"commanderSuit":' .. ((GG and GG.VA_SuitJson) and GG.VA_SuitJson() or 'null'),
  }
end

