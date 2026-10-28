-- campaign/result.lua: the sortie result: every JSON part, chunked logging, the headless finish
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: echoStatus, finishHeadlessResult, heroStatesJson, logJsonChunked, logResult,
-- objectiveCompleteHow, recordShellScar
-- Uses: field_recruits, hero_spawn, heroes, mission_data, objectives, start, state, telemetry,
-- terminal, translation

local objectiveBypassed = false

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

function heroResultsJson()
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

function recruitedHeroIdsJson()
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
function namedOutcomesJson()
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

function primaryCompanionJson()
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

function graphJson()
  local g = mission.graph or {}
  -- q7 = Tenebrium scarcity axis (1=dry, 0=abundant). Live bank softens readout.
  local q7 = tonumber(g.q7_resource_scarcity or g.q7_scarcity or 0) or 0
  local bank = tonumber(tenebLoot.bank) or 0
  local liveQ7 = q7
  if bank > 0 then
    liveQ7 = math.max(0, math.min(1, q7 - math.min(0.35, bank * 0.04)))
  end
  return table.concat({
    '"q0_armada_cortex":' .. jnum(g.q0_armada_cortex or 0, 4),
    '"q2_void_structure":' .. jnum(g.q2_void_structure or 0, 4),
    '"q3_biogenesis_memory":' .. jnum(g.q3_biogenesis_memory or 0, 4),
    '"q4_ai_human":' .. jnum(g.q4_ai_human or 0, 4),
    '"q6_contested":' .. jnum(g.q6_contested or 0, 4),
    '"q6_independent":' .. jnum(g.q6_independent or 0, 4),
    '"q7_scarcity":' .. jnum(liveQ7, 4),
    '"q7_resource_scarcity":' .. jnum(liveQ7, 4),
    '"tenebriumBank":' .. jnum(bank, 0),
    '"armadaTenebriumCrisis":' .. tostring(tenebLoot.armadaCrisis == true)
  }, ',')
end

function reputationJson()
  -- WO-002: clans collapsed into nullmercs. Prefer nullmercs; if only clans is
  -- present on an old seed, emit it under nullmercs (never emit both as distinct).
  local r = mission.reputation or {}
  local merc = r.nullmercs
  if merc == nil then merc = r.clans end
  merc = merc or 0
  return table.concat({
    '"armada":' .. jnum(r.armada or 0, 2),
    '"cortex":' .. jnum(r.cortex or 0, 2),
    '"nullmercs":' .. jnum(merc, 2),
    '"sev":' .. jnum(r.sev or 0, 2)
  }, ',')
end

function economyJson()
  local e = mission.economy or {}
  return table.concat({
    '"metalIncome":' .. jnum(e.metalIncome or 0, 2),
    '"energyIncome":' .. jnum(e.energyIncome or 0, 2),
    '"buildPower":' .. jnum(e.buildPower or 0, 2)
  }, ',')
end

objectiveCompleteHow = ""

-- The primary objective id, listed once it completed by any path (destroyed,
-- zone held, node claimed). Python reads this as "the objective was done".
function destroyedObjectiveIdsJson()
  local oid = mission.objective and mission.objective.id
  if oid and objectiveComplete then
    return '[' .. jstr(oid) .. ']'
  end
  return '[]'
end

-- One row for the primary objective: how far it got and how it completed.
-- status is the mechanic that finished it, not a judgement of the sortie.
function objectiveResultsJson()
  local obj = mission.objective or {}
  if not obj.id then return '[]' end
  local objStatus = "incomplete"
  if objectiveComplete then
    if objectiveCompleteHow == "node_claimed" then
      objStatus = "claimed"
    elseif objectiveCompleteHow == "zone_held" or objectiveCompleteHow == "zone_fortified" then
      objStatus = "complete"
    else
      objStatus = "destroyed"
    end
  end
  local damage = 0
  if objectiveTargetCount > 0 then
    damage = objectiveTargetsDestroyed / objectiveTargetCount
  elseif objectiveComplete then
    damage = 1
  end
  return '[{' .. table.concat({
    '"objectiveId":' .. jstr(obj.id),
    '"kind":' .. jstr(obj.kind or ""),
    '"mode":' .. jstr(vaObjectiveMode(obj.kind)),
    '"status":' .. jstr(objStatus),
    '"how":' .. jstr(objectiveCompleteHow or ""),
    '"targetsTotal":' .. jnum(objectiveTargetCount),
    '"targetsDestroyed":' .. jnum(objectiveTargetsDestroyed),
    '"damage":' .. jnum(damage, 3),
  }, ',') .. '}]'
end

-- Drop 4: secondary-objective ledger for the campaign engine (bonus marks pay
-- merc standing; required marks are implied by any victory that got home).
function secondaryResultsJson()
  return MarksLib.resultsJson(marks, jstr, jnum)
end

-- Fusion vaults + their beamer teeth that are still standing at terminal.
-- Campaign state keeps these so the prize is here when you come back, and
-- offscreen aggression can schedule a defend sortie instead of silent wipe.
function survivingInstallsJson()
  local byPocket = {}
  local units = Spring.GetAllUnits() or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local hv = Spring.GetUnitRulesParam(uid, "va_high_value")
      local held = Spring.GetUnitRulesParam(uid, "va_held_install")
      local role = tostring(Spring.GetUnitRulesParam(uid, "va_force_role") or "")
      local pocket = tostring(Spring.GetUnitRulesParam(uid, "va_shell_pocket") or "")
      local zone = tostring(Spring.GetUnitRulesParam(uid, "va_shell_zone") or "")
      local isShell = Spring.GetUnitRulesParam(uid, "va_living_shell") == 1
        or Spring.GetUnitRulesParam(uid, "va_living_shell") == true
      local interesting = (hv == 1) or (held == 1) or role == "held_install"
        or role == "objective_secondary"
      if isShell and interesting and pocket ~= "" then
        local bag = byPocket[pocket]
        if not bag then
          bag = {
            pocketId = pocket,
            zoneId = zone,
            highValue = (hv == 1 or role == "objective_secondary"),
            held = (held == 1 or role == "held_install"),
            ownerTeam = Spring.GetUnitTeam(uid),
            units = {},
          }
          byPocket[pocket] = bag
        end
        local dID = Spring.GetUnitDefID(uid)
        local ud = dID and UnitDefs[dID]
        local x, _, z = Spring.GetUnitPosition(uid)
        local hp, maxHp = Spring.GetUnitHealth(uid)
        bag.units[#bag.units + 1] = {
          def = ud and ud.name or "",
          x = x or 0,
          z = z or 0,
          hpFrac = (maxHp and maxHp > 0 and hp) and (hp / maxHp) or 1,
          highValue = (hv == 1),
        }
        if hv == 1 then bag.highValue = true end
        if zone ~= "" then bag.zoneId = zone end
      end
    end
  end
  -- Also count beamer/LLT teeth in the same HV pocket even if not marked secondary.
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local pocket = tostring(Spring.GetUnitRulesParam(uid, "va_shell_pocket") or "")
      local bag = pocket ~= "" and byPocket[pocket]
      if bag and bag.highValue then
        local role = tostring(Spring.GetUnitRulesParam(uid, "va_force_role") or "")
        local hv = Spring.GetUnitRulesParam(uid, "va_high_value")
        if role == "occupation" or role == "held_install" or role == "" then
          local dID = Spring.GetUnitDefID(uid)
          local ud = dID and UnitDefs[dID]
          local n = ud and tostring(ud.name or ""):lower() or ""
          if n:find("beamer", 1, true) or n:find("llt", 1, true) or n:find("hlt", 1, true)
              or n:find("fus", 1, true) then
            local already = false
            for _, u in ipairs(bag.units) do
              if u.def == (ud and ud.name) then
                -- coarse dedupe by def+near position later; allow multiples
              end
            end
            local x, _, z = Spring.GetUnitPosition(uid)
            local hp, maxHp = Spring.GetUnitHealth(uid)
            -- Skip if this uid was already recorded as HV/secondary above.
            local skip = (hv == 1) or role == "objective_secondary"
            if not skip then
              bag.units[#bag.units + 1] = {
                def = ud and ud.name or "",
                x = x or 0,
                z = z or 0,
                hpFrac = (maxHp and maxHp > 0 and hp) and (hp / maxHp) or 1,
                highValue = false,
              }
            end
          end
        end
      end
    end
  end
  local parts = {}
  local mapId = tostring((mission and mission.deploymentMapId) or "")
  for _, bag in pairs(byPocket) do
    if bag.highValue and #(bag.units) > 0 then
      local owner = "enemy"
      if bag.held or (bag.ownerTeam == playerTeamID) then owner = "player" end
      local uparts = {}
      for _, u in ipairs(bag.units) do
        uparts[#uparts + 1] = '{'
          .. '"unitDefName":' .. jstr(u.def)
          .. ',"x":' .. jnum(u.x, 1)
          .. ',"z":' .. jnum(u.z, 1)
          .. ',"hpFrac":' .. jnum(u.hpFrac, 3)
          .. ',"highValue":' .. tostring(u.highValue == true)
          .. '}'
      end
      parts[#parts + 1] = '{'
        .. '"mapId":' .. jstr(mapId)
        .. ',"zoneId":' .. jstr(bag.zoneId or "")
        .. ',"pocketId":' .. jstr(bag.pocketId or "")
        .. ',"installationId":' .. jstr(mapId .. "::" .. tostring(bag.pocketId or ""))
        .. ',"owner":' .. jstr(owner)
        .. ',"status":"standing"'
        .. ',"highValue":true'
        .. ',"units":[' .. table.concat(uparts, ",") .. ']'
        .. '}'
    end
  end
  return '[' .. table.concat(parts, ',') .. ']'
end

-- One walk over the player's units at terminal, five facts out of it:
--   footprint    company-built structures (pads / mex / storage) so a claimed zone is
--                not empty dirt on re-entry. Heroes and their pack structures travel
--                with the sheet and are skipped (saving them respawns a second Solarium).
--   survivors    mobile combat units by def (legacy cadre carry).
--   survivorXp   per def: count / peak+avg engine XP / peak+avg craft XP (fighters AND
--                constructors; rez bots and builders carry craft XP). Named heroes use
--                their sticky peak when it beats live engine XP.
--   loanUnitHp   per def HP quality of units tagged va_loan_package (broker settle).
--   armyValue    metal of living mobile combat units (banked as army budget by Python).
-- Self-contained on purpose: the shared unit helpers are defined further down.
function playerUnitFacts()
  local out = { footprint = {}, footprintCount = 0, survivors = {}, xp = {}, loan = {}, armyValue = 0 }
  local maxFootprint = 400   -- a whole base: the old 64 kept the wind farm and lost the converters
  local deployZ = tostring((mission and mission.deploymentZoneId) or "")
  local sx = Game.mapSizeX or 1
  local sz = Game.mapSizeZ or 1
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  for i = 1, #units do
    local uID = units[i]
    if Spring.ValidUnitID(uID) and not Spring.GetUnitIsDead(uID) then
      local dID = Spring.GetUnitDefID(uID)
      local ud = dID and UnitDefs[dID]
      if ud then
        local structure = ud.isBuilding or ud.isFactory or ((ud.speed or 1) == 0)
        local commander = ud.customParams and ud.customParams.iscommander
        local fights = ud.canAttack or (ud.weapons and #ud.weapons > 0)
        local builder = (tonumber(ud.buildSpeed) or 0) > 0 or ud.canResurrect or ud.canRepair
        local x, _, z = Spring.GetUnitPosition(uID)
        local hp, maxHp = Spring.GetUnitHealth(uID)
        local hpFrac = (maxHp and maxHp > 0 and hp) and (hp / maxHp) or 1
        -- footprint: structures only, never commanders / living shell / hero pack kit
        if structure and not commander and out.footprintCount < maxFootprint then
          local shell = Spring.GetUnitRulesParam(uID, "va_living_shell")
          local isShell = (shell == 1 or shell == true or shell == "1")
          local heroMark = Spring.GetUnitRulesParam(uID, "va_hero_id")
          local packMark = Spring.GetUnitRulesParam(uID, "va_pack_id")
          local travels = (heroMark ~= nil and heroMark ~= "" and heroMark ~= 0)
            or (packMark ~= nil and packMark ~= "" and packMark ~= 0)
          if (not isShell) and (not travels) then
            local facing = 0
            if Spring.GetUnitBuildFacing then
              facing = tonumber(Spring.GetUnitBuildFacing(uID)) or 0
            end
            local zoneId = deployZ
            if zoneMap and type(zoneMap.zones) == "table" and x and z then
              for _, zrec in ipairs(zoneMap.zones) do
                local b = zrec.bounds or {}
                if x >= normalizedToElmos(b.xMin, sx) and x <= normalizedToElmos(b.xMax, sx)
                    and z >= normalizedToElmos(b.zMin, sz) and z <= normalizedToElmos(b.zMax, sz) then
                  zoneId = tostring(zrec.zoneId or zoneId)
                  break
                end
              end
            end
            out.footprintCount = out.footprintCount + 1
            out.footprint[#out.footprint + 1] = '{'
              .. '"unitDefName":' .. jstr(ud.name or "")
              .. ',"x":' .. jnum(x or 0, 1)
              .. ',"z":' .. jnum(z or 0, 1)
              .. ',"facing":' .. jnum(facing)
              .. ',"hpFrac":' .. jnum(hpFrac, 3)
              .. ',"zoneId":' .. jstr(zoneId)
              .. ',"owner":"player"'
              .. ',"role":"player_footprint"'
              .. '}'
          end
        end
        -- survivors / armyValue: mobile combat units
        if (not structure) and (not commander) and fights then
          out.survivors[ud.name] = (out.survivors[ud.name] or 0) + 1
          out.armyValue = out.armyValue + (tonumber(ud.metalCost or ud.metal or 0) or 0)
        end
        -- survivorXp: mobile fighters + constructors
        if (not structure) and (not commander) and (fights or builder) then
          local xp = 0
          if Spring.GetUnitExperience then
            xp = tonumber((Spring.GetUnitExperience(uID))) or 0
          end
          local hid = heroByUnitID and heroByUnitID[uID]
          if hid and heroes and heroes[hid] then
            local peak = math.max(tonumber(heroes[hid].peakXp) or 0, tonumber(heroes[hid].lastXp) or 0)
            if peak > xp then xp = peak end
          end
          local craft = tonumber((Spring.GetUnitRulesParam(uID, "va_craft_xp"))) or 0
          local b = out.xp[ud.name]
          if not b then
            b = { count = 0, sumXp = 0, peakXp = 0, sumCraft = 0, peakCraft = 0 }
            out.xp[ud.name] = b
          end
          b.count = b.count + 1
          b.sumXp = b.sumXp + xp
          if xp > b.peakXp then b.peakXp = xp end
          b.sumCraft = b.sumCraft + craft
          if craft > b.peakCraft then b.peakCraft = craft end
        end
        -- loanUnitHp: anything tagged as a broker loan
        local loan = Spring.GetUnitRulesParam(uID, "va_loan_package")
        if (loan == 1 or loan == true or loan == "1") and ud.name then
          local frac = (tonumber(maxHp) or 0) > 0 and ((tonumber(hp) or 0) / tonumber(maxHp)) or 0
          local b = out.loan[ud.name]
          if not b then
            b = { count = 0, sum = 0, min = 1 }
            out.loan[ud.name] = b
          end
          b.count = b.count + 1
          b.sum = b.sum + frac
          if frac < b.min then b.min = frac end
        end
      end
    end
  end
  Spring.Echo("VA_PLAYER_FOOTPRINT count=" .. tostring(out.footprintCount)
    .. " map=" .. tostring((mission and mission.deploymentMapId) or ""))
  return out
end

function playerFootprintJson(facts)
  return '[' .. table.concat(facts.footprint, ',') .. ']'
end

function playerSurvivorsJson(facts)
  local parts = {}
  for name, c in pairs(facts.survivors) do parts[#parts + 1] = jstr(name) .. ':' .. jnum(c) end
  return '{' .. table.concat(parts, ',') .. '}'
end

function playerSurvivorXpJson(facts)
  local parts = {}
  for name, b in pairs(facts.xp) do
    local avg = (b.count > 0) and (b.sumXp / b.count) or 0
    local avgCraft = (b.count > 0) and (b.sumCraft / b.count) or 0
    parts[#parts + 1] = jstr(name) .. ':{'
      .. '"count":' .. jnum(b.count)
      .. ',"peakXp":' .. jnum(b.peakXp, 4)
      .. ',"avgXp":' .. jnum(avg, 4)
      .. ',"peakCraftXp":' .. jnum(b.peakCraft, 4)
      .. ',"avgCraftXp":' .. jnum(avgCraft, 4)
      .. '}'
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

function loanUnitHpJson(facts)
  local parts = {}
  for name, b in pairs(facts.loan) do
    local avg = (b.count > 0) and (b.sum / b.count) or 0
    parts[#parts + 1] = jstr(name) .. ':{'
      .. '"count":' .. jnum(b.count)
      .. ',"avgHpFrac":' .. jnum(avg, 3)
      .. ',"minHpFrac":' .. jnum(b.min, 3)
      .. '}'
  end
  return '{' .. table.concat(parts, ',') .. '}'
end

-- Living-shell scar events this sortie (occupation model lock — wrath not listed).
local shellScarEvents = {}
function recordShellScar(unitID, unitDefID)
  if not unitID then return end
  local role = Spring.GetUnitRulesParam and Spring.GetUnitRulesParam(unitID, "va_force_role")
  local pocket = Spring.GetUnitRulesParam and Spring.GetUnitRulesParam(unitID, "va_shell_pocket")
  -- Living shell stamps va_shell_zone; accept legacy va_zone_id if present.
  local zone = Spring.GetUnitRulesParam and (
    Spring.GetUnitRulesParam(unitID, "va_shell_zone")
    or Spring.GetUnitRulesParam(unitID, "va_zone_id")
  )
  local shell = Spring.GetUnitRulesParam and Spring.GetUnitRulesParam(unitID, "va_living_shell")
  if not (shell == 1 or shell == true or shell == "1" or pocket or role == "occupation" or role == "shell") then
    return
  end
  local ud = unitDefID and UnitDefs[unitDefID]
  local defName = ud and ud.name or ""
  local hvParam = Spring.GetUnitRulesParam and Spring.GetUnitRulesParam(unitID, "va_high_value")
  local highValue = (hvParam == 1 or hvParam == true or hvParam == "1")
  if not highValue and type(defName) == "string" then
    local dn = string.lower(defName)
    if string.find(dn, "fus", 1, true) or string.find(dn, "beamer", 1, true)
        or string.find(dn, "annihilator", 1, true) then
      highValue = true
    end
  end
  local targetZone = (mission and mission.objective and mission.objective.targetZoneId)
    or (mission and mission.targetZoneId) or ""
  shellScarEvents[#shellScarEvents + 1] = {
    zoneId = zone and tostring(zone) or tostring(targetZone),
    pocketId = pocket and tostring(pocket) or "",
    unitDefName = defName,
    destroyed = true,
    damageFrac = 1.0,
    highValue = highValue and true or false,
  }
end

function shellScarsJson()
  local parts = {}
  for i = 1, #shellScarEvents do
    local e = shellScarEvents[i]
    parts[#parts + 1] = '{'
      .. '"zoneId":' .. jstr(e.zoneId or "")
      .. ',"pocketId":' .. jstr(e.pocketId or "")
      .. ',"unitDefName":' .. jstr(e.unitDefName or "")
      .. ',"destroyed":true'
      .. ',"damageFrac":1'
      .. ',"highValue":' .. tostring(e.highValue == true)
      .. '}'
  end
  return '[' .. table.concat(parts, ',') .. ']'
end

-- The result is facts only (law: Lua reports facts, Python interprets).
-- status is the terminal KIND (extracted | wiped | closed), never a verdict;
-- tools/manifest_v1.py and tools/match_credit_v1.py turn these facts into
-- victory / partial / defeat / abandon, zone flips and credits. Nothing here
-- may compute a judgement — if Python needs something, export the fact.
local function resultJson()
  local alive, total = companionCounts()
  local req = mission.objective and mission.objective.requiredFrames or 600
  local frame = Spring.GetGameFrame() or 0
  local obj = mission.objective or {}
  local targetZone = mission.targetZoneId or obj.targetZoneId or ""
  local patron = mission.patron or (mission.worldConflict and mission.worldConflict.patron) or ""
  -- Capture state machine facts: the pocket was cleared / the hold finished.
  local nodeClaimed = capture.nodeClaimed or (objectiveCompleteHow == "node_claimed")
  local chapter = sortieChapter or 1
  local reasonSafe = tostring(terminalReason or "none"):gsub("|", "_")
  local cid = mission.campaignId or "verdance_ashes"
  local mid = mission.missionId or "va_unknown"
  local mn = tostring(mission.missionNumber or 0)
  -- resultKey: unique per sortie attempt (chapter + terminal kind + reason + frame).
  local rkey = cid .. "|" .. mid .. "|" .. mn
    .. "|ch" .. tostring(chapter)
    .. "|" .. tostring(status)
    .. "|" .. reasonSafe
    .. "|f" .. tostring(frame)
  Spring.SetGameRulesParam("va_result_key", rkey, { public = true })
  local sortieId = mission.hubChoiceId or mission.choiceId or mission.sortieId or ""
  -- Exfil refund: living Tnb stakes on player builds return to liquid bank.
  -- Campaign settle uses tenebriumBank as bag SoT; without this, spent stakes
  -- on left-behind structures vanish from the company wallet.
  local livingStakes, livingStakeUnits = 0, 0
  if tenebLoot.refundLivingStakesOnExfil then
    livingStakes, livingStakeUnits = tenebLoot.refundLivingStakesOnExfil(playerTeamID)
  elseif tenebLoot.livingStakes then
    livingStakes, livingStakeUnits = tenebLoot.livingStakes(playerTeamID)
  end
  livingStakes = math.floor(tonumber(livingStakes) or 0)
  livingStakeUnits = math.floor(tonumber(livingStakeUnits) or 0)
  -- End-of-sortie metal stock → campaign 1km$ export (floor(metal/1000)).
  -- Campaign bag stays home; settle ADDS this export (does not replace bag).
  local metalStored, metalStorage = 0, 0
  if Spring.GetTeamResources then
    local okM, mc, ms = pcall(Spring.GetTeamResources, playerTeamID, "metal")
    if okM then
      metalStored = tonumber(mc) or 0
      metalStorage = tonumber(ms) or 0
    end
  end
  local metalKExtracted = math.floor(metalStored / 1000)
  local com = (mission and mission.commerce) or {}
  -- Bag no longer enters the field (metalKBrought=0). fieldStart is operating
  -- allotment only; settle nets it out so unused seed does not inflate the bag.
  local metalKBrought = math.floor(tonumber(com.metalKBrought or 0) or 0)
  local metalKFieldStart = math.floor(tonumber(com.fieldStartMetalK or com.metalKFieldStart or 0) or 0)
  -- One walk over the player's units: footprint, survivors, XP, loan HP, army metal.
  local facts = playerUnitFacts()
  return '{' .. table.concat({
    '"schemaVersion":' .. jstr("verdance-match-result/2.0"),
    '"campaignId":' .. jstr(cid),
    '"missionId":' .. jstr(mid),
    '"missionNumber":' .. jnum(mission.missionNumber or 0),
    '"playerTeamId":' .. jnum(playerTeamID),
    '"armyValue":' .. jnum(facts.armyValue, 2),
    '"metrics":{"armyValue":' .. jnum(facts.armyValue, 2) .. '}',
    '"chapterIndex":' .. jnum(chapter),
    '"pathSignal":' .. jstr(mission.pathSignal or "B"),
    -- terminal kind only: extracted | wiped | closed (Python reads the verdict off the manifest)
    '"status":' .. jstr(status),
    '"manifest":' .. ((GG and GG.VA_ManifestJson) and GG.VA_ManifestJson() or 'null'),
    '"resultKey":' .. jstr(rkey),
    '"sortieId":' .. jstr(tostring(sortieId)),
    '"holdFrames":' .. jnum(holdFrames),
    '"requiredFrames":' .. jnum(req),
    '"frame":' .. jnum(frame),
    '"elapsedMinutes":' .. jnum(frame / 1800.0, 2),
    '"deploymentMapId":' .. jstr(mission.deploymentMapId or ""),
    '"mapId":' .. jstr(mission.deploymentMapId or ""),
    '"deploymentZoneId":' .. jstr(mission.deploymentZoneId or ""),
    '"targetZoneId":' .. jstr(targetZone),
    '"patron":' .. jstr(patron),
    -- capture state machine (facts)
    '"nodeClaimed":' .. tostring(nodeClaimed == true),
    '"nodeClaimedFrame":' .. jnum(nodeClaimedFrame),
    '"pocketCleared":' .. tostring(capture.pocketCleared == true),
    '"capturePhase":' .. jstr(capture.phase or "idle"),
    '"captureMode":' .. tostring(capture.mode == true),
    '"regrowWaves":' .. jnum(capture.regrowWaves or 0),
    '"zoneHoldFrames":' .. jnum(zoneHoldFrames),
    '"terminalReason":' .. jstr(terminalReason),
    -- primary objective (facts)
    '"objectiveKind":' .. jstr(obj.kind or ""),
    '"objectiveMode":' .. jstr(vaObjectiveMode(obj.kind)),
    '"objectiveComplete":' .. tostring(objectiveComplete == true),
    '"objectiveCompleteHow":' .. jstr(objectiveCompleteHow or ""),
    '"objectiveCompleteFrame":' .. jnum(objectiveCompleteFrame),
    '"objectiveBypassed":' .. tostring(objectiveBypassed == true),
    '"objectiveTargetsTotal":' .. jnum(objectiveTargetCount),
    '"objectiveTargetsDestroyed":' .. jnum(objectiveTargetsDestroyed),
    -- required secondary marks still open + the full-victory gate the HUD showed (EXTRACT phase)
    '"requiredMarksLeft":' .. jnum(MarksLib.requiredLeft(marks)),
    '"allObjectivesDone":' .. tostring(vaAllObjectivesDone() == true),
    -- objectiveFailed is the SoT latch (rescue contract destroyed). Alias kept
    -- for older hub/kernel readers. Fail hero lets company.fieldPool mark lost.
    '"objectiveFailed":' .. tostring(rescueContractFailed == true),
    '"objectiveFailReason":' .. jstr(rescueContractFailReason or ""),
    '"objectiveFailHero":' .. jstr(rescueContractFailHero or ""),
    '"rescueContractFailed":' .. tostring(rescueContractFailed == true),
    '"extractionZoneId":' .. jstr(mission.extractionZoneId or obj.extractionZoneId or ""),
    '"playerSurvivors":' .. playerSurvivorsJson(facts),
    '"playerSurvivorXp":' .. playerSurvivorXpJson(facts),
    '"loanUnitHp":' .. loanUnitHpJson(facts),
    '"shellScars":' .. shellScarsJson(),
    '"heroResults":' .. heroResultsJson(),
    '"recruitedHeroIds":' .. recruitedHeroIdsJson(),
    '"namedOutcomes":' .. namedOutcomesJson(),
    '"destroyedObjectiveIds":' .. destroyedObjectiveIdsJson(),
    '"objectiveResults":' .. objectiveResultsJson(),
    '"secondaryResults":' .. secondaryResultsJson(),
    '"survivingInstalls":' .. survivingInstallsJson(),
    '"playerFootprint":' .. playerFootprintJson(facts),
    -- pass three belief contract, produced by game_verdance_belief_observe.lua (GG, no new locals here)
    '"observedZones":' .. ((GG and GG.VA_ObservedZonesJson) and GG.VA_ObservedZonesJson() or 'null'),
    -- the kings' showdown, from game_verdance_kings.lua: who fell, when, to whom
    '"kings":' .. ((GG and GG.VA_KingsJson) and GG.VA_KingsJson() or 'null'),
    -- a commander suit won in the field, from game_verdance_suits.lua (verdance.campaign.suits)
    '"commanderSuit":' .. ((GG and GG.VA_SuitJson) and GG.VA_SuitJson() or 'null'),
    '"beliefExport":' .. ((GG and GG.VA_BeliefExportJson) and GG.VA_BeliefExportJson() or 'null'),
    '"purge":{"armed":' .. tostring(extraObj.purge == true)
      .. ',"done":' .. tostring(extraObj.purgeDone == true) .. '}',
    '"companionsAlive":' .. jnum(alive),
    '"companionsTotal":' .. jnum(total),
    '"debugAutoProgress":' .. jnum(debugAutoProgress),
    '"sessionMode":' .. jstr(mission.sessionMode or "same_map"),
    '"occupationModel":' .. jstr(mission.occupationModel or "living_shell"),
    '"map":{"name":' .. jstr(Game.mapName or "") .. ',"sizeX":' .. jnum(Game.mapSizeX or 0) .. ',"sizeZ":' .. jnum(Game.mapSizeZ or 0) .. '}',
    '"zoneMap":{' .. zoneMapJson() .. '}',
    '"economy":{' .. economyJson() .. '}',
    '"metalStored":' .. jnum(metalStored, 1),
    '"metalStorage":' .. jnum(metalStorage, 1),
    '"metalKExtracted":' .. jnum(metalKExtracted),
    '"metalKBrought":' .. jnum(metalKBrought),
    '"metalKFieldStart":' .. jnum(metalKFieldStart),
    '"metalExportMode":' .. jstr("add"),
    '"graph":{' .. graphJson() .. '}',
    '"reputation":{' .. reputationJson() .. '}',
    '"primaryCompanion":{' .. primaryCompanionJson() .. '}',
    '"tenebriumLooted":' .. jnum(tenebLoot.looted or tenebLoot.total or 0),
    '"tenebriumBank":' .. jnum(tenebLoot.bank or 0),
    '"tenebriumInvested":' .. jnum(livingStakes),
    '"tenebriumLivingStakes":' .. jnum(livingStakes),
    '"tenebriumLivingStakeUnits":' .. jnum(livingStakeUnits),
    '"tenebriumSpent":' .. jnum(tenebLoot.spent or 0),
    '"tenebriumLost":' .. jnum(tenebLoot.lost or 0),
    '"tenebriumLootEvents":' .. (tenebLoot.eventsJson and tenebLoot.eventsJson() or '[]'),
    '"tenebriumWrecksCreated":' .. jnum(tenebLoot.wrecksCreated or 0),
    '"tenebriumWrecksClaimed":' .. jnum(tenebLoot.wrecksClaimed or 0),
    '"tenebriumWrecksLost":' .. jnum(tenebLoot.wrecksLost or 0),
    '"tenebriumUnclaimedOnExtraction":' .. jnum(tenebLoot.unclaimedWrecks and tenebLoot.unclaimedWrecks() or 0),
    '"tenebriumClaimEvents":' .. (tenebLoot.claimEventsJson and tenebLoot.claimEventsJson() or '[]'),
    '"tenebriumTeamBanks":' .. (tenebLoot.teamBanksJson and tenebLoot.teamBanksJson() or '{}'),
    '"tenebriumFactionBanks":' .. (tenebLoot.factionBanksJson and tenebLoot.factionBanksJson() or '{}'),
    '"armadaTenebriumCrisis":' .. tostring(tenebLoot.armadaCrisis == true),
    '"zoneDv":' .. zoneDvJson()
  }, ',') .. '}'
end

function echoStatus()
  local req = mission.objective and mission.objective.requiredFrames or 600
  Spring.Echo("VA_STATUS mission=" .. tostring(mission.missionId) .. " status=" .. status .. " hold=" .. holdFrames .. "/" .. req .. " auto=" .. debugAutoProgress)
end

function logJsonChunked(prefix, json)
  local chunkSize = 180
  local total = math.ceil(#json / chunkSize)
  if total < 1 then total = 1 end
  Spring.Echo(prefix .. "_BEGIN")
  for i = 1, total do
    local a = ((i - 1) * chunkSize) + 1
    local b = i * chunkSize
    Spring.Echo(prefix .. "_CHUNK " .. tostring(i) .. "/" .. tostring(total) .. " " .. json:sub(a, b))
  end
  Spring.Echo(prefix .. "_END")
end

-- Forward declaration: the Hermitian-observable emitter is defined later (it
-- depends on the zone-scan helpers), but the terminal paths above need to call
-- it. Assigning to this file-scope local at its definition site wires them up.
logAndBroadcastTranslation = nil

function logResult()
  -- resultJson can throw on bad Spring returns; never skip the harvest marker.
  local ok, json = pcall(resultJson)
  if not ok then
    Spring.Echo("VA_RESULT_JSON_ERROR " .. tostring(json))
    json = "{"
      .. '"schemaVersion":"verdance-match-result/2.0-fallback",'
      .. '"status":' .. jstr(tostring(status or "unknown")) .. ","
      .. '"terminalReason":' .. jstr(tostring(terminalReason or "result_json_error")) .. ","
      .. '"objectiveComplete":' .. tostring(objectiveComplete == true) .. ","
      .. '"objectiveFailed":' .. tostring(rescueContractFailed == true) .. ","
      .. '"objectiveFailHero":' .. jstr(tostring(rescueContractFailHero or "")) .. ","
      .. '"tenebriumBank":' .. jnum((tenebLoot and tenebLoot.bank) or 0) .. ","
      .. '"tenebriumLooted":' .. jnum((tenebLoot and (tenebLoot.looted or tenebLoot.total)) or 0)
      .. "}"
  end
  lastResultJson = json
  logJsonChunked("VA_RESULT_JSON", json)
  echoStatus()
end

function finishHeadlessResult(outcome)
  local req = mission.objective and mission.objective.requiredFrames or 600
  status = outcome or "victory"
  holdFrames = req
  debugAutoProgress = 0
  terminal = true
  terminalReason = "headless_fastwin"
  Spring.SetGameRulesParam("va_hold_frames", holdFrames, { public = true })
  Spring.Echo("VA_HEADLESS_RESULT_READY mission=" .. tostring(mission.missionId) .. " status=" .. status)
  logResult()
  if logAndBroadcastTranslation then logAndBroadcastTranslation() end
  if headless.quit then
    headless.quitFrame = Spring.GetGameFrame() + 2
  end
end
