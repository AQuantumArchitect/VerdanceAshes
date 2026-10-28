-- campaign/result_company.lua: the result's company parts: what of ours is on the field, survivors and their XP, loan units, metal and Tenebrium
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: playerUnitFacts, resultCompanyFields, resultMetalFields, resultTenebriumFields
-- Uses: heroes, mission_data, start, state

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

local function playerFootprintJson(facts)
  return '[' .. table.concat(facts.footprint, ',') .. ']'
end

local function playerSurvivorsJson(facts)
  local parts = {}
  for name, c in pairs(facts.survivors) do parts[#parts + 1] = jstr(name) .. ':' .. jnum(c) end
  return '{' .. table.concat(parts, ',') .. '}'
end

local function playerSurvivorXpJson(facts)
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

local function loanUnitHpJson(facts)
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

-- The company's units: army value, who survived (and their XP), loan units, where everyone stands.
function resultCompanyFields(c)
  local facts = c.facts
  return {
    '"armyValue":' .. jnum(facts.armyValue, 2),
    '"metrics":{"armyValue":' .. jnum(facts.armyValue, 2) .. '}',
    '"playerSurvivors":' .. playerSurvivorsJson(facts),
    '"playerSurvivorXp":' .. playerSurvivorXpJson(facts),
    '"loanUnitHp":' .. loanUnitHpJson(facts),
    '"playerFootprint":' .. playerFootprintJson(facts),
  }
end

-- The metal the company brings home: what is in storage at extraction (1k for every 1,000), net of
-- the field's start allotment (Python settles it; the bag itself never enters the field).
function resultMetalFields(c)
  local com = (mission and mission.commerce) or {}
  -- Bag no longer enters the field (metalKBrought=0). fieldStart is operating
  -- allotment only; settle nets it out so unused seed does not inflate the bag.
  return {
    '"metalStored":' .. jnum(c.metalStored, 1),
    '"metalStorage":' .. jnum(c.metalStorage, 1),
    '"metalKExtracted":' .. jnum(math.floor(c.metalStored / 1000)),
    '"metalKBrought":' .. jnum(math.floor(tonumber(com.metalKBrought or 0) or 0)),
    '"metalKFieldStart":' .. jnum(math.floor(tonumber(com.fieldStartMetalK or com.metalKFieldStart or 0) or 0)),
    '"metalExportMode":' .. jstr("add"),
  }
end

-- Tenebrium: the bank after the exfil refund, what was looted, spent and lost, the wrecks.
function resultTenebriumFields(c)
  return {
    '"tenebriumLooted":' .. jnum(tenebLoot.looted or tenebLoot.total or 0),
    '"tenebriumBank":' .. jnum(tenebLoot.bank or 0),
    '"tenebriumInvested":' .. jnum(c.livingStakes),
    '"tenebriumLivingStakes":' .. jnum(c.livingStakes),
    '"tenebriumLivingStakeUnits":' .. jnum(c.livingStakeUnits),
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
  }
end

