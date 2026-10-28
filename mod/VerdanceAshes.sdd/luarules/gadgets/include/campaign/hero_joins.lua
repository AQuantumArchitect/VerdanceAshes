-- campaign/hero_joins.lua: a wild hero joins: raised, captured or a field factory taken; recruited ids kept across reloads
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: heroOnUnitGiven, maybeFieldFactoryJoin, recruitAssistFortifyOnSecure,
-- restoreRecruitedHeroIdsFromRules, tryRecruitFieldHero
-- Uses: crew, field_recruits, hero_wrecks, heroes, state

-- If the wreck corpse was a mobile proxy (geo/fusion/nano/airpad seeds), swap
-- the rezzed constructor into the real hero chassis once they join.
local function promoteFieldRecruitChassis(rec, unitID)
  if not rec or not unitID or not Spring.ValidUnitID(unitID) then return unitID end
  if not rec.needsChassisPromote then return unitID end
  local want = tostring(rec.unitDefName or "")
  if want == "" or not UnitDefNames or not UnitDefNames[want] then
    rec.needsChassisPromote = false
    return unitID
  end
  local curDefID = Spring.GetUnitDefID and Spring.GetUnitDefID(unitID)
  local cur = curDefID and UnitDefs[curDefID]
  local curName = cur and cur.name or ""
  if curName == want then
    rec.needsChassisPromote = false
    return unitID
  end
  local x, y, z = Spring.GetUnitPosition(unitID)
  local team = Spring.GetUnitTeam(unitID) or playerTeamID
  local facing = (Spring.GetUnitBuildFacing and Spring.GetUnitBuildFacing(unitID)) or 0
  local xp = 0
  if Spring.GetUnitExperience then xp = Spring.GetUnitExperience(unitID) or 0 end
  rec.promotingChassis = true
  heroByUnitID[unitID] = nil
  Spring.DestroyUnit(unitID, false, true) -- reclaimed → no wreck
  rec.promotingChassis = false
  local fresh = Spring.CreateUnit(want, x, y or 0, z, facing, team)
  if not fresh then
    Spring.Echo("VA_FIELD_RECRUIT_PROMOTE_FAIL id=" .. tostring(rec.id)
      .. " want=" .. want .. " from=" .. tostring(curName))
    rec.needsChassisPromote = false
    return nil
  end
  rec.needsChassisPromote = false
  rec.wreckSeedDef = nil
  heroRecovered(rec, fresh)
  if Spring.SetUnitExperience and xp > 0 then
    pcall(Spring.SetUnitExperience, fresh, math.max(xp, tonumber(rec.peakXp) or 0))
  end
  Spring.Echo("VA_FIELD_RECRUIT_PROMOTE id=" .. tostring(rec.id)
    .. " from=" .. tostring(curName) .. " to=" .. want .. " unit=" .. tostring(fresh))
  return fresh
end

-- Sign a wild / mission-join hero onto the company. Used by wreck+rez,
-- decoy capture (UnitGiven), and assist_fortify on zone secure.
local function publishRecruitedHeroIds()
  local parts = {}
  for _, id in ipairs(VA_FIELD_RECRUIT.recruited or {}) do
    if id and tostring(id) ~= "" then parts[#parts + 1] = tostring(id) end
  end
  -- Sticky across soft-continue + gadget auto-reload (Lua tables reset on reload).
  Spring.SetGameRulesParam("va_recruited_heroes", table.concat(parts, ","), { public = true })
  Spring.SetGameRulesParam("va_recruited_count", #parts, { public = true })
end

function restoreRecruitedHeroIdsFromRules()
  local raw = tostring((Spring.GetGameRulesParam("va_recruited_heroes")) or "")
  if raw == "" or raw == "0" then return 0 end
  local n = 0
  VA_FIELD_RECRUIT.recruited = VA_FIELD_RECRUIT.recruited or {}
  for id in string.gmatch(raw, "[^,]+") do
    id = tostring(id or ""):match("^%s*(.-)%s*$") or ""
    if id ~= "" then
      local seen = false
      for _, x in ipairs(VA_FIELD_RECRUIT.recruited) do
        if x == id then seen = true; break end
      end
      if not seen then
        VA_FIELD_RECRUIT.recruited[#VA_FIELD_RECRUIT.recruited + 1] = id
        n = n + 1
      end
      local rec = heroes[id]
      if rec then
        rec.recruited = true
        rec.recruitable = false
        rec.wasFieldRecruit = true
      end
    end
  end
  if n > 0 then
    Spring.Echo("VA_FIELD_RECRUIT_RESTORE count=" .. tostring(#VA_FIELD_RECRUIT.recruited)
      .. " from_rules=" .. raw)
  end
  return n
end

function tryRecruitFieldHero(rec, unitID, reason)
  if not rec or not rec.recruitable or rec.recruited then return false end
  unitID = promoteFieldRecruitChassis(rec, unitID) or unitID
  rec.recruited = true
  rec.recruitable = false
  rec.recruitReason = tostring(reason or rec.recruitMode or "wreck_rez")
  VA_FIELD_RECRUIT.recruited[#VA_FIELD_RECRUIT.recruited + 1] = rec.id
  publishRecruitedHeroIds()
  if unitID and Spring.ValidUnitID(unitID) then
    Spring.SetUnitRulesParam(unitID, "va_recruitable", 0, { public = true })
    Spring.SetUnitRulesParam(unitID, "va_recruited", 1, { public = true })
    Spring.SetUnitRulesParam(unitID, "va_force_role", "field_join", { public = true })
    Spring.SetUnitRulesParam(unitID, "va_recruit_reason", rec.recruitReason, { public = true })
  end
  local rx, rz = 0, 0
  if unitID and Spring.ValidUnitID(unitID) then
    rx, _, rz = Spring.GetUnitPosition(unitID)
  end
  -- Pull the bound bay/lab onto the company (capture already may have done this).
  claimFieldFactoriesForHero(rec.id, rx, rz)
  resolveHeroDownObjective(rec, "recruited")
  broadcastHeroEvent("recruited", rec, rx, rz)
  Spring.Echo("VA_FIELD_RECRUITED id=" .. tostring(rec.id)
    .. " unit=" .. tostring(unitID)
    .. " reason=" .. tostring(rec.recruitReason))
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_BEAT", "field_recruit", tostring(rec.id), tostring(rec.name or rec.id), 0, 0)
  end
  return true
end

-- Factory structure captured or rezzed onto the player team.
function maybeFieldFactoryJoin(unitID, unitDefID, unitTeam, builderID)
  if unitTeam ~= playerTeamID or not unitID then return end
  local forHero = Spring.GetUnitRulesParam(unitID, "va_field_factory_for")
  -- Rez: builder was working a stamped Legion bay wreck.
  if (not forHero or tostring(forHero) == "") and builderID then
    local featureID = resolveWorkerFeatureID(builderID)
    if featureID and VA_FIELD_RECRUIT.fabByFeature[featureID] then
      forHero = VA_FIELD_RECRUIT.fabByFeature[featureID]
      VA_FIELD_RECRUIT.fabByFeature[featureID] = nil
    end
  end
  if forHero and tostring(forHero) ~= "" then
    Spring.SetUnitRulesParam(unitID, "va_field_factory_for", tostring(forHero), { public = true })
    enableFieldFactoryPrinter(unitID, tostring(forHero))
    Spring.Echo("VA_FIELD_FACTORY_OWNED hero=" .. tostring(forHero) .. " unit=" .. tostring(unitID))
    return
  end
  -- Fallback: structure def → bound field hero (rez lost the feature link).
  local ud = unitDefID and UnitDefs[unitDefID]
  local defName = ud and ud.name
  if not defName then return end
  local roster = VA_CREW_loadRoster()
  if not roster.FACTORIES then return end
  for _, fab in pairs(roster.FACTORIES) do
    if fab and tostring(fab.structureDef or "") == defName and fab.boundHero then
      local hid = tostring(fab.boundHero)
      local rec = heroes[hid]
      if rec and (rec.wasFieldRecruit or rec.recruitable or rec.recruited) then
        Spring.SetUnitRulesParam(unitID, "va_field_factory_for", hid, { public = true })
        enableFieldFactoryPrinter(unitID, hid)
        Spring.Echo("VA_FIELD_FACTORY_REZ hero=" .. hid .. " unit=" .. tostring(unitID))
        return
      end
    end
  end
end

-- Decoy commanders (and any cancapture builder) convert via Capture.
-- When a recruitable hero unit is Given to the player, that is a join.
function heroOnUnitGiven(unitID, unitDefID, newTeam, oldTeam)
  if newTeam ~= playerTeamID then return end
  maybeFieldFactoryJoin(unitID, unitDefID, newTeam, nil)
  local id = heroByUnitID[unitID]
  if not id then return end
  local rec = heroes[id]
  if not rec then return end
  -- Capture is the standard conversion path (armdecom cancapture=true).
  if tryRecruitFieldHero(rec, unitID, "capture") then
    -- Ensure they sit on the player force role after the transfer.
    if Spring.ValidUnitID(unitID) then
      Spring.SetUnitRulesParam(unitID, "va_force_role", "field_join", { public = true })
    end
  end
end

-- After fortify / secure: assist_fortify recruits who are still alive join.
function recruitAssistFortifyOnSecure()
  for _, rec in pairs(heroes) do
    if rec and rec.recruitable and not rec.recruited then
      local mode = tostring(rec.recruitMode or "")
      if mode == "assist_fortify" or mode == "mission_assist" then
        local uid = rec.unitID
        if uid and Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
          -- Pull them onto the player team if they were still wild/NPC.
          local team = Spring.GetUnitTeam(uid)
          if team and team ~= playerTeamID and Spring.TransferUnit then
            pcall(Spring.TransferUnit, uid, playerTeamID, false)
          end
          tryRecruitFieldHero(rec, uid, "assist_fortify")
        end
      end
    end
  end
end
