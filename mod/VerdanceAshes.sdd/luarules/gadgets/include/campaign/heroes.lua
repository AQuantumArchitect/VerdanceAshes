-- campaign/heroes.lua: the named heroes: their table, the down marks, lost and recovered, the rescue contract, end-of-sortie states
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: broadcastHeroEvent, finalizeHeroStates, heroByUnitID, heroInState, heroLost,
-- heroRecovered, heroWasRecovered, heroes, registerHeroDownObjective, rescueContractFailHero,
-- rescueContractFailReason, rescueContractFailed, resolveHeroDownObjective
-- Uses: hero_spawn, mission_data, state, terminal, units

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
local function failRescueContract(rec, how)
  if rescueContractFailed then return false end
  if not rec or not rec.wasFieldRecruit or rec.recruited then return false end
  if rec.sortieLinked ~= true then return false end
  rescueContractFailed = true
  rescueContractFailReason = tostring(how or "wreck_destroyed")
  rescueContractFailHero = tostring(rec.id or "")
  -- SoT for HUD / playfeel / result JSON; the fail is its own latch.
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
