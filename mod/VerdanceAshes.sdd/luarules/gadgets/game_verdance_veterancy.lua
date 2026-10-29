if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Quantum Veterancy",
    desc = "Combat XP: HP early, speed/range mid, attack speed late. Dual-φ saturators.",
    author = "Verdance",
    date = "2026-09-06",
    license = "GPL v2 or later",
    layer = 2,
    enabled = true,
  }
end

-- one shared options table for the rules params set every tick (a fresh { public = true } per call is garbage)
local PUBLIC = { public = true }

if not gadgetHandler:IsSyncedCode() then
  -- Forward rank-up juice to LuaUI playfeel widgets.
  function gadget:Initialize()
    gadgetHandler:AddSyncAction("VERDANCE_VET_RANK", function(_, unitID, prev, rank, x, y, z, mults)
      if Script.LuaUI and Script.LuaUI.VerdanceVetRank then
        Script.LuaUI.VerdanceVetRank(unitID, prev, rank, x, y, z, mults)
      end
    end)
  end
  function gadget:Shutdown()
    gadgetHandler:RemoveSyncAction("VERDANCE_VET_RANK")
  end
  return
end

--[[
  Quantum parametric combat veterancy
  -----------------------------------
  Engine XP (damage/kills) remains the source of truth.
  We own the *reward shape* by writing absolute stats from baselines.

  Phase (HUD / rank eigenvalues):
    θ = xp / (xp + φ)

  φ saturators (early → late):
    φ_hp  = 1/φ      → HP early
    φ_spd = 1        → move speed mid-early
    φ_rng = √φ       → weapon range mid
    φ_as  = φ        → attack speed late

    hpMult     = 1 + B·φ · xp/(xp + φ_hp)      ≤ HP_CAP
    speedMult  = 1 + B·0.70 · xp/(xp + φ_spd)  ≤ SPEED_CAP
    rangeMult  = 1 + B·0.85 · xp/(xp + φ_rng)  ≤ RANGE_CAP
    reloadMult = 1 / (1 + B · xp/(xp + φ_as))  ≥ RELOAD_FLOOR

  Scope: all player-team units except factories.
    - weapons → HP / reload / range
    - mobile  → move speed (MoveCtrl)
  Heroes: baseline captured AFTER campaign heroHpMult stamp (second layer).
]]

local PHI = (1 + math.sqrt(5)) * 0.5 -- 1.6180339887...
local PHI_HP = 1 / PHI               -- 0.618 — early survivability
local PHI_SPD = 1.0                  -- mid-early mobility
local PHI_RNG = math.sqrt(PHI)       -- ~1.272 — mid reach
local PHI_AS = PHI                   -- 1.618 — late bite
local B = 0.55                       -- shared veterancy budget
local HP_CAP = 1.90
local SPEED_CAP = 1.22               -- speed is strong; keep modest
local RANGE_CAP = 1.28
local RELOAD_FLOOR = 0.55            -- never more than ~1.82× RoF

local RANK_BLOODED = 1 / (PHI * PHI) -- θ ≥ ~0.382
local RANK_HARDENED = 1 / PHI        -- θ ≥ ~0.618
local RANK_CRACKED = 1 - (1 / (PHI * PHI)) -- ~0.764

local enabled = true
local playerTeam = 0
local EXP_GRADE = 0.02
local POLL_PERIOD = 30 -- 1s @ 30fps; safety net if UnitExperience misses

local spMoveCtrlGetTag = Spring.MoveCtrl and Spring.MoveCtrl.GetTag

-- unitID -> baseline + last applied mults
local vet = {}

local Util = nil
do
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_util.lua")
  if ok and type(mod) == "table" then Util = mod end
end
local function truthy(v)
  return Util and Util.truthy and Util.truthy(v) or (v == true or v == 1)
end
local function resolvePlayerTeam()
  if Util and Util.resolvePlayerTeam then return Util.resolvePlayerTeam() end
  return 0
end

local function getMovetype(ud)
  if not ud then return false end
  if ud.canFly or ud.isAirUnit then
    if ud.isHoveringAirUnit then return 1 end -- gunship
    return 0 -- fixedwing
  end
  if not ud.isImmobile then return 2 end -- ground/sea
  return false
end

local function unitHasWeapons(ud)
  if not ud then return false end
  local weapons = ud.weapons
  return type(weapons) == "table" and weapons[1] ~= nil
end

local function isPlayerVetUnit(unitID, unitDefID)
  if not Spring.ValidUnitID(unitID) or Spring.GetUnitIsDead(unitID) then return false end
  local team = Spring.GetUnitTeam(unitID)
  if team ~= playerTeam then return false end
  local dID = unitDefID or Spring.GetUnitDefID(unitID)
  local ud = dID and UnitDefs[dID]
  if not ud or ud.isFactory then return false end
  -- All non-factory player units: armed get combat stats; mobile get speed.
  return unitHasWeapons(ud) or (not ud.isImmobile)
end

local function captureWeaponStats(unitID, ud)
  local reloads, ranges = {}, {}
  if not ud or not ud.weapons then return reloads, ranges end
  for i = 1, #ud.weapons do
    local rt, rng = nil, nil
    if Spring.GetUnitWeaponState then
      rt = Spring.GetUnitWeaponState(unitID, i, "reloadTime")
      rng = Spring.GetUnitWeaponState(unitID, i, "range")
    end
    if WeaponDefs then
      local w = ud.weapons[i]
      local wdID = w and (w.weaponDef or w.weapondef)
      local wd = wdID and WeaponDefs[wdID]
      if wd then
        if not rt or rt <= 0 then rt = tonumber(wd.reload) or tonumber(wd.reloadTime) end
        if not rng or rng <= 0 then rng = tonumber(wd.range) end
      end
    end
    if type(rt) == "number" and rt > 0 then reloads[i] = rt end
    if type(rng) == "number" and rng > 0 then ranges[i] = rng end
  end
  return reloads, ranges
end

local function captureMoveBaseline(unitID, ud)
  local movetype = getMovetype(ud)
  if movetype == false then return nil end
  local speed = tonumber(ud and ud.speed) or 0
  local reverse = 0
  local turnRate = tonumber(ud and ud.turnRate) or 0
  local maxAcc = tonumber(ud and (ud.maxAcc or ud.acceleration)) or 0
  local maxDec = tonumber(ud and (ud.maxDec or ud.brakeRate)) or 0
  local fromMoveType = false
  if Spring.GetUnitMoveTypeData then
    local md = Spring.GetUnitMoveTypeData(unitID)
    if type(md) == "table" then
      if tonumber(md.maxSpeed) and md.maxSpeed > 0 then
        speed = md.maxSpeed
        fromMoveType = true
      elseif tonumber(md.maxWantedSpeed) and md.maxWantedSpeed > 0 then
        speed = md.maxWantedSpeed
        fromMoveType = true
      end
      if tonumber(md.maxReverseSpeed) then reverse = md.maxReverseSpeed end
      if tonumber(md.turnRate) and md.turnRate > 0 then turnRate = md.turnRate end
      if tonumber(md.accRate) and md.accRate > 0 then maxAcc = md.accRate end
      if tonumber(md.decRate) and md.decRate > 0 then maxDec = md.decRate end
      if tonumber(md.maxAcc) and md.maxAcc > 0 then maxAcc = md.maxAcc end
      if tonumber(md.maxDec) and md.maxDec > 0 then maxDec = md.maxDec end
    end
  end
  -- BAR/Recoil MoveCtrl maxSpeed uses UnitDef.speed units (elmos/sec) as-is.
  -- Do NOT divide by 30 — that made veterans crawl (~30× too slow).
  if speed <= 0 then return nil end
  if maxAcc <= 0 then maxAcc = speed * 0.15 end
  if maxDec <= 0 then maxDec = speed * 0.15 end
  return {
    movetype = movetype,
    speed = speed,
    reverse = reverse,
    turnRate = turnRate,
    maxAcc = maxAcc,
    maxDec = maxDec,
    fromMoveType = fromMoveType,
  }
end

local function captureBaseline(unitID, unitDefID)
  local dID = unitDefID or Spring.GetUnitDefID(unitID)
  local ud = dID and UnitDefs[dID]
  if not ud or ud.isFactory then return nil end

  local _, maxH = 0, 0
  if Spring.GetUnitHealth then
    _, maxH = Spring.GetUnitHealth(unitID)
  end
  local baseMaxH = tonumber(maxH) or 0
  if baseMaxH <= 0 then
    baseMaxH = tonumber(ud.health) or tonumber(ud.maxDamage) or 0
  end

  local hasWpn = unitHasWeapons(ud)
  local reloads, ranges = {}, {}
  if hasWpn then
    reloads, ranges = captureWeaponStats(unitID, ud)
  end
  local move = captureMoveBaseline(unitID, ud)

  if baseMaxH <= 0 and not hasWpn and not move then return nil end

  return {
    defID = dID,
    baseMaxH = baseMaxH,
    baseReload = reloads,
    baseRange = ranges,
    move = move,
    hasWeapons = hasWpn,
    lastHpMult = 1,
    lastReloadMult = 1,
    lastRangeMult = 1,
    lastSpeedMult = 1,
    lastRank = "green",
    sawXp = 0,
  }
end

local function ensureVet(unitID, unitDefID)
  local rec = vet[unitID]
  if rec then return rec end
  if not isPlayerVetUnit(unitID, unitDefID) then return nil end
  rec = captureBaseline(unitID, unitDefID)
  if not rec then return nil end
  vet[unitID] = rec
  return rec
end

local function phaseTheta(xp)
  xp = math.max(0, tonumber(xp) or 0)
  return xp / (xp + PHI)
end

local function computeMults(xp)
  xp = math.max(0, tonumber(xp) or 0)
  local hpBonus = B * PHI * (xp / (xp + PHI_HP))
  local spdBonus = B * 0.70 * (xp / (xp + PHI_SPD))
  local rngBonus = B * 0.85 * (xp / (xp + PHI_RNG))
  local asBonus = B * (xp / (xp + PHI_AS))
  local hpMult = math.min(HP_CAP, 1 + hpBonus)
  local speedMult = math.min(SPEED_CAP, 1 + spdBonus)
  local rangeMult = math.min(RANGE_CAP, 1 + rngBonus)
  local reloadMult = 1 / (1 + asBonus)
  if reloadMult < RELOAD_FLOOR then reloadMult = RELOAD_FLOOR end
  local theta = phaseTheta(xp)
  local aHp = math.cos(math.pi * theta * 0.5)
  aHp = aHp * aHp
  local aAs = math.sin(math.pi * theta * 0.5)
  aAs = aAs * aAs
  local rank = "green"
  if theta >= RANK_CRACKED then
    rank = "cracked"
  elseif theta >= RANK_HARDENED then
    rank = "hardened"
  elseif theta >= RANK_BLOODED then
    rank = "blooded"
  end
  return hpMult, reloadMult, speedMult, rangeMult, theta, aHp, aAs, rank
end

local function applyMoveSpeed(unitID, rec, speedMult)
  local move = rec.move
  if not move or not move.speed or move.speed <= 0 then return false end
  -- Compose pack × field × vet via shared mobility (does not wipe field stride).
  if GG and GG.VA_MobilitySetVet then
    return GG.VA_MobilitySetVet(unitID, speedMult, move) and true or false
  end
  if spMoveCtrlGetTag and spMoveCtrlGetTag(unitID) ~= nil then return false end
  Spring.SetUnitRulesParam(unitID, "va_vet_speed_mult", speedMult, PUBLIC)
  if GG and GG.VA_MobilityApply then
    return GG.VA_MobilityApply(unitID, { move = move }) and true or false
  end
  return false
end

local function applyWeaponRange(unitID, rec, rangeMult)
  if not rec.baseRange or not Spring.SetUnitWeaponState then return false end
  local maxR = 0
  local any = false
  for wpn, baseR in pairs(rec.baseRange) do
    local r = baseR * rangeMult
    if pcall(Spring.SetUnitWeaponState, unitID, wpn, "range", r) then
      any = true
      if r > maxR then maxR = r end
    end
  end
  if any and maxR > 0 and Spring.SetUnitMaxRange then
    pcall(Spring.SetUnitMaxRange, unitID, maxR)
  end
  return any
end

local function applyVeterancy(unitID, rec, xp, reason)
  if not rec then return end
  xp = math.max(0, tonumber(xp) or 0)
  local hpMult, reloadMult, speedMult, rangeMult, theta, aHp, aAs, rank = computeMults(xp)

  Spring.SetUnitRulesParam(unitID, "va_vet_xp", xp, PUBLIC)
  Spring.SetUnitRulesParam(unitID, "va_vet_theta", theta, PUBLIC)
  Spring.SetUnitRulesParam(unitID, "va_vet_hp_mult", hpMult, PUBLIC)
  Spring.SetUnitRulesParam(unitID, "va_vet_reload_mult", reloadMult, PUBLIC)
  Spring.SetUnitRulesParam(unitID, "va_vet_speed_mult", speedMult, PUBLIC)
  Spring.SetUnitRulesParam(unitID, "va_vet_range_mult", rangeMult, PUBLIC)
  Spring.SetUnitRulesParam(unitID, "va_vet_rank", rank, PUBLIC)
  Spring.SetUnitRulesParam(unitID, "va_vet_a_hp", aHp, PUBLIC)
  Spring.SetUnitRulesParam(unitID, "va_vet_a_as", aAs, PUBLIC)

  local hpChanged = math.abs(hpMult - rec.lastHpMult) > 0.002
  local asChanged = math.abs(reloadMult - rec.lastReloadMult) > 0.002
  local spdChanged = math.abs(speedMult - rec.lastSpeedMult) > 0.002
  local rngChanged = math.abs(rangeMult - rec.lastRangeMult) > 0.002

  if hpChanged and rec.baseMaxH > 0 and Spring.SetUnitMaxHealth and Spring.GetUnitHealth then
    local curH, curMax = Spring.GetUnitHealth(unitID)
    local targetMax = rec.baseMaxH * hpMult
    if targetMax > 0 then
      local frac = 1
      if curMax and curMax > 0 and curH then
        frac = math.max(0, math.min(1, curH / curMax))
      end
      pcall(Spring.SetUnitMaxHealth, unitID, targetMax)
      if hpMult >= rec.lastHpMult and Spring.SetUnitHealth then
        pcall(Spring.SetUnitHealth, unitID, targetMax * frac)
      end
      rec.lastHpMult = hpMult
    end
  end

  if asChanged and Spring.SetUnitWeaponState and rec.baseReload then
    for wpn, baseRt in pairs(rec.baseReload) do
      pcall(Spring.SetUnitWeaponState, unitID, wpn, "reloadTime", baseRt * reloadMult)
    end
    rec.lastReloadMult = reloadMult
  end

  if rngChanged then
    applyWeaponRange(unitID, rec, rangeMult)
    rec.lastRangeMult = rangeMult
  end

  if spdChanged then
    applyMoveSpeed(unitID, rec, speedMult)
    rec.lastSpeedMult = speedMult
  end

  if rank ~= rec.lastRank then
    local prev = tostring(rec.lastRank or "green")
    Spring.Echo(string.format(
      "VA_VET_RANK unit=%s %s→%s xp=%.3f θ=%.3f hp=×%.2f spd=×%.2f rng=×%.2f reload=×%.2f%s",
      tostring(unitID), prev, rank, xp, theta,
      hpMult, speedMult, rangeMult, reloadMult,
      reason and (" [" .. tostring(reason) .. "]") or ""))
    rec.lastRank = rank
    -- Playfeel: unsynced juice + selected-unit chip can hear rank-ups.
    local x, y, z = Spring.GetUnitPosition(unitID)
    if SendToUnsynced and rank ~= "green" then
      SendToUnsynced(
        "VERDANCE_VET_RANK",
        unitID,
        prev,
        rank,
        x or 0,
        y or 0,
        z or 0,
        string.format("%.2f|%.2f|%.2f|%.2f", hpMult, speedMult, rangeMult, reloadMult))
    end
    if Spring.SpawnCEG and x then
      -- Best-effort sparkle; missing CEG is fine.
      pcall(Spring.SpawnCEG, "sanctumflare", x, (y or 0) + 18, z, 0, 1, 0, 40)
    end
  elseif reason == "force" and (hpChanged or asChanged or spdChanged or rngChanged) then
    Spring.Echo(string.format(
      "VA_VET_APPLY unit=%s xp=%.3f θ=%.3f hp=×%.2f spd=×%.2f rng=×%.2f reload=×%.2f rank=%s",
      tostring(unitID), xp, theta, hpMult, speedMult, rangeMult, reloadMult, rank))
  end

  rec.sawXp = xp
end

local function refreshUnit(unitID, reason)
  if not enabled then return end
  if not isPlayerVetUnit(unitID) then return end
  local rec = ensureVet(unitID)
  if not rec then return end
  -- If hero stamp grew maxHP after our first capture, re-baseline once when xp still ~0.
  if Spring.GetUnitHealth then
    local _, liveMax = Spring.GetUnitHealth(unitID)
    if liveMax and rec.baseMaxH > 0 then
      local projected = rec.baseMaxH * (rec.lastHpMult or 1)
      if (rec.sawXp or 0) < 0.05 and liveMax > rec.baseMaxH * 1.02 then
        rec.baseMaxH = liveMax
        local dID = Spring.GetUnitDefID(unitID)
        local ud = dID and UnitDefs[dID]
        if ud then
          rec.baseReload, rec.baseRange = captureWeaponStats(unitID, ud)
          rec.move = captureMoveBaseline(unitID, ud)
          rec.hasWeapons = unitHasWeapons(ud)
        end
      elseif liveMax > projected * 1.08 and (rec.sawXp or 0) < 0.05 then
        rec.baseMaxH = liveMax / math.max(rec.lastHpMult, 1)
      end
    end
  end
  local xp = 0
  if Spring.GetUnitExperience then
    xp = Spring.GetUnitExperience(unitID) or 0
  end
  applyVeterancy(unitID, rec, xp, reason)
end

-- Public hook for campaign hero stamp / rez recover.
GG = GG or {}
GG.VA_VetRefresh = function(unitID)
  if not unitID then return end
  -- Drop cached baseline so we re-capture after hero HP mult.
  vet[unitID] = nil
  refreshUnit(unitID, "force")
end

GG.VA_VetRebaseline = function(unitID)
  if not unitID or not Spring.ValidUnitID(unitID) then return end
  vet[unitID] = nil
  local rec = ensureVet(unitID)
  if rec then
    local xp = 0
    if Spring.GetUnitExperience then xp = Spring.GetUnitExperience(unitID) or 0 end
    applyVeterancy(unitID, rec, xp, "force")
  end
end

function gadget:Initialize()
  local opts = Spring.GetModOptions() or {}
  if opts.va_veterancy ~= nil then
    enabled = truthy(opts.va_veterancy)
  end
  local okTeam, teamOrErr = pcall(resolvePlayerTeam)
  playerTeam = (okTeam and teamOrErr) or 0

  if Spring.SetExperienceGrade then
    pcall(Spring.SetExperienceGrade, EXP_GRADE)
  end

  if enabled then
    Spring.Echo(string.format(
      "VA_VET_ARMED φ=%.4f φ_hp=%.4f φ_spd=%.4f φ_rng=%.4f φ_as=%.4f B=%.2f caps hp=%.2f spd=%.2f rng=%.2f reloadFloor=%.2f team=%s",
      PHI, PHI_HP, PHI_SPD, PHI_RNG, PHI_AS, B, HP_CAP, SPEED_CAP, RANGE_CAP, RELOAD_FLOOR, tostring(playerTeam)))
  else
    Spring.Echo("VA_VET_OFF")
  end
end

function gadget:GameStart()
  local ok, teamOrErr = pcall(resolvePlayerTeam)
  playerTeam = (ok and teamOrErr) or playerTeam or 0
end

function gadget:UnitFinished(unitID, unitDefID, unitTeam)
  if not enabled or unitTeam ~= playerTeam then return end
  if not isPlayerVetUnit(unitID, unitDefID) then return end
  vet[unitID] = nil
  ensureVet(unitID, unitDefID)
  refreshUnit(unitID, "finished")
end

local bornAt = {}   -- unitID -> frame; XP set in a unit's first second is a carried seed, not combat
local paced = {}    -- unitID -> the XP we last left it at (the engine reports only grade crossings)

function gadget:UnitCreated(unitID, unitDefID, unitTeam)
  bornAt[unitID] = Spring.GetGameFrame()
  if not enabled or unitTeam ~= playerTeam then return end
  if not isPlayerVetUnit(unitID, unitDefID) then return end
end

function gadget:UnitDestroyed(unitID)
  vet[unitID] = nil
  bornAt[unitID] = nil
  paced[unitID] = nil
end

function gadget:UnitTaken(unitID, unitDefID, oldTeam, newTeam)
  if newTeam ~= playerTeam then
    vet[unitID] = nil
  end
end

function gadget:UnitGiven(unitID, unitDefID, newTeam, oldTeam)
  if newTeam == playerTeam and isPlayerVetUnit(unitID, unitDefID) then
    vet[unitID] = nil
    refreshUnit(unitID, "given")
  end
end

-- The company learns at half the engine's rate (owner call, 2026-10-24: everyone levelled too
-- fast). Its aircraft earn half again as much as that: the same as pricing them a third cheaper
-- in the engine's damage-for-XP sum (owner call, 2026-10-23; the pack's starting XP takes the
-- same third off in tools/verdance/company/pack_xp.py). Seeds (XP set as a unit is placed, the
-- carried veterancy) are left alone.
local FIELD_XP_RATE = 0.5
local AIR_XP_BONUS = 0.5
local pacing = false

function gadget:UnitExperience(unitID, unitDefID, unitTeam, xp, oldXp)
  if not enabled then return end
  if unitTeam ~= playerTeam then return end
  local seeded = (Spring.GetGameFrame() - (bornAt[unitID] or -999)) < 30
  if pacing then
    -- our own write echoing back
  elseif seeded or not Spring.SetUnitExperience then
    paced[unitID] = xp
  else
    -- everything earned since we last set it, not just the increment that crossed the grade
    local from = paced[unitID] or oldXp or 0
    if xp > from then
      local ud = UnitDefs[unitDefID]
      local rate = FIELD_XP_RATE * ((ud and ud.canFly) and (1 + AIR_XP_BONUS) or 1)
      xp = from + (xp - from) * rate
      pacing = true
      Spring.SetUnitExperience(unitID, xp)
      pacing = false
    end
    paced[unitID] = xp
  end
  if not isPlayerVetUnit(unitID, unitDefID) then return end
  local rec = ensureVet(unitID, unitDefID)
  if not rec then return end
  applyVeterancy(unitID, rec, xp, nil)
end

function gadget:GameFrame(frame)
  if not enabled or frame < 60 then return end
  if frame % POLL_PERIOD ~= 0 then return end

  local units = Spring.GetTeamUnits(playerTeam) or {}
  local slice = frame / POLL_PERIOD
  for i = 1, #units do
    local uid = units[i]
    if uid % 8 == slice % 8 then
      if isPlayerVetUnit(uid) then
        local rec = vet[uid]
        local isHero = (Spring.GetUnitRulesParam(uid, "va_hero") or 0) == 1
        if not rec then
          refreshUnit(uid, "poll_init")
        elseif isHero then
          refreshUnit(uid, nil)
        else
          local xp = 0
          if Spring.GetUnitExperience then xp = Spring.GetUnitExperience(uid) or 0 end
          if math.abs(xp - (rec.sawXp or 0)) >= EXP_GRADE * 0.5 then
            applyVeterancy(uid, rec, xp, nil)
          end
        end
      end
    end
  end
end
