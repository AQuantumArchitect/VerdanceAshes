local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Unit Behavior Assist",
    desc = "Idle/assist micro: rez repair + tree eat, Phobos frontline kite, skirmisher Dgun standoff",
    author = "Verdance",
    date = "2026-09-06",
    license = "GPL v2 or later",
    layer = 2,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  return
end

--[[
  Player-assist micro for Verdance sorties (human play, not autoplay).

  Policy (v6 — belief-driven intents):
  - Named heroes + rez bots: sense → BeliefField → IntentResolver → actuators.
  - Pack grunts stay manual (pack drag / speed in pack_overlay).
  - Intents: bail | kite | craft | push | hold. Hero Codex doctrine (va_hero_doctrine)
    biases thresholds; Kiln plods to defenses with no kite/bail.
  - Player combat orders pulse dissipative `orders` belief (tune γ in Intent).
  - Actuators reuse existing MOVE/REPAIR/REZ/kite helpers (belief is the bus,
    not a second mover). Inspired by GummyDynasty Umwelt host contract — no umweltd.
  - Stage 4 molecule policy: modoption/GameRulesParam va_molecule_policy=
    off|shadow|soft. soft blends doctrine biases toward D(u) (α≈0.28); BeliefField
    + orders + Kiln hard gates unchanged. Default soft (vibe seal). Rollback=off.
]]

local enabled = true
local playerTeam = 0
local lastThink = -999999
local THINK_PERIOD = 18 -- ~0.6s at 30fps
local moleculePolicyMode = "soft" -- off | shadow | soft (default soft after vibe seal)

-- Chase horizons (seconds of travel at UnitDef.speed). Shared by every BP bot.
local CHASE_SEC_TNB = 16   -- soak priority — walk farther for shards
local CHASE_SEC_CRAFT = 12 -- capture / rez / repair
local CHASE_SEC_TREE = 7   -- energy trees (rez bots)
local CHASE_MIN = 280      -- floor so short-range bots still look nearby
local CHASE_MAX = 2400     -- ceiling so fast cons don't map-wide vacuum
local ENERGY_DEFICIT_FRAC = 0.22 -- current/storage below this → tree eat
local ENERGY_DEFICIT_ABS = 180 -- or absolute current below this
-- Phobos: hold the line. Sense lasers early, but only hop out of the beam
-- envelope — never limp home to nanos unless hurt-retreat already fired.
local PHOBOS_THREAT_RANGE = 560   -- awareness / soft kite start
local PHOBOS_DANGER_RANGE = 320   -- hard bubble: ignore player override
local PHOBOS_FLEE_DIST = 200      -- short hop; stay on the front
local PHOBOS_SKITTISH_COOLDOWN = 75 -- ~2.5s between kite reissues
local SKIRM_DGUN_BUBBLE = 260 -- stay outside this of com/decoy
local SKIRM_FLEE_DIST = 340
local HURT_HP_FRAC = 0.34 -- retreat when below this
local HURT_SAFE_FRAC = 0.55 -- stop auto-retreat once healed past this
local HURT_COOLDOWN = 90 -- frames between retreat reissues (~3s)

local CMD_MOVE = CMD and CMD.MOVE
local CMD_REPAIR = CMD and CMD.REPAIR
local CMD_RECLAIM = CMD and CMD.RECLAIM
local CMD_STOP = CMD and CMD.STOP
local CMD_CAPTURE = CMD and CMD.CAPTURE
local CMD_RESURRECT = CMD and CMD.RESURRECT
local CMD_GUARD = CMD and CMD.GUARD

-- Per-unit last assist tag so we don't spam orders every think.
local lastAssist = {} -- unitID -> { kind=, frame= }
local hurtRetreating = {} -- unitID -> true while in auto-fallback
local aiOrdering = {} -- unitID -> true while gadget issues an order (skip override stamp)

local CMD_ATTACK = CMD and CMD.ATTACK
local CMD_FIGHT = CMD and CMD.FIGHT
local CMD_PATROL = CMD and CMD.PATROL
local PLAYER_COMBAT_CMDS = {}
if CMD_MOVE then PLAYER_COMBAT_CMDS[CMD_MOVE] = true end
if CMD_FIGHT then PLAYER_COMBAT_CMDS[CMD_FIGHT] = true end
if CMD_PATROL then PLAYER_COMBAT_CMDS[CMD_PATROL] = true end
if CMD_ATTACK then PLAYER_COMBAT_CMDS[CMD_ATTACK] = true end
if CMD_GUARD then PLAYER_COMBAT_CMDS[CMD_GUARD] = true end

local Util, UnitClass, Belief, Intent, HeroDoctrine, MoleculePolicy = nil, nil, nil, nil, nil, nil
do
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_util.lua")
  if ok and type(mod) == "table" then Util = mod end
  ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_unit_class.lua")
  if ok and type(mod) == "table" then UnitClass = mod end
  ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_belief_field.lua")
  if ok and type(mod) == "table" then Belief = mod end
  ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_intent_resolver.lua")
  if ok and type(mod) == "table" then Intent = mod end
  ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_hero_doctrine.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_hero_doctrine.lua")
  end
  if ok and type(mod) == "table" then HeroDoctrine = mod end
  ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_molecule_policy.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_molecule_policy.lua")
  end
  if ok and type(mod) == "table" then MoleculePolicy = mod end
  -- Synced env has no rawget/_G; pin doctrine onto Intent explicitly.
  if Intent and Intent.setHeroDoctrine and HeroDoctrine then
    Intent.setHeroDoctrine(HeroDoctrine)
  elseif Intent and HeroDoctrine then
    Intent._heroDoc = HeroDoctrine
  end
end
local function truthy(v)
  return Util and Util.truthy and Util.truthy(v) or (v == true or v == 1)
end

local field = Belief and Belief.new() or nil
local unitIntent = {} -- unitID -> last intent string
local unitDoctrine = {} -- unitID -> doctrine kind
local CRAFT_REEVAL_COOLDOWN = 90 -- ~3s anti-sticky craft reissue
local lastCraftReeval = {} -- unitID -> frame

local function dist2(ax, az, bx, bz)
  local dx, dz = ax - bx, az - bz
  return dx * dx + dz * dz
end

local function unitPos(unitID)
  local x, y, z = Spring.GetUnitPosition(unitID)
  return x, y, z
end

local function queueLen(unitID)
  -- count=0 → queue size only (cheap)
  local n = Spring.GetUnitCommands(unitID, 0)
  if type(n) == "number" then return n end
  local q = Spring.GetUnitCommands(unitID, 1)
  return (q and #q) or 0
end

local function isIdle(unitID)
  return queueLen(unitID) <= 0
end

local function defNameOf(unitID)
  local dID = Spring.GetUnitDefID(unitID)
  local ud = dID and UnitDefs[dID]
  return ud and ud.name or "", ud
end

-- Live build range (craft XP can stretch buildDistance).
local function unitBuildDistance(unitID, ud)
  local base = tonumber(ud and ud.buildDistance) or 0
  if unitID and Spring.GetUnitBuildParams then
    local live = Spring.GetUnitBuildParams(unitID, "buildDistance")
      or Spring.GetUnitBuildParams(unitID, "buildRange")
    live = tonumber(live)
    if live and live > 0 then return live end
  end
  if base > 0 then return base end
  return 100
end

-- BAR/Recoil UnitDef.speed is elmos/sec.
local function unitMoveSpeed(ud)
  return math.max(0, tonumber(ud and ud.speed) or 0)
end

-- Shared chase radius for every build-power bot.
--   chase = buildDistance + speed * horizonSec  (clamped)
local function chaseRange(unitID, ud, horizonSec)
  local r = unitBuildDistance(unitID, ud) + unitMoveSpeed(ud) * (horizonSec or CHASE_SEC_CRAFT)
  if r < CHASE_MIN then return CHASE_MIN end
  if r > CHASE_MAX then return CHASE_MAX end
  return r
end

local function canReclaimWork(ud)
  if not ud then return false end
  -- Explicit false blocks; nil/true means reclaim-capable builder.
  if ud.canReclaim == false then return false end
  return ud.canReclaim or ud.canResurrect or (tonumber(ud.buildSpeed) or 0) > 0
end

local function isRezBot(ud)
  if UnitClass and UnitClass.isRezBot then return UnitClass.isRezBot(ud) end
  return ud and ud.canResurrect == true
end

local function isPhobos(ud)
  -- Vane/Mirren pack chassis — Legion Phobos (legcen).
  return ud and tostring(ud.name or "") == "legcen"
end

local function isSkirmisher(ud)
  if not ud then return false end
  local n = tostring(ud.name or "")
  -- Javelin / Lancer feel-anchor + other soft skirmishers that melt to Dgun.
  if n == "legjav" or n == "armpw" or n == "corak" or n == "legbal" then
    return true
  end
  -- Generic: mobile, not tanky, ranged, not builder/hero-structure.
  if (ud.speed or 0) <= 0 then return false end
  if ud.isBuilder or ud.canResurrect then return false end
  if ud.customParams and (ud.customParams.iscommander or ud.customParams.isscout) then
    return false
  end
  -- Light raiders with range but low HP.
  local hp = tonumber(ud.health) or 0
  local range = tonumber(ud.maxWeaponRange) or 0
  return hp > 0 and hp <= 900 and range >= 280 and (ud.speed or 0) >= 1.4
end

local function isCommanderOrDecoy(unitID, ud)
  if UnitClass and UnitClass.isCommanderOrDecoy and UnitClass.isCommanderOrDecoy(unitID, ud) then
    return true
  end
  -- Weapon-level: any unit with a Dgun / disintegrator (behavior-only heuristic).
  if not ud then
    local dID = Spring.GetUnitDefID(unitID)
    ud = dID and UnitDefs[dID]
  end
  if not ud or not ud.weapons then return false end
  for i = 1, #ud.weapons do
    local wd = WeaponDefs[ud.weapons[i].weaponDef]
    if wd then
      local wt = tostring(wd.type or ""):lower()
      local wn = tostring(wd.name or ""):lower()
      if wt == "dgun" or wn:find("dgun", 1, true) or wn:find("disintegrator", 1, true) then
        return true
      end
    end
  end
  return false
end

local function isLaserOrBeamerThreat(ud)
  if not ud then return false end
  local n = tostring(ud.name or ""):lower()
  -- Known BAR laser / beamer teeth (static + mobile).
  if n:find("beamer", 1, true) or n:find("llt", 1, true)
      or n == "armhlt" or n == "corhlt" or n == "legmg"
      or n:find("laser", 1, true) or n:find("heatray", 1, true)
      or n:find("lightning", 1, true) then
    return true
  end
  if not ud.weapons then return false end
  for i = 1, #ud.weapons do
    local wd = WeaponDefs[ud.weapons[i].weaponDef]
    if wd then
      local wt = tostring(wd.type or ""):lower()
      local wn = tostring(wd.name or ""):lower()
      if wt == "beamlaser" or wt == "laserCannon" or wt == "lasercannon"
          or wn:find("beam", 1, true) or wn:find("laser", 1, true)
          or wn:find("heatray", 1, true) or wn:find("lightning", 1, true) then
        return true
      end
    end
  end
  return false
end

local function isTreeFeature(featureID)
  local fdID = Spring.GetFeatureDefID(featureID)
  local fd = fdID and FeatureDefs[fdID]
  if not fd or not fd.reclaimable then return false end
  if fd.geoThermal then return false end
  local name = tostring(fd.name or ""):lower()
  local desc = tostring(fd.description or ""):lower()
  -- Rocks / metal piles / geo: reject.
  if name:find("rock", 1, true) or name:find("geo", 1, true)
      or desc:find("rock", 1, true) or desc:find("metal", 1, true) then
    return false
  end
  local metal = tonumber(fd.metal) or 0
  local energy = tonumber(fd.energy) or 0
  -- Engine default trees: energy > 0, metal ≈ 0. Also name treetype*.
  if name:find("tree", 1, true) or desc:find("tree", 1, true) then
    return energy > 0 and metal < 1
  end
  -- Fallback: pure energy feature with no metal (never rocks).
  return energy >= 50 and metal < 1
end

local function energyInDeficit(teamID)
  local cur, stor = Spring.GetTeamResources(teamID, "energy")
  cur = tonumber(cur) or 0
  stor = tonumber(stor) or 0
  if cur <= ENERGY_DEFICIT_ABS then return true end
  if stor > 0 and (cur / stor) <= ENERGY_DEFICIT_FRAC then return true end
  return false
end

local function issueOrder(unitID, cmdID, params, opts)
  if not unitID or not cmdID then return false end
  aiOrdering[unitID] = true
  local ok = pcall(Spring.GiveOrderToUnit, unitID, cmdID, params, opts or {})
  aiOrdering[unitID] = nil
  return ok
end

local function issueMove(unitID, x, z)
  if not CMD_MOVE or not x or not z then return false end
  local y = Spring.GetGroundHeight(x, z) or 0
  local ok = issueOrder(unitID, CMD_MOVE, { x, y, z }, {})
  if ok then
    Spring.SetUnitRulesParam(unitID, "va_behavior", "move", { public = true })
  end
  return ok
end

local function fleeFrom(unitID, tx, tz, dist)
  local x, _, z = unitPos(unitID)
  if not x or not tx then return false end
  local dx, dz = x - tx, z - tz
  local d = math.sqrt(dx * dx + dz * dz)
  if d < 1 then
    dx, dz, d = 1, 0, 1
  end
  local nx = x + (dx / d) * dist
  local nz = z + (dz / d) * dist
  local msx = Game.mapSizeX or 8192
  local msz = Game.mapSizeZ or 8192
  nx = math.max(32, math.min(msx - 32, nx))
  nz = math.max(32, math.min(msz - 32, nz))
  return issueMove(unitID, nx, nz)
end

local function findNearestWounded(teamID, fromX, fromZ, maxRange)
  local best, bestD2, bestFrac = nil, maxRange * maxRange, 2
  local units = Spring.GetTeamUnits(teamID) or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local hp, maxHp = Spring.GetUnitHealth(uid)
      hp, maxHp = tonumber(hp) or 0, tonumber(maxHp) or 0
      if maxHp > 0 and hp < maxHp * 0.96 then
        local ux, _, uz = unitPos(uid)
        if ux then
          local d2 = dist2(fromX, fromZ, ux, uz)
          local frac = hp / maxHp
          if d2 <= bestD2 and (frac < bestFrac or (frac == bestFrac and d2 < bestD2)) then
            best, bestD2, bestFrac = uid, d2, frac
          end
        end
      end
    end
  end
  return best
end

local function findNearestTree(fromX, fromZ, maxRange)
  local feats = Spring.GetFeaturesInCylinder(fromX, fromZ, maxRange) or {}
  local best, bestD2 = nil, maxRange * maxRange
  for i = 1, #feats do
    local fid = feats[i]
    if isTreeFeature(fid) then
      local fx, _, fz = Spring.GetFeaturePosition(fid)
      if fx then
        local d2 = dist2(fromX, fromZ, fx, fz)
        if d2 < bestD2 then
          best, bestD2 = fid, d2
        end
      end
    end
  end
  return best
end

local function findLaserThreat(teamID, fromX, fromZ, maxRange)
  local best, bestD2 = nil, maxRange * maxRange
  local bx, bz = nil, nil
  local units = Spring.GetAllUnits() or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local t = Spring.GetUnitTeam(uid)
      if t and t ~= teamID and not Spring.AreTeamsAllied(teamID, t) then
        local dID = Spring.GetUnitDefID(uid)
        local ud = dID and UnitDefs[dID]
        if isLaserOrBeamerThreat(ud) then
          local ux, _, uz = unitPos(uid)
          if ux then
            local d2 = dist2(fromX, fromZ, ux, uz)
            if d2 < bestD2 then
              best, bestD2, bx, bz = uid, d2, ux, uz
            end
          end
        end
      end
    end
  end
  return best, bx, bz
end

local function findNearestComOrDecoy(teamID, fromX, fromZ, maxRange)
  local best, bestD2, bx, bz = nil, maxRange * maxRange, nil, nil
  local units = Spring.GetAllUnits() or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local t = Spring.GetUnitTeam(uid)
      if t and t ~= teamID and not Spring.AreTeamsAllied(teamID, t) then
        local dID = Spring.GetUnitDefID(uid)
        local ud = dID and UnitDefs[dID]
        if isCommanderOrDecoy(uid, ud) then
          local ux, _, uz = unitPos(uid)
          if ux then
            local d2 = dist2(fromX, fromZ, ux, uz)
            if d2 < bestD2 then
              best, bestD2, bx, bz = uid, d2, ux, uz
            end
          end
        end
      end
    end
  end
  return best, bx, bz, bestD2 and math.sqrt(bestD2) or nil
end

local function findNearestCapturable(teamID, fromX, fromZ, maxRange)
  local best, bestD2 = nil, maxRange * maxRange
  local units = Spring.GetUnitsInCylinder(fromX, fromZ, maxRange) or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local t = Spring.GetUnitTeam(uid)
      if t and t ~= teamID and not Spring.AreTeamsAllied(teamID, t) then
        -- Living-shell occupation pads stay enemy marks. Capturing them mid-map
        -- plants a second Solarium-looking nest on the citadel guns.
        local shell = Spring.GetUnitRulesParam and Spring.GetUnitRulesParam(uid, "va_living_shell")
        if shell == 1 or shell == true or shell == "1" then
          -- skip
        else
          local dID = Spring.GetUnitDefID(uid)
          local ud = dID and UnitDefs[dID]
          -- Prefer capturable eco / statics over combat spam.
          if ud and (ud.isBuilding or ud.capturable ~= false) then
            local ux, _, uz = unitPos(uid)
            if ux then
              local d2 = dist2(fromX, fromZ, ux, uz)
              if d2 < bestD2 then
                best, bestD2 = uid, d2
              end
            end
          end
        end
      end
    end
  end
  return best
end

local function findNearestRezWreck(fromX, fromZ, maxRange)
  local feats = Spring.GetFeaturesInCylinder(fromX, fromZ, maxRange) or {}
  local best, bestD2, bestHero = nil, maxRange * maxRange, false
  for i = 1, #feats do
    local fid = feats[i]
    local fdID = Spring.GetFeatureDefID(fid)
    local fd = fdID and FeatureDefs[fdID]
    if fd and fd.reclaimable then
      local heroName = Spring.GetFeatureRulesParam and Spring.GetFeatureRulesParam(fid, "va_hero_wreck_name")
      local isHero = type(heroName) == "string" and heroName ~= ""
      local isWreck = false
      local n = tostring(fd.name or ""):lower()
      if isHero or n:find("corpse", 1, true) or n:find("wreck", 1, true) or n:find("dead", 1, true) then
        isWreck = true
      end
      -- Resurrectable corpses usually have metal and a unit-ish name.
      if isWreck or ((tonumber(fd.metal) or 0) >= 20 and not isTreeFeature(fid)) then
        local fx, _, fz = Spring.GetFeaturePosition(fid)
        if fx then
          local d2 = dist2(fromX, fromZ, fx, fz)
          if isHero and not bestHero then
            best, bestD2, bestHero = fid, d2, true
          elseif (not bestHero) and d2 < bestD2 then
            best, bestD2 = fid, d2
          elseif isHero and d2 < bestD2 then
            best, bestD2, bestHero = fid, d2, true
          end
        end
      end
    end
  end
  return best
end

-- Unclaimed Tenebrium shards / staked wrecks (va_tenebrium_amount > 0).
local function findNearestTnbShard(fromX, fromZ, maxRange)
  if not Spring.GetFeatureRulesParam then return nil end
  local feats = Spring.GetFeaturesInCylinder(fromX, fromZ, maxRange) or {}
  local best, bestD2, bestAmt = nil, maxRange * maxRange, 0
  for i = 1, #feats do
    local fid = feats[i]
    -- Parentheses: GetFeatureRulesParam can return nothing (not nil).
    local amt = tonumber((Spring.GetFeatureRulesParam(fid, "va_tenebrium_amount"))) or 0
    if amt > 0 then
      local fx, _, fz = Spring.GetFeaturePosition(fid)
      if fx then
        local d2 = dist2(fromX, fromZ, fx, fz)
        -- Prefer richer shards; break ties by distance.
        if amt > bestAmt or (amt == bestAmt and d2 < bestD2) then
          best, bestD2, bestAmt = fid, d2, amt
        end
      end
    end
  end
  return best
end

local function findNearestHeroWounded(teamID, fromX, fromZ, maxRange)
  local best, bestD2 = nil, maxRange * maxRange
  local units = Spring.GetTeamUnits(teamID) or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      -- GetUnitRulesParam returns nothing (not nil) when missing — wrap before type().
      local isHero = (Spring.GetUnitRulesParam(uid, "va_hero") or 0) == 1
        or (type((Spring.GetUnitRulesParam(uid, "va_hero_name"))) == "string")
      if isHero then
        local hp, maxHp = Spring.GetUnitHealth(uid)
        hp, maxHp = tonumber(hp) or 0, tonumber(maxHp) or 0
        if maxHp > 0 and hp < maxHp * 0.96 then
          local ux, _, uz = unitPos(uid)
          if ux then
            local d2 = dist2(fromX, fromZ, ux, uz)
            if d2 <= bestD2 then
              best, bestD2 = uid, d2
            end
          end
        end
      end
    end
  end
  return best
end

local REPAIR_BP_CLUSTER_R = 620 -- elmos: sum friendly build power in this bubble
local REPAIR_BP_MIN = 25 -- ignore empty "clusters"

local function unitBuildPower(unitID, ud)
  if not ud then
    local dID = Spring.GetUnitDefID(unitID)
    ud = dID and UnitDefs[dID]
  end
  if not ud then return 0 end
  if ud.isFactory then return 0 end
  local bp = tonumber(ud.buildSpeed) or 0
  if bp <= 0 then return 0 end
  -- Nano / rez / cons all count; passive structures with no build do not.
  if ud.isBuilder or ud.canResurrect or ud.canRepair then
    return bp
  end
  return bp > 0 and bp or 0
end

local function friendlyBuildPowerNear(teamID, x, z, radius)
  local r2 = radius * radius
  local sum = 0
  local units = Spring.GetTeamUnits(teamID) or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local ux, _, uz = unitPos(uid)
      if ux and dist2(x, z, ux, uz) <= r2 then
        local _, ud = defNameOf(uid)
        sum = sum + unitBuildPower(uid, ud)
      end
    end
  end
  return sum
end

-- Best repair zone = densest friendly build-power bubble (nanos / rez / cons).
local function bestRepairBpTarget(teamID, fromX, fromZ)
  local units = Spring.GetTeamUnits(teamID) or {}
  local bestScore, bx, bz = -1, nil, nil
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local _, ud = defNameOf(uid)
      local ownBp = unitBuildPower(uid, ud)
      if ownBp > 0 then
        local ux, _, uz = unitPos(uid)
        if ux then
          local cluster = friendlyBuildPowerNear(teamID, ux, uz, REPAIR_BP_CLUSTER_R)
          if cluster >= REPAIR_BP_MIN then
            local d = math.sqrt(dist2(fromX, fromZ, ux, uz))
            -- Prefer fat BP nests; soft distance falloff so far pads still win if richer.
            local score = cluster / (1 + d / 1100)
            if score > bestScore then
              bestScore, bx, bz = score, ux, uz
            end
          end
        end
      end
    end
  end
  if bx then return bx, bz, "repair_bp", bestScore end
  return nil, nil, nil, nil
end

local function nearestHealthyFriend(teamID, fromX, fromZ)
  local units = Spring.GetTeamUnits(teamID) or {}
  local bestD2, bx, bz = 1e18, nil, nil
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local hp, maxHp = Spring.GetUnitHealth(uid)
      hp, maxHp = tonumber(hp) or 0, tonumber(maxHp) or 0
      if maxHp > 0 and (hp / maxHp) >= 0.7 then
        local ux, _, uz = unitPos(uid)
        if ux then
          local d2 = dist2(fromX, fromZ, ux, uz)
          if d2 > 80 * 80 and d2 < bestD2 then
            bestD2, bx, bz = d2, ux, uz
          end
        end
      end
    end
  end
  if bx then return bx, bz, "friend" end
  return nil, nil, nil
end

local function retreatTarget(teamID, fromX, fromZ)
  -- Injury doctrine: run to repairs first, not the extract pad.
  -- 1) densest friendly build-power nest (nanos / rez / cons)
  -- 2) nearest healthy friend
  -- 3) deploy pad
  -- 4) extract (last resort — leave the fight only if nothing can heal you)
  local rx, rz, rkind = bestRepairBpTarget(teamID, fromX, fromZ)
  if rx then return rx, rz, rkind or "repair_bp" end

  local fx, fz, fkind = nearestHealthyFriend(teamID, fromX, fromZ)
  if fx then return fx, fz, fkind end

  -- the pad: one point, the company lands and lifts from it (va_pad_x/z, exfil gadget)
  local px = tonumber((Spring.GetGameRulesParam("va_pad_x")))
  local pz = tonumber((Spring.GetGameRulesParam("va_pad_z")))
  if px and pz and px > 0 and pz > 0 then
    return px, pz, "pad"
  end
  return nil, nil, nil
end

-- Frontline kite: clear the beam envelope with a short hop. Stay on the line —
-- no repair-pad bias (hurt-retreat owns "go get fixed").
-- Optional packCentroid pulls slightly toward the herd so the hop doesn't
-- scatter a Phobos pack into solo rabbit runs.
local function fleeFrontlineKite(unitID, threatX, threatZ, fleeDist, packCX, packCZ)
  local x, _, z = unitPos(unitID)
  if not x or not threatX then return false end
  local ax, az = x - threatX, z - threatZ
  local ad = math.sqrt(ax * ax + az * az)
  if ad < 1 then ax, az, ad = 1, 0, 1 end
  local nx = x + (ax / ad) * fleeDist
  local nz = z + (az / ad) * fleeDist
  if packCX and packCZ then
    -- 20% herd cohesion, 80% clear the envelope.
    nx = nx * 0.80 + packCX * 0.20
    nz = nz * 0.80 + packCZ * 0.20
  end
  local msx = Game.mapSizeX or 8192
  local msz = Game.mapSizeZ or 8192
  nx = math.max(32, math.min(msx - 32, nx))
  nz = math.max(32, math.min(msz - 32, nz))
  return issueMove(unitID, nx, nz)
end

local function packCentroidNear(unitID, teamID, sameDefID, radius)
  local x, _, z = unitPos(unitID)
  if not x or not sameDefID then return nil, nil end
  local mates = Spring.GetTeamUnitsByDefs(teamID, sameDefID) or {}
  local sx, sz, n = 0, 0, 0
  local r2 = radius * radius
  for i = 1, #mates do
    local uid = mates[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local ux, _, uz = unitPos(uid)
      if ux and dist2(x, z, ux, uz) <= r2 then
        sx, sz, n = sx + ux, sz + uz, n + 1
      end
    end
  end
  if n < 2 then return nil, nil end
  return sx / n, sz / n
end

local function thinkHurtRetreat(unitID, teamID, frame, ud, forceBail)
  if not ud or ud.isBuilder or ud.canResurrect or ud.isFactory then return false end
  if ud.isImmobile or (ud.speed or 0) <= 0 then return false end
  -- Don't yank constructors mid-craft; combat bodies only.
  if ud.isBuilder then return false end

  local hp, maxHp = Spring.GetUnitHealth(unitID)
  hp, maxHp = tonumber(hp) or 0, tonumber(maxHp) or 0
  if maxHp <= 0 then return false end
  local frac = hp / maxHp

  if hurtRetreating[unitID] then
    if frac >= HURT_SAFE_FRAC then
      hurtRetreating[unitID] = nil
      return false
    end
  elseif forceBail then
    -- Belief bail: limp back while hurt, but not when still mostly healthy.
    if frac > 0.72 then return false end
  elseif frac > HURT_HP_FRAC then
    return false
  end

  local prev = lastAssist[unitID]
  if prev and prev.kind == "hurt_retreat" and (frame - (prev.frame or 0)) < HURT_COOLDOWN then
    return true
  end

  local x, _, z = unitPos(unitID)
  if not x then return false end
  local tx, tz, kind = retreatTarget(teamID, x, z)
  if not tx then return false end

  -- Move partway toward safety (don't force full map trek every tick).
  local dx, dz = tx - x, tz - z
  local d = math.sqrt(dx * dx + dz * dz)
  if d < 120 then
    hurtRetreating[unitID] = nil
    return false
  end
  local step = math.min(520, d * 0.55)
  local nx = x + (dx / d) * step
  local nz = z + (dz / d) * step
  if issueMove(unitID, nx, nz) then
    hurtRetreating[unitID] = true
    Spring.SetUnitRulesParam(unitID, "va_behavior", "hurt_retreat", { public = true })
    Spring.SetUnitRulesParam(unitID, "va_retreat_kind", tostring(kind or ""), { public = true })
    Spring.SetUnitRulesParam(unitID, "va_retreat_x", math.floor(tx), { public = true })
    Spring.SetUnitRulesParam(unitID, "va_retreat_z", math.floor(tz), { public = true })
    lastAssist[unitID] = { kind = "hurt_retreat", frame = frame, toward = kind }
    return true
  end
  return false
end

local function isConstructor(ud)
  if not ud then return false end
  if ud.isFactory then return false end
  if ud.canResurrect then return true end
  if ud.isBuilder then return true end
  local bp = tonumber(ud.buildSpeed) or 0
  return bp > 0 and (ud.canRepair or ud.canReclaim or ud.canCapture)
end

local function thinkConstructor(unitID, teamID, frame, ud, allowBusy)
  -- allowBusy: anti-sticky re-eval may STOP a capture to soak Tnb.
  if not isIdle(unitID) and not allowBusy then return false end
  local x, _, z = unitPos(unitID)
  if not x then return false end

  local tnbChase = chaseRange(unitID, ud, CHASE_SEC_TNB)
  local craftChase = chaseRange(unitID, ud, CHASE_SEC_CRAFT)
  local treeChase = chaseRange(unitID, ud, CHASE_SEC_TREE)

  if canReclaimWork(ud) and CMD_RECLAIM then
    local shard = findNearestTnbShard(x, z, tnbChase)
    if shard then
      if not isIdle(unitID) and CMD_STOP then
        issueOrder(unitID, CMD_STOP, {}, {})
      end
      if issueOrder(unitID, CMD_RECLAIM, { shard }, {}) then
        Spring.SetUnitRulesParam(unitID, "va_behavior", "tnb_soak", { public = true })
        Spring.SetUnitRulesParam(unitID, "va_chase_r", math.floor(tnbChase), { public = true })
        lastAssist[unitID] = { kind = "tnb_soak", frame = frame }
        return true
      end
    end
  end

  if not isIdle(unitID) then return false end

  if ud.canCapture and CMD_CAPTURE then
    local prey = findNearestCapturable(teamID, x, z, craftChase)
    if prey then
      if issueOrder(unitID, CMD_CAPTURE, { prey }, {}) then
        Spring.SetUnitRulesParam(unitID, "va_behavior", "capture", { public = true })
        Spring.SetUnitRulesParam(unitID, "va_chase_r", math.floor(craftChase), { public = true })
        lastAssist[unitID] = { kind = "capture", frame = frame }
        return true
      end
    end
  end

  if (ud.canResurrect or CMD_RESURRECT) and CMD_RESURRECT then
    local wreck = findNearestRezWreck(x, z, craftChase)
    if wreck then
      if issueOrder(unitID, CMD_RESURRECT, { wreck }, {}) then
        Spring.SetUnitRulesParam(unitID, "va_behavior", "rez", { public = true })
        Spring.SetUnitRulesParam(unitID, "va_chase_r", math.floor(craftChase), { public = true })
        lastAssist[unitID] = { kind = "rez", frame = frame }
        return true
      end
    end
  end

  if ud.canRepair ~= false and CMD_REPAIR then
    local hero = findNearestHeroWounded(teamID, x, z, craftChase)
    if hero then
      if issueOrder(unitID, CMD_REPAIR, { hero }, {}) then
        Spring.SetUnitRulesParam(unitID, "va_behavior", "repair_hero", { public = true })
        Spring.SetUnitRulesParam(unitID, "va_chase_r", math.floor(craftChase), { public = true })
        lastAssist[unitID] = { kind = "repair_hero", frame = frame }
        return true
      end
    end
    local wounded = findNearestWounded(teamID, x, z, craftChase)
    if wounded then
      if issueOrder(unitID, CMD_REPAIR, { wounded }, {}) then
        Spring.SetUnitRulesParam(unitID, "va_behavior", "repair", { public = true })
        Spring.SetUnitRulesParam(unitID, "va_chase_r", math.floor(craftChase), { public = true })
        lastAssist[unitID] = { kind = "repair", frame = frame }
        return true
      end
    end
  end

  if isRezBot(ud) and energyInDeficit(teamID) and CMD_RECLAIM then
    local tree = findNearestTree(x, z, treeChase)
    if tree then
      if issueOrder(unitID, CMD_RECLAIM, { tree }, {}) then
        Spring.SetUnitRulesParam(unitID, "va_behavior", "eat_tree", { public = true })
        Spring.SetUnitRulesParam(unitID, "va_chase_r", math.floor(treeChase), { public = true })
        lastAssist[unitID] = { kind = "tree", frame = frame }
        return true
      end
    end
  end
  return false
end

local function actKite(unitID, teamID, frame, ud, kind)
  local x, _, z = unitPos(unitID)
  if not x then return false end
  local prev = lastAssist[unitID]
  if prev and (prev.kind == "skittish" or prev.kind == "dgun")
      and (frame - (prev.frame or 0)) < PHOBOS_SKITTISH_COOLDOWN then
    return true
  end

  if kind == "skirm" then
    local com, cx, cz, d = findNearestComOrDecoy(teamID, x, z, SKIRM_DGUN_BUBBLE + 120)
    if com and cx and d and d < SKIRM_DGUN_BUBBLE + 40 then
      if fleeFrom(unitID, cx, cz, SKIRM_FLEE_DIST) then
        Spring.SetUnitRulesParam(unitID, "va_behavior", "dgun_standoff", { public = true })
        lastAssist[unitID] = { kind = "dgun", frame = frame }
        return true
      end
    end
  end

  local threat, tx, tz = findLaserThreat(teamID, x, z, PHOBOS_THREAT_RANGE)
  if not threat or not tx then return false end
  local dist = math.sqrt(dist2(x, z, tx, tz))
  if dist > PHOBOS_THREAT_RANGE * 0.92 then return false end
  local dID = Spring.GetUnitDefID(unitID)
  local cx, cz = nil, nil
  local doctrine = Intent and Intent.profile(kind) or nil
  if doctrine and doctrine.flock then
    cx, cz = packCentroidNear(unitID, teamID, dID, 900)
  end
  if fleeFrontlineKite(unitID, tx, tz, PHOBOS_FLEE_DIST, cx, cz) then
    Spring.SetUnitRulesParam(unitID, "va_behavior", "skittish", { public = true })
    Spring.SetUnitRulesParam(unitID, "va_retreat_kind", "frontline_kite", { public = true })
    Spring.SetUnitRulesParam(unitID, "va_retreat_x", math.floor(tx), { public = true })
    Spring.SetUnitRulesParam(unitID, "va_retreat_z", math.floor(tz), { public = true })
    lastAssist[unitID] = { kind = "skittish", frame = frame }
    return true
  end
  return false
end

local function isDefenseTarget(ud)
  if not ud then return false end
  if ud.isBuilding or ud.isFactory then return true end
  local n = tostring(ud.name or ""):lower()
  if n:find("llt", 1, true) or n:find("beamer", 1, true) or n:find("hlt", 1, true)
      or n:find("turret", 1, true) or n:find("ferret", 1, true)
      or n:find("defender", 1, true) or n:find("punisher", 1, true)
      or n:find("guardian", 1, true) or n:find("annihilator", 1, true)
      or n:find("toaster", 1, true) or n:find("claw", 1, true)
      or n:find("rl", 1, true) or n:find("flak", 1, true)
      or n:find("sam", 1, true) or n:find("razor", 1, true) then
    return true
  end
  return false
end

local function actPush(unitID, teamID, frame, doctrine)
  if not isIdle(unitID) or not CMD_FIGHT then return false end
  local x, _, z = unitPos(unitID)
  if not x then return false end
  local preferDef = doctrine and doctrine.preferDefenses == true
  local bestD2 = (preferDef and 2200 * 2200) or (1400 * 1400)
  local bestDefD2 = bestD2
  local bx, bz, defX, defZ = nil, nil, nil, nil
  local units = Spring.GetAllUnits() or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local t = Spring.GetUnitTeam(uid)
      if t and t ~= teamID and not Spring.AreTeamsAllied(teamID, t) then
        local ux, _, uz = unitPos(uid)
        if ux then
          local d2 = dist2(x, z, ux, uz)
          if preferDef then
            local dID = Spring.GetUnitDefID(uid)
            local tud = dID and UnitDefs[dID]
            if isDefenseTarget(tud) and d2 < bestDefD2 then
              bestDefD2, defX, defZ = d2, ux, uz
            end
          end
          if d2 < bestD2 then
            bestD2, bx, bz = d2, ux, uz
          end
        end
      end
    end
  end
  if preferDef and defX then
    bx, bz = defX, defZ
  end
  if not bx then return false end
  local y = Spring.GetGroundHeight(bx, bz) or 0
  if issueOrder(unitID, CMD_FIGHT, { bx, y, bz }, {}) then
    local tag = (preferDef and defX) and "kiln_plod" or "push"
    Spring.SetUnitRulesParam(unitID, "va_behavior", tag, { public = true })
    lastAssist[unitID] = { kind = tag, frame = frame }
    return true
  end
  return false
end

local function heroIdFor(unitID)
  local hid = Spring.GetUnitRulesParam(unitID, "va_hero_id")
  if hid ~= nil and tostring(hid) ~= "" then return tostring(hid) end
  return nil
end

local function doctrineKindFor(unitID, ud, rez)
  local hid = heroIdFor(unitID)
  if hid and HeroDoctrine and HeroDoctrine.forHero then
    local row = HeroDoctrine.forHero(hid)
    if row and row.kind then return tostring(row.kind), hid end
  end
  if hid and Intent and Intent.profileForHero then
    local _, kind = Intent.profileForHero(hid, rez and "rez" or nil)
    if kind and kind ~= "default" then return kind, hid end
  end
  if rez then return "rez", hid end
  if isPhobos(ud) then return "phobos", hid end
  if isSkirmisher(ud) then return "skirm", hid end
  if isConstructor(ud) then return "constructor", hid end
  return "default", hid
end

local seededSquad = {} -- squadNode -> true after doctrine prior seeded once

local function ensureActorGraph(unitID, kind)
  if not field or not Belief then return nil end
  local teamNode = "team" .. tostring(playerTeam)
  local squadNode = "squad-" .. tostring(kind or "default")
  local actor = Belief.nodeIdForUnit(unitID)
  Belief.addNode(field, "world", nil, Belief.KIND_WORLD)
  Belief.addNode(field, teamNode, "world", Belief.KIND_WORLD)
  Belief.addNode(field, squadNode, teamNode, Belief.KIND_WORLD)
  Belief.addNode(field, actor, squadNode, Belief.KIND_ACTOR)
  local ordersGamma = (Intent and Intent.ORDERS_GAMMA) or 1.85
  local roles = {
    -- Orders: dissipative (not a 5s wall-clock). γ tunes click-stick feel.
    { "orders", Belief.MODE_DISSIPATIVE, ordersGamma, Belief.REDUCE_MEAN },
    { "hold", Belief.MODE_UNITARY, 0.05 },
    { "threat", Belief.MODE_DISSIPATIVE, 0.40, Belief.REDUCE_MAX },
    { "pain", Belief.MODE_DISSIPATIVE, 0.30, Belief.REDUCE_MEAN },
    { "pressure", Belief.MODE_DISSIPATIVE, 0.45, Belief.REDUCE_MAX },
    { "craft", Belief.MODE_DISSIPATIVE, 0.35, Belief.REDUCE_MEAN },
  }
  for i = 1, #roles do
    local r = roles[i]
    Belief.ensureRole(field, actor, r[1], r[2], r[3], r[4])
    Belief.ensureRole(field, squadNode, r[1], r[2], r[3], r[4])
  end
  -- Squad doctrine prior once: soak leans craft, frontline leans hold.
  if not seededSquad[squadNode] then
    seededSquad[squadNode] = true
    if kind == "rez" or kind == "constructor" then
      Belief.observe(field, squadNode, "craft", 0.7, 0.35)
      Belief.observe(field, squadNode, "hold", 0.55, 0.3)
    elseif kind == "skirm" then
      Belief.observe(field, squadNode, "hold", 0.35, 0.25)
    else
      Belief.observe(field, squadNode, "hold", 0.65, 0.35)
    end
  end
  return actor
end

local function senseUnit(unitID, teamID, frame, ud, kind)
  if not field or not Belief then return nil end
  local actor = ensureActorGraph(unitID, kind)
  if not actor then return nil end

  local hp, maxHp = Spring.GetUnitHealth(unitID)
  hp, maxHp = tonumber(hp) or 0, tonumber(maxHp) or 1
  local missing = (maxHp > 0) and (1 - (hp / maxHp)) or 0
  Belief.observe(field, actor, "pain", missing, 0.55)

  local x, _, z = unitPos(unitID)
  if not x then return actor end

  local threatV, threatEta = 0.15, 0.08
  local laser, lx, lz = findLaserThreat(teamID, x, z, PHOBOS_THREAT_RANGE)
  if laser and lx then
    local d = math.sqrt(dist2(x, z, lx, lz))
    local near = 1 - math.min(1, d / PHOBOS_THREAT_RANGE)
    threatV = 0.35 + near * 0.65
    if d <= PHOBOS_DANGER_RANGE then threatV = math.max(threatV, 0.85) end
    threatEta = 0.65
  end
  if kind == "skirm" then
    local com, cx, cz, d = findNearestComOrDecoy(teamID, x, z, SKIRM_DGUN_BUBBLE + 100)
    if com and d and d < SKIRM_DGUN_BUBBLE + 60 then
      threatV = math.max(threatV, 0.9)
      threatEta = 0.7
    end
  end
  Belief.observe(field, actor, "threat", threatV, threatEta)
  Belief.observe(field, actor, "pressure", threatV * 0.9, threatEta * 0.8)

  -- Orders decays via Tick(γ). Light reinforce only while a *player* pulse
  -- is still warm and a cmd remains queued — never boost AI kite/craft MOVEs.
  if queueLen(unitID) > 0 and Intent then
    local ov, oc = Belief.get(field, actor, "orders")
    if ov >= 0.55 or oc >= 0.22 then
      Belief.observe(field, actor, "orders",
        Intent.ORDERS_QUEUE_VALUE or 0.78,
        Intent.ORDERS_QUEUE_ETA or 0.14)
    end
  end

  if isConstructor(ud) or isRezBot(ud) then
    local craftV, craftEta = 0.2, 0.1
    local tnbChase = chaseRange(unitID, ud, CHASE_SEC_TNB)
    local craftChase = chaseRange(unitID, ud, CHASE_SEC_CRAFT)
    if canReclaimWork(ud) and findNearestTnbShard(x, z, tnbChase) then
      craftV, craftEta = 0.95, 0.7
    elseif ud.canResurrect and findNearestRezWreck(x, z, craftChase) then
      craftV, craftEta = 0.8, 0.55
    elseif findNearestHeroWounded(teamID, x, z, craftChase)
        or findNearestWounded(teamID, x, z, craftChase) then
      craftV, craftEta = 0.7, 0.5
    elseif ud.canCapture and findNearestCapturable(teamID, x, z, craftChase) then
      craftV, craftEta = 0.55, 0.4
    end
    Belief.observe(field, actor, "craft", craftV, craftEta)
  end

  return actor
end

local function readBeliefs(actor)
  if not field or not Belief or not actor then return {} end
  local function pack(role)
    local v, c = Belief.get(field, actor, role)
    return { value = v, confidence = c }
  end
  return {
    orders = pack("orders"),
    threat = pack("threat"),
    pain = pack("pain"),
    pressure = pack("pressure"),
    craft = pack("craft"),
    hold = pack("hold"),
  }
end

local function stampTelemetry(unitID, intent, beliefs, extra)
  Spring.SetUnitRulesParam(unitID, "va_intent", tostring(intent or "hold"), { public = true })
  local function pct(b)
    return math.floor(((b and b.value) or 0.5) * 100 + 0.5)
  end
  Spring.SetUnitRulesParam(unitID, "va_belief_threat", pct(beliefs.threat), { public = true })
  Spring.SetUnitRulesParam(unitID, "va_belief_pain", pct(beliefs.pain), { public = true })
  Spring.SetUnitRulesParam(unitID, "va_belief_orders", pct(beliefs.orders), { public = true })
  if type(extra) == "table" then
    if extra.shadowIntent then
      Spring.SetUnitRulesParam(unitID, "va_shadow_intent", tostring(extra.shadowIntent), { public = true })
    end
    if extra.policyMode then
      Spring.SetUnitRulesParam(unitID, "va_molecule_policy", tostring(extra.policyMode), { public = true })
    end
  end
end

local function refreshMoleculePolicyMode()
  if MoleculePolicy and MoleculePolicy.resolveMode then
    moleculePolicyMode = MoleculePolicy.resolveMode()
  else
    moleculePolicyMode = "off"
  end
  return moleculePolicyMode
end

local function doctrineForResolve(hid, kind)
  local doctrine = Intent.profile(kind)
  if hid and Intent.profileForHero then
    local ok, merged = pcall(Intent.profileForHero, hid, kind)
    if ok and type(merged) == "table" then
      doctrine = merged
    end
  end
  local mode = moleculePolicyMode or "off"
  if MoleculePolicy and MoleculePolicy.apply and hid then
    local applied, usedMode = MoleculePolicy.apply(doctrine, hid, mode)
    doctrine = applied or doctrine
    mode = usedMode or mode
  end
  return doctrine, mode
end

local function actIntent(unitID, teamID, frame, ud, intent, kind)
  if intent == "bail" then
    if thinkHurtRetreat(unitID, teamID, frame, ud, true) then return true end
    -- Builders/rez skip hurt-retreat; soft kite then keep crafting.
    if isConstructor(ud) or isRezBot(ud) then
      actKite(unitID, teamID, frame, ud, kind)
      return thinkConstructor(unitID, teamID, frame, ud, false)
    end
    return false
  end
  if intent == "kite" then
    return actKite(unitID, teamID, frame, ud, kind)
  end
  if intent == "craft" then
    local prev = lastAssist[unitID]
    local allowBusy = false
    if prev and prev.kind == "capture" then
      local last = lastCraftReeval[unitID] or 0
      if frame - last >= CRAFT_REEVAL_COOLDOWN then
        allowBusy = true
        lastCraftReeval[unitID] = frame
      end
    end
    return thinkConstructor(unitID, teamID, frame, ud, allowBusy)
  end
  if intent == "push" then
    local hid = heroIdFor(unitID)
    local doctrine = nil
    if Intent then
      doctrine = doctrineForResolve(hid, kind)
    elseif HeroDoctrine and HeroDoctrine.forHero and hid then
      local row = HeroDoctrine.forHero(hid)
      if row then
        doctrine = {
          preferDefenses = row.preferDefenses,
          allowBail = row.allowBail,
          allowKite = row.allowKite,
        }
      end
    end
    return actPush(unitID, teamID, frame, doctrine)
  end
  -- hold: respect player queue; clear stale tags when idle
  if isIdle(unitID) then
    Spring.SetUnitRulesParam(unitID, "va_behavior", "hold", { public = true })
  end
  return false
end

local function thinkAssistUnit(unitID, teamID, frame, ud, rez)
  local kind = unitDoctrine[unitID]
  if not kind then
    kind = doctrineKindFor(unitID, ud, rez)
    unitDoctrine[unitID] = kind
    Spring.SetUnitRulesParam(unitID, "va_doctrine", kind, { public = true })
  end

  -- Fallback if belief includes failed to load: legacy priority path.
  if not field or not Belief or not Intent then
    if thinkHurtRetreat(unitID, teamID, frame, ud) then return end
    if rez or isConstructor(ud) then
      thinkConstructor(unitID, teamID, frame, ud, false)
    elseif isPhobos(ud) then
      actKite(unitID, teamID, frame, ud, "phobos")
    elseif isSkirmisher(ud) then
      actKite(unitID, teamID, frame, ud, "skirm")
    elseif kind == "kiln" or kind == "siege_plod" then
      actPush(unitID, teamID, frame, Intent and Intent.profile(kind) or { preferDefenses = true })
    end
    return
  end

  -- Sensing already ran this wave in GameFrame; resolve against the shared field.
  local actor = Belief.nodeIdForUnit(unitID)
  local beliefs = readBeliefs(actor)
  local hid = heroIdFor(unitID)
  refreshMoleculePolicyMode()
  local doctrine, policyMode = doctrineForResolve(hid, kind)
  local prev = unitIntent[unitID] or "hold"
  local canCraft = rez or isConstructor(ud)
  local intent = Intent.resolve(beliefs, doctrine, prev, canCraft)
  local shadowIntent = nil
  -- shadow mode: live stays hand; log preferred intent under soft blend (no act change)
  if policyMode == "shadow" and MoleculePolicy and hid and Intent then
    local hand = Intent.profile(kind)
    if Intent.profileForHero then
      hand = Intent.profileForHero(hid, kind)
    end
    local der = MoleculePolicy.derivedFor and MoleculePolicy.derivedFor(hid) or nil
    if der then
      local softDoc = MoleculePolicy.blend(hand, der, MoleculePolicy.alpha and MoleculePolicy.alpha() or 0.28)
      shadowIntent = Intent.resolve(beliefs, softDoc, prev, canCraft)
    end
  end
  unitIntent[unitID] = intent
  stampTelemetry(unitID, intent, beliefs, {
    shadowIntent = shadowIntent,
    policyMode = policyMode,
  })
  actIntent(unitID, teamID, frame, ud, intent, kind)
end

local function resolvePlayerTeam()
  if Util and Util.resolvePlayerTeam then return Util.resolvePlayerTeam() end
  -- Prefer campaign seed player team; fall back to team 0.
  local fromRules = tonumber((Spring.GetGameRulesParam("va_player_team")))
  if fromRules and Spring.GetTeamInfo(fromRules, false) then
    return fromRules
  end
  local opts = Spring.GetModOptions() or {}
  local fromOpt = tonumber(opts.va_player_team or opts.playerteam)
  if fromOpt and Spring.GetTeamInfo(fromOpt, false) then
    return fromOpt
  end
  return 0
end

function gadget:Initialize()
  local opts = Spring.GetModOptions() or {}
  if opts.va_unit_behavior ~= nil then
    enabled = truthy(opts.va_unit_behavior)
  end
  -- Stay off during pure autoplay harness (it has its own order rig).
  if truthy(opts.va_autoplay) then
    enabled = false
  end
  refreshMoleculePolicyMode()
  local ok, teamOrErr = pcall(resolvePlayerTeam)
  playerTeam = (ok and teamOrErr) or 0
  if enabled then
    Spring.Echo("VA_UNIT_BEHAVIOR_ARMED team=" .. tostring(playerTeam)
      .. " period=" .. tostring(THINK_PERIOD)
      .. " scope=named_heroes+rez_bots"
      .. " belief=" .. tostring(field ~= nil and Intent ~= nil)
      .. " orders_g=" .. tostring(Intent and Intent.ORDERS_GAMMA or "?")
      .. " bp_chase=buildDist+speed*sec(tnb=" .. tostring(CHASE_SEC_TNB)
      .. ",craft=" .. tostring(CHASE_SEC_CRAFT)
      .. ",tree=" .. tostring(CHASE_SEC_TREE) .. ")"
      .. " intents=bail>kite>craft>push>hold"
      .. " hero_doc=" .. tostring(HeroDoctrine ~= nil)
      .. " molecule_policy=" .. tostring(moleculePolicyMode)
      .. " molecule_mod=" .. tostring(MoleculePolicy ~= nil))
  else
    Spring.Echo("VA_UNIT_BEHAVIOR_OFF")
  end
end

function gadget:GameStart()
  local ok, teamOrErr = pcall(resolvePlayerTeam)
  playerTeam = (ok and teamOrErr) or playerTeam or 0
end

function gadget:UnitDestroyed(unitID)
  lastAssist[unitID] = nil
  hurtRetreating[unitID] = nil
  aiOrdering[unitID] = nil
  unitIntent[unitID] = nil
  unitDoctrine[unitID] = nil
  lastCraftReeval[unitID] = nil
end

function gadget:UnitTaken(unitID)
  lastAssist[unitID] = nil
  hurtRetreating[unitID] = nil
  aiOrdering[unitID] = nil
  unitIntent[unitID] = nil
  unitDoctrine[unitID] = nil
  lastCraftReeval[unitID] = nil
end

-- Player combat orders: pulse dissipative `orders` belief (γ tunes stick).
function gadget:UnitCommand(unitID, _unitDefID, unitTeam, cmdID, _cmdParams, _cmdOptions, _cmdTag)
  if unitTeam ~= playerTeam then return end
  if aiOrdering[unitID] then return end
  if not PLAYER_COMBAT_CMDS[cmdID] then return end
  if field and Belief and Intent then
    local kind = unitDoctrine[unitID] or "default"
    local actor = ensureActorGraph(unitID, kind)
    if actor then
      Belief.observe(field, actor, "orders",
        Intent.ORDERS_PULSE_VALUE or 1.0,
        Intent.ORDERS_PULSE_ETA or 0.92)
    end
  end
end

function gadget:GameFrame(frame)
  if not enabled or frame < 45 then return end
  if frame - lastThink < THINK_PERIOD then return end
  local dt = (frame - lastThink) / 30
  if dt < 0.05 then dt = THINK_PERIOD / 30 end
  lastThink = frame

  if field and Belief then
    Belief.tick(field, dt)
  end

  local teamID = playerTeam
  local units = Spring.GetTeamUnits(teamID) or {}
  local assist = {}
  for i = 1, #units do
    local unitID = units[i]
    if Spring.ValidUnitID(unitID) and not Spring.GetUnitIsDead(unitID) then
      local _, ud = defNameOf(unitID)
      if ud then
        local isHero = (Spring.GetUnitRulesParam(unitID, "va_hero") or 0) == 1
        local rez = isRezBot(ud)
        -- Pack grunts stay manual. Only named heroes + rez bots get assist AI.
        if isHero or rez then
          assist[#assist + 1] = { unitID, ud, rez }
        end
      end
    end
  end

  -- Sense all first so propagate sees a coherent wave of observations.
  if field and Belief and Intent then
    for i = 1, #assist do
      local unitID, ud, rez = assist[i][1], assist[i][2], assist[i][3]
      local kind = unitDoctrine[unitID]
      if not kind then
        kind = doctrineKindFor(unitID, ud, rez)
        unitDoctrine[unitID] = kind
        Spring.SetUnitRulesParam(unitID, "va_doctrine", kind, { public = true })
      end
      senseUnit(unitID, teamID, frame, ud, kind)
    end
    Belief.propagate(field, 0.15)
  end

  for i = 1, #assist do
    local unitID, ud, rez = assist[i][1], assist[i][2], assist[i][3]
    thinkAssistUnit(unitID, teamID, frame, ud, rez)
  end
end
