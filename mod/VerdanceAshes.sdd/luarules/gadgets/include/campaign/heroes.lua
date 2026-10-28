-- campaign/heroes.lua: hero lifecycle: down, wreck, rez, lost, recovered, field joins
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: checkHeroWreckTimeouts, finalizeHeroStates, heroByUnitID, heroInState,
-- heroOnFeatureCreated, heroOnFeatureDestroyed, heroOnUnitCreated, heroOnUnitDestroyed,
-- heroOnUnitGiven, heroWasRecovered, heroes, maybeFieldFactoryJoin, recruitAssistFortifyOnSecure,
-- rescueContractFailHero, rescueContractFailReason, rescueContractFailed,
-- restoreRecruitedHeroIdsFromRules, tryRecruitFieldHero
-- Uses: crew, field_recruits, hero_spawn, mission_data, state, terminal, units

-- Sortie-linked field recruit wreck destroyed → fail contract, open partial extract.
-- Idempotent latch (WO-008: no hard defeat; RTB instead).
rescueContractFailed = false
rescueContractFailReason = ""
rescueContractFailHero = ""

-- Named hero roster (Fire Emblem doctrine): heroes leave wrecks; a rez bot can
-- bring them back mid-mission. A destroyed wreck is permadeath - and a mission
-- defeat when the hero is mission-critical (the player character, Ketha).
heroes = {}             -- heroId -> record (state machine below)
heroByUnitID = {}       -- live unitID -> heroId

local heroPendingWreck = {}   -- dead unitID -> heroId (awaiting corpse FeatureCreated)
local heroByFeatureID = {}    -- wreck featureID -> heroId
local wreckConsumedByRez = {} -- featureID -> true when a resurrection consumed it
local HERO_WRECK_TIMEOUT = 90 -- frames a corpse may lag the death (BAR corpse-link window)

-- Resurrection often destroys the wreck feature before UnitCreated runs; hold
-- permadeath for a short grace so the rezzed unit can reclaim the hero identity.
local HERO_REZ_GRACE = 60     -- 2s at 30fps
local HERO_REZ_MATCH_DIST = 450 -- elmos; rez spawns on the wreck

-- ============================================================
-- Named hero lifecycle (Fire Emblem doctrine).
-- alive -> down_pending_wreck -> down (wreck tracked) -> recovered | lost.
-- BAR's own gadgets guarantee the primitives: corpses link to their source
-- unit (unit_corpse_link.lua) and resurrection fires UnitCreated with the
-- rez bot as builder while the corpse still exists (unit_resurrected.lua).
--
-- Downed heroes share the marks registry (kind=hero_recover) with vault marks.
-- ============================================================

setTerminal = nil  -- forward: a lost critical hero ends the mission (gadget-env; local budget)

function registerHeroDownObjective(rec)
  local sid = MarksLib.upsertHeroRecover(marks, rec)
  if not sid then return end
  marksCommit("secondary_changed", sid)
end

function resolveHeroDownObjective(rec, outcome)
  local g, newly = MarksLib.completeHeroRecover(marks, rec, outcome)
  local sid = rec and (rec.secondaryId or ("hero_down_" .. tostring(rec.id))) or ""
  if newly and outcome == "lost" then
    marksCommit("secondary_failed", sid)
  elseif newly then
    marksCommit("secondary_complete", sid)
  else
    marksCommit("secondary_changed", sid)
  end
  return g, newly
end

function broadcastHeroEvent(event, rec, x, z)
  Spring.Echo("VA_HERO_" .. string.upper(event) .. " id=" .. rec.id .. " critical=" .. tostring(rec.missionCritical))
  publishHeroRules()
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_HERO_EVENT", event, rec.id, rec.name, rec.missionCritical and 1 or 0, x or 0, z or 0)
  end
end

-- One fail path: latch → publish. The player decides when to lift (manifest);
-- there is no extract loop to open.
function failRescueContract(rec, how)
  if rescueContractFailed then return false end
  if not rec or not rec.wasFieldRecruit or rec.recruited then return false end
  if rec.sortieLinked ~= true then return false end
  rescueContractFailed = true
  rescueContractFailReason = tostring(how or "wreck_destroyed")
  rescueContractFailHero = tostring(rec.id or "")
  -- SoT for HUD / playfeel / result JSON. Do NOT set objectiveBypassed —
  -- bypass is hive_clear_or_bypass only; fail is its own latch.
  Spring.SetGameRulesParam("va_objective_failed", 1, { public = true })
  Spring.SetGameRulesParam("va_objective_fail_reason", rescueContractFailReason, { public = true })
  Spring.SetGameRulesParam("va_objective_fail_hero", rescueContractFailHero, { public = true })
  Spring.Echo("VA_OBJECTIVE_FAILED reason=" .. rescueContractFailReason
    .. " hero=" .. rescueContractFailHero
    .. " name=" .. tostring(rec.name or ""))
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_MISSION_EVENT", "objective_failed", rescueContractFailReason)
  end
  return true
end

function heroLost(rec, how)
  -- WO-008: named loss never hard-defeats. Contracted field recruit →
  -- failRescueContract (partial EXTRACT). Company heroes: bookkeeping only.
  if rec.state == "lost" then return end
  rec.state = "lost"
  rec.diedHow = tostring(how or "")
  resolveHeroDownObjective(rec, "lost")
  -- Latch before lost broadcast so HUD sees va_objective_failed and skips
  -- a second rescue bark (objective_failed event owns that copy).
  failRescueContract(rec, how)
  broadcastHeroEvent("lost", rec, rec.deathX, rec.deathZ)
  Spring.Echo("VA_NAMED_DEAD " .. rec.id .. " cause=" .. tostring(how or "unknown")
    .. " critical=" .. tostring(rec.missionCritical == true)
    .. " linked=" .. tostring(rec.sortieLinked == true))
  -- Intentionally no setTerminal("defeat", "hero_lost_*") — DCO-01 wreck rule.
end

function heroRecovered(rec, newUnitID)
  rec.state = "alive"
  rec.unitID = newUnitID
  rec.rezGraceUntil = nil
  heroByUnitID[newUnitID] = rec.id
  Spring.SetUnitRulesParam(newUnitID, "va_hero", 1, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_id", rec.id, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_name", rec.name, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_critical", rec.missionCritical and 1 or 0, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_level", rec.level or 1, { public = true })
  Spring.SetUnitRulesParam(newUnitID, "va_hero_rank", HeroTags.normalizeRank(rec.rank or "Green"), { public = true })
  stampPadToothIfNeeded(newUnitID, rec.id)
  -- BAR's unit_resurrected gadget restores experience and heals the fresh
  -- instance; only the hero toughness multiplier needs re-applying.
  applyHeroModifiers(newUnitID, rec)
  -- XP NEVER drops on death/rez: restore peak (max of lastXp/peakXp).
  local keep = math.max(tonumber(rec.peakXp) or 0, tonumber(rec.lastXp) or 0)
  rec.peakXp = keep
  rec.lastXp = keep
  Spring.SetUnitRulesParam(newUnitID, "va_hero_xp", keep, { public = true })
  if Spring.SetUnitExperience and keep > 0 then
    local cur = 0
    if Spring.GetUnitExperience then cur = Spring.GetUnitExperience(newUnitID) or 0 end
    if cur < keep then pcall(Spring.SetUnitExperience, newUnitID, keep) end
  end
  -- Peak XP is stamped after toughness — refresh vet curve so HP/RoF match kept XP.
  if GG and GG.VA_VetRefresh then
    pcall(GG.VA_VetRefresh, newUnitID)
  end
  local x, _, z = Spring.GetUnitPosition(newUnitID)
  resolveHeroDownObjective(rec, "recovered")
  broadcastHeroEvent("recovered", rec, x, z)
  Spring.Echo("VA_NAMED_RECOVERED " .. rec.id .. " unit=" .. tostring(newUnitID) .. " xp=" .. tostring(keep))
end

function heroOnUnitDestroyed(unitID)
  local id = heroByUnitID[unitID]
  if not id then return end
  local rec = heroes[id]
  heroByUnitID[unitID] = nil
  rec.unitID = nil
  -- Chassis promote destroys the proxy constructor without a rescue contract.
  if rec.promotingChassis then
    return
  end
  -- Through the Spire Gate (game_verdance_jump_gate.lua): gone home, not down.
  if rec.ported then
    return
  end
  if Spring.GetUnitExperience then
    local cur = Spring.GetUnitExperience(unitID) or 0
    rec.lastXp = cur
    rec.peakXp = math.max(tonumber(rec.peakXp) or 0, cur)
  end
  -- Capture unitDef at death so rez matching still works if the seed omitted it.
  -- Never overwrite a real hero chassis with a wreck-seed proxy def.
  if (not rec.unitDefName or rec.unitDefName == "") and Spring.GetUnitDefID then
    local dID = Spring.GetUnitDefID(unitID)
    local ud = dID and UnitDefs[dID]
    if ud and ud.name then rec.unitDefName = ud.name end
  end
  if terminal then return end
  rec.everDown = true
  rec.state = "down_pending_wreck"
  local x, _, z = Spring.GetUnitPosition(unitID)
  rec.deathX, rec.deathZ = x, z
  rec.wreckDeadline = (Spring.GetGameFrame() or 0) + HERO_WRECK_TIMEOUT
  heroPendingWreck[unitID] = id
end

function heroOnFeatureCreated(featureID, allyTeamID, sourceID)
  if not next(heroPendingWreck) then return end
  if not sourceID and GG and GG.GetCorpsePriorUnitID then
    -- Older engine path: BAR's corpse-link registry backfills the source unit.
    sourceID = GG.GetCorpsePriorUnitID(featureID)
  end
  local id = sourceID and heroPendingWreck[sourceID]
  if not id then
    -- No source link (seen with a Halberd hovertank): take the corpse of the hero's chassis
    -- that appears where they fell.
    local fx, _, fz = Spring.GetFeaturePosition(featureID)
    local fdef = Spring.GetFeatureDefID and FeatureDefs[Spring.GetFeatureDefID(featureID) or -1]
    local fname = fdef and fdef.name or ""
    if fx then
      for deadUnitID, hid in pairs(heroPendingWreck) do
        local r = heroes[hid]
        local chassis = r and tostring(r.unitDefName or "") or ""
        local dx, dz = fx - (r and r.deathX or fx), fz - (r and r.deathZ or fz)
        if chassis ~= "" and fname:sub(1, #chassis) == chassis and dx * dx + dz * dz <= 300 * 300 then
          id, sourceID = hid, deadUnitID
          Spring.Echo("VA_HERO_WRECK_BY_POSITION id=" .. hid .. " feature=" .. tostring(featureID) .. " def=" .. fname)
          break
        end
      end
    end
  end
  if not id then return end
  heroPendingWreck[sourceID] = nil
  local rec = heroes[id]
  if rec.state ~= "down_pending_wreck" then return end
  rec.state = "down"
  rec.wreckFeatureID = featureID
  heroByFeatureID[featureID] = id
  if Spring.SetFeatureRulesParam then
    Spring.SetFeatureRulesParam(featureID, "va_hero_wreck", id, { public = true })
    Spring.SetFeatureRulesParam(featureID, "va_hero_wreck_name", rec.name, { public = true })
    Spring.SetFeatureRulesParam(featureID, "va_hero_wreck_def", rec.unitDefName or "", { public = true })
  end
  local x, _, z = Spring.GetFeaturePosition(featureID)
  if x then rec.deathX, rec.deathZ = x, z end
  -- Same objective ledger for seeded field wrecks and mid-fight company downs.
  registerHeroDownObjective(rec)
  broadcastHeroEvent("down", rec, x or rec.deathX, z or rec.deathZ)
end

-- IIFE: nested locals do not count toward main-chunk 200-local limit.
WorkerFeature = (function()
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_worker_feature.lua")
  if ok and type(mod) == "table" then return mod end
  return nil
end)()

function resolveWorkerFeatureID(builderID)
  if WorkerFeature and WorkerFeature.featureIDFromResurrect then
    return WorkerFeature.featureIDFromResurrect(builderID)
  end
  if not builderID or not Spring.GetUnitWorkerTask then return nil end
  local cmdID, targetID = Spring.GetUnitWorkerTask(builderID)
  if cmdID ~= CMD.RESURRECT or not targetID then return nil end
  local featureID = targetID
  if not (Engine and Engine.FeatureSupport and Engine.FeatureSupport.noOffsetForFeatureID) then
    featureID = featureID - Game.maxUnits
  end
  return featureID
end

function builderCanResurrect(builderID)
  if not builderID then return false end
  local dID = Spring.GetUnitDefID(builderID)
  local ud = dID and UnitDefs[dID]
  return ud and ud.canResurrect == true
end

-- Match a freshly created unit back to a downed hero (feature id, def+position).
-- A hero can come back by rez while down, in rez grace, waiting for the wreck, or "lost" only
-- because the wreck never linked (no_wreck): the corpse may still be lying there.
function heroRezzable(rec)
  local st = rec and rec.state
  return st == "down" or st == "rez_grace" or st == "down_pending_wreck" or (st == "lost" and rec.diedHow == "no_wreck")
end

function findHeroForResurrection(unitID, unitDefID, builderID)
  local featureID = resolveWorkerFeatureID(builderID)
  if featureID and heroByFeatureID[featureID] then
    return heroByFeatureID[featureID], featureID
  end

  local ud = unitDefID and UnitDefs[unitDefID]
  local defName = ud and ud.name or ""
  local x, _, z = Spring.GetUnitPosition(unitID)
  if not x then return nil, nil end

  local bestId, bestDist = nil, nil
  for id, rec in pairs(heroes) do
    if heroRezzable(rec) then
      local expected = rec.unitDefName or ""
      if expected == "" or expected == defName then
        local dx = x - (rec.deathX or x)
        local dz = z - (rec.deathZ or z)
        local dist = dx * dx + dz * dz
        local limit = HERO_REZ_MATCH_DIST * HERO_REZ_MATCH_DIST
        if dist <= limit and (not bestDist or dist < bestDist) then
          bestId, bestDist = id, dist
        end
      end
    end
  end
  return bestId, featureID
end

function heroOnUnitCreated(unitID, unitDefID, unitTeam, builderID)
  -- Need either a live wreck map or a hero in rez grace / pending.
  local anyDown = next(heroByFeatureID) ~= nil
  if not anyDown then
    for _, rec in pairs(heroes) do
      if heroRezzable(rec) then
        anyDown = true
        break
      end
    end
  end
  if not anyDown then return end

  -- Only treat as rez when the builder is rezzing or is a rez-capable unit.
  -- (Worker task can already be cleared by the time we run; def check is backup.)
  local featureFromWorker = resolveWorkerFeatureID(builderID)
  if not featureFromWorker and not builderCanResurrect(builderID) then
    return
  end

  local id, featureID = findHeroForResurrection(unitID, unitDefID, builderID)
  if not id then return end
  local rec = heroes[id]
  if featureID then
    wreckConsumedByRez[featureID] = true
    heroByFeatureID[featureID] = nil
  elseif rec.wreckFeatureID then
    wreckConsumedByRez[rec.wreckFeatureID] = true
    heroByFeatureID[rec.wreckFeatureID] = nil
  end
  rec.wreckFeatureID = nil
  if unitTeam == playerTeamID or (Spring.AreTeamsAllied and Spring.AreTeamsAllied(unitTeam, playerTeamID)) then
    heroRecovered(rec, unitID)
    -- Field recruit: wreck+rez (or stash retrieve) by the player signs them on.
    tryRecruitFieldHero(rec, unitID, "wreck_rez")
  else
    heroLost(rec, "captured")
  end
end

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
function publishRecruitedHeroIds()
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

function rezBuilderWorkingFeature(featureID)
  if not featureID or not playerTeamID or not Spring.GetTeamUnits then return false end
  local units = Spring.GetTeamUnits(playerTeamID) or {}
  for i = 1, #units do
    local uid = units[i]
    if uid and builderCanResurrect(uid) then
      local fid = resolveWorkerFeatureID(uid)
      if fid == featureID then return true end
    end
  end
  return false
end

function heroOnFeatureDestroyed(featureID)
  if wreckConsumedByRez[featureID] then
    wreckConsumedByRez[featureID] = nil
    return
  end
  local id = heroByFeatureID[featureID]
  if not id then return end
  heroByFeatureID[featureID] = nil
  local rec = heroes[id]
  rec.wreckFeatureID = nil
  -- Rez path often destroys the corpse a tick before UnitCreated. Always enter
  -- grace for the race — but blast/reclaim (no rez bot on the feature) uses a
  -- short window so rescue-fail → EXTRACT does not wait a full 2s.
  if rec.state == "down" or rec.state == "down_pending_wreck" or rec.state == "rez_grace" then
    local likelyRez = rezBuilderWorkingFeature(featureID)
    local grace = likelyRez and HERO_REZ_GRACE or math.min(HERO_REZ_GRACE, 15)
    rec.state = "rez_grace"
    rec.rezGraceUntil = (Spring.GetGameFrame() or 0) + grace
    rec.wreckLikelyBlasted = not likelyRez
    Spring.Echo("VA_HERO_REZ_GRACE id=" .. id
      .. " feature=" .. tostring(featureID)
      .. " frames=" .. tostring(grace)
      .. " blast=" .. tostring(not likelyRez))
    if not likelyRez and SendToUnsynced then
      -- Early HUD cue: stop "still recoverable" while grace races the rez check.
      SendToUnsynced("VERDANCE_HERO_EVENT", "wreck_gone", rec.id, rec.name,
        rec.missionCritical and 1 or 0, rec.deathX or 0, rec.deathZ or 0)
    end
    return
  end
  heroLost(rec, "wreck_destroyed")
end

function checkHeroWreckTimeouts(frame)
  if next(heroPendingWreck) then
    for deadUnitID, id in pairs(heroPendingWreck) do
      local rec = heroes[id]
      if rec and rec.state == "down_pending_wreck" and frame > (rec.wreckDeadline or 0) then
        heroPendingWreck[deadUnitID] = nil
        heroLost(rec, "no_wreck")
      end
    end
  end
  for id, rec in pairs(heroes) do
    if rec.state == "rez_grace" and frame > (rec.rezGraceUntil or 0) then
      heroLost(rec, "wreck_destroyed")
    end
  end
end

-- Terminal outcome for every hero: intact wrecks are dragged home only when the
-- line holds them dear (mission-critical); anyone else left in a wreck is gone.
function finalizeHeroStates()
  for _, rec in pairs(heroes) do
    if rec.state == "lost" then
      rec.result = "dead"
    elseif rec.state == "down" or rec.state == "down_pending_wreck" or rec.state == "rez_grace" then
      -- Still a wreck (or rez race unresolved): critical = wounded carry, else dead.
      rec.result = rec.missionCritical and "wounded" or "dead"
    else
      -- alive at the end = home in good health, even if they went down and were rezzed
      -- (the rescue is still reported, as a "recovered" named outcome, for the story).
      rec.result = "survived"
      if rec.unitID and Spring.ValidUnitID(rec.unitID) and Spring.GetUnitExperience then
        local cur = Spring.GetUnitExperience(rec.unitID) or 0
        rec.lastXp = cur
        rec.peakXp = math.max(tonumber(rec.peakXp) or 0, cur)
      end
    end
    -- Sticky peak for dead/wounded too (farmed XP survives the wreck).
    rec.peakXp = math.max(tonumber(rec.peakXp) or 0, tonumber(rec.lastXp) or 0)
    rec.lastXp = rec.peakXp
  end
end

-- ============================================================
-- In-mission beats: seed-authored WC3-style triggers -> actions.
-- All beats fire once; evaluation rides the CHECK_PERIOD cadence.
-- ============================================================

function heroInState(heroId, state1, state2)
  if heroId then
    local rec = heroes[heroId]
    return rec ~= nil and (rec.state == state1 or rec.state == state2)
  end
  for _, rec in pairs(heroes) do
    if rec.state == state1 or rec.state == state2 then return true end
  end
  return false
end

function heroWasRecovered(heroId)
  if heroId then
    local rec = heroes[heroId]
    return rec ~= nil and rec.state == "alive" and rec.everDown
  end
  for _, rec in pairs(heroes) do
    if rec.state == "alive" and rec.everDown then return true end
  end
  return false
end
