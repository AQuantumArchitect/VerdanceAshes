-- campaign/mentors.lua: pack mentors (Spoke, the leads): subordinate XP and field effects
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: harvestMentorXp, heroIsPackMentor, isWheelieDef, mentorProductDefs, packMentors,
-- pollMentorSubordinateXp, registerPackMentor, stampMentorSubordinate
-- Uses: crew, hero_spawn, heroes, state

-- Register a named hero on its freshly spawned unit: identity rules params for
-- the HUD/name tags, the toughness multiplier, and carried experience.
-- XP peak is sticky: death/rez never drops lastXp below the mission high-water.
-- Pack mentors (scout / factory heroes): bank XP from ALL subordinates, then
-- re-grant the hero's ONE field-effect stat (speed / vision / build / …).
-- Spoke wheelies remain the classic case; Tick / Kettle / Consul / Twitch join.
packMentors = packMentors or {}  -- heroId -> { bankXp, harvested, minted, productDefs }

-- Compat alias: older call sites still touch wheelieMentor for Spoke.
wheelieMentor = wheelieMentor or { heroId = nil, bankXp = 0, minted = 0, harvested = 0 }

function isWheelieDef(defName)
  if not defName then return false end
  local n = string.lower(tostring(defName))
  return n == "legscout" or n:find("wheel", 1, true) ~= nil
end

function mentorProductDefs()
  local roster = VA_CREW_loadRoster and VA_CREW_loadRoster() or nil
  if roster and roster.MENTOR_PRODUCTS then return roster.MENTOR_PRODUCTS end
  return {}
end

function heroIsPackMentor(heroId, spec, tagList)
  local id = tostring(heroId or (spec and spec.heroId) or "")
  local roster = VA_CREW_loadRoster and VA_CREW_loadRoster() or nil
  if roster and roster.isMentor and roster.isMentor(id) then return true end
  if HeroTags and HeroTags.isMentorHero then
    return HeroTags.isMentorHero(id, tagList)
  end
  local trait = tostring(spec and (spec.heroTrait or spec.trait) or "")
  return trait == "wheelie_mentor" or trait == "scout_tech" or trait == "factory_mentor"
end

local function refreshMentorFieldEffect(heroId)
  local rec = heroes[heroId]
  if not rec or not rec.unitID or not Spring.ValidUnitID(rec.unitID) then return end
  if not HeroTags or not HeroTags.applyToHero then return end
  local roster = VA_CREW_loadRoster and VA_CREW_loadRoster() or nil
  local h = roster and ((roster.get and roster.get(heroId)) or (roster.HEROES and roster.HEROES[heroId])) or nil
  local tagList = HeroTags.collectFromHero(h, { heroId = heroId, heroTrait = rec.trait }, heroId)
  local xp = math.max(tonumber(rec.peakXp) or 0, tonumber((packMentors[heroId] or {}).bankXp) or 0)
  local field = HeroTags.applyToHero(rec.unitID, rec, tagList, xp)
  -- Push the same field effect onto living pack mates.
  if field and field.primaryStat and Spring.GetTeamUnits then
    local units = Spring.GetTeamUnits(playerTeamID) or {}
    for i = 1, #units do
      local u = units[i]
      if u ~= rec.unitID and Spring.ValidUnitID(u) and not Spring.GetUnitIsDead(u) then
        local lead = Spring.GetUnitRulesParam(u, "va_pack_leader")
          or Spring.GetUnitRulesParam(u, "va_pack_id")
        if tostring(lead or "") == tostring(heroId) then
          HeroTags.applyFieldToUnit(u, field, rec)
        end
      end
    end
  end
end

function stampMentorSubordinate(unitID, heroId)
  local bag = packMentors[heroId]
  if not bag then return end
  local floor = tonumber(bag.bankXp) or 0
  Spring.SetUnitRulesParam(unitID, "va_pack_leader", heroId, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_pack_id", heroId, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_pack_role", "mate", { public = true })
  if floor > 0 and Spring.SetUnitExperience then
    pcall(Spring.SetUnitExperience, unitID, floor)
    Spring.SetUnitRulesParam(unitID, "va_mentor_xp_floor", floor, { public = true })
  end
  bag.minted = (bag.minted or 0) + 1
  -- Apply current field effect to the new mate.
  local rec = heroes[heroId]
  if rec and rec.field and HeroTags and HeroTags.applyFieldToUnit then
    HeroTags.applyFieldToUnit(unitID, rec.field, rec)
  elseif rec then
    refreshMentorFieldEffect(heroId)
  end
  if GG and GG.VA_PackOverlayStamp then
    pcall(GG.VA_PackOverlayStamp, unitID, heroId, "mate")
  end
  -- Spoke compat markers
  if heroId == "spoke" then
    Spring.SetUnitRulesParam(unitID, "va_wheelie_mint", 1, { public = true })
    Spring.SetUnitRulesParam(unitID, "va_wheelie_xp_floor", floor, { public = true })
  end
end

function harvestMentorXp(unitID, heroId)
  heroId = tostring(heroId or "")
  if heroId == "" or not packMentors[heroId] then return end
  if heroByUnitID[unitID] then return end -- named hero death handled elsewhere
  local xp = 0
  if Spring.GetUnitExperience then xp = Spring.GetUnitExperience(unitID) or 0 end
  if xp <= 0 then return end
  local bag = packMentors[heroId]
  local prev = tonumber(bag.bankXp) or 0
  if xp <= prev then return end
  bag.bankXp = xp
  bag.harvested = (bag.harvested or 0) + 1
  local rec = heroes[heroId]
  if rec then
    rec.peakXp = math.max(tonumber(rec.peakXp) or 0, xp)
    rec.lastXp = rec.peakXp
    if rec.unitID and Spring.ValidUnitID(rec.unitID) and Spring.SetUnitExperience then
      pcall(Spring.SetUnitExperience, rec.unitID, rec.peakXp)
      Spring.SetUnitRulesParam(rec.unitID, "va_hero_xp", rec.peakXp, { public = true })
    end
    refreshMentorFieldEffect(heroId)
  end
  if heroId == "spoke" then
    wheelieMentor.bankXp = bag.bankXp
    wheelieMentor.harvested = bag.harvested
  end
  Spring.Echo("VA_MENTOR_HARVEST mentor=" .. heroId
    .. " xp=" .. tostring(xp) .. " bank=" .. tostring(bag.bankXp)
    .. " field=" .. tostring(rec and rec.fieldStat or "?"))
end

function registerPackMentor(heroId, rec, seedXp)
  heroId = tostring(heroId or "")
  if heroId == "" then return end
  local bag = packMentors[heroId] or { bankXp = 0, harvested = 0, minted = 0 }
  bag.bankXp = math.max(tonumber(bag.bankXp) or 0, tonumber(seedXp) or 0, tonumber(rec and rec.peakXp) or 0)
  bag.productDefs = mentorProductDefs()[heroId]
  packMentors[heroId] = bag
  if heroId == "spoke" then
    wheelieMentor.heroId = heroId
    wheelieMentor.bankXp = bag.bankXp
  end
  Spring.Echo("VA_PACK_MENTOR online id=" .. heroId
    .. " bank=" .. tostring(bag.bankXp)
    .. " field=" .. tostring(rec and rec.fieldStat or "?"))
end

function pollMentorSubordinateXp(frame)
  if not next(packMentors) then return end
  if frame % 90 ~= 0 then return end -- ~3s
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  local peaks = {}
  for i = 1, #units do
    local u = units[i]
    if Spring.ValidUnitID(u) and not Spring.GetUnitIsDead(u) and not heroByUnitID[u] then
      local lead = Spring.GetUnitRulesParam(u, "va_pack_leader")
        or Spring.GetUnitRulesParam(u, "va_pack_id")
      lead = tostring(lead or "")
      if lead ~= "" and packMentors[lead] then
        local xp = 0
        if Spring.GetUnitExperience then xp = Spring.GetUnitExperience(u) or 0 end
        if xp > (peaks[lead] or 0) then peaks[lead] = xp end
      end
    end
  end
  for heroId, xp in pairs(peaks) do
    local bag = packMentors[heroId]
    if bag and xp > (tonumber(bag.bankXp) or 0) then
      bag.bankXp = xp
      local rec = heroes[heroId]
      if rec then
        rec.peakXp = math.max(tonumber(rec.peakXp) or 0, xp)
        rec.lastXp = rec.peakXp
        if rec.unitID and Spring.ValidUnitID(rec.unitID) and Spring.SetUnitExperience then
          pcall(Spring.SetUnitExperience, rec.unitID, rec.peakXp)
          Spring.SetUnitRulesParam(rec.unitID, "va_hero_xp", rec.peakXp, { public = true })
        end
        refreshMentorFieldEffect(heroId)
        Spring.Echo("VA_MENTOR_POLL mentor=" .. heroId .. " bank=" .. tostring(xp)
          .. " field=" .. tostring(rec.fieldStat or "?"))
      end
    end
  end
end
