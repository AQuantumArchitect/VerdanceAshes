-- campaign/hero_wrecks.lua: a hero's wreck: death to wreck, the rez that brings them back, a wreck that is destroyed or times out
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: checkHeroWreckTimeouts, heroOnFeatureCreated, heroOnFeatureDestroyed,
-- heroOnUnitCreated, heroOnUnitDestroyed, resolveWorkerFeatureID
-- Uses: hero_joins, heroes, state, terminal

local heroPendingWreck = {}   -- dead unitID -> heroId (awaiting corpse FeatureCreated)
local heroByFeatureID = {}    -- wreck featureID -> heroId
-- Shared read-only with the exfil gadget's HUD scan, so it need not walk every feature on the map.
if GG then GG.VA_HeroWreckFeatures = heroByFeatureID end
local wreckConsumedByRez = {} -- featureID -> true when a resurrection consumed it
local HERO_WRECK_TIMEOUT = 90 -- frames a corpse may lag the death (BAR corpse-link window)

-- Resurrection often destroys the wreck feature before UnitCreated runs; hold
-- permadeath for a short grace so the rezzed unit can reclaim the hero identity.
local HERO_REZ_GRACE = 60     -- 2s at 30fps
local HERO_REZ_MATCH_DIST = 450 -- elmos; rez spawns on the wreck

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

local function builderCanResurrect(builderID)
  if not builderID then return false end
  local dID = Spring.GetUnitDefID(builderID)
  local ud = dID and UnitDefs[dID]
  return ud and ud.canResurrect == true
end

-- Match a freshly created unit back to a downed hero (feature id, def+position).
-- A hero can come back by rez while down, in rez grace, waiting for the wreck, or "lost" only
-- because the wreck never linked (no_wreck): the corpse may still be lying there.
local function heroRezzable(rec)
  local st = rec and rec.state
  return st == "down" or st == "rez_grace" or st == "down_pending_wreck" or (st == "lost" and rec.diedHow == "no_wreck")
end

local function findHeroForResurrection(unitID, unitDefID, builderID)
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

local function rezBuilderWorkingFeature(featureID)
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
