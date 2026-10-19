local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Constructor Craft XP",
    desc = "Golden-ratio craft XP: capture > rez > build > repair; reclaim=0. Rewards % build power + slight build range.",
    author = "Verdance",
    date = "2026-09-06",
    license = "GPL v2 or later",
    layer = 3,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  return
end

--[[
  Craft XP ladder (golden ratio φ ≈ 1.618):

    reclaim : repair : build : rez : capture
         0  :   φ^0  :  φ^1  : φ^2 :  φ^3

  Capture sits above rez. Rez is intentionally a step down from "full".
  Repair is the unit base (bumped up). Reclaim never pays craft XP.

  Rewards (percentage of unit baseline):
    buildPower  *= 1 + 0.35 * craftXp   (cap 1.80)
    buildRange  *= 1 + 0.12 * craftXp   (cap 1.25)
]]

local PHI = (1 + math.sqrt(5)) * 0.5 -- 1.6180339887...
local PHI2 = PHI * PHI               -- 2.618...
local PHI3 = PHI2 * PHI              -- 4.236...

-- Repair is the geometric unit. Others scale by φ^n.
local RATE_REPAIR = 0.015            -- /s while repairing (medium, bumped up)
local RATE_BUILD = RATE_REPAIR * PHI
local RATE_REZ_TICK = RATE_REPAIR * PHI2
local RATE_RECLAIM = 0

-- Completion bonuses ≈ 6s of that tier's tick rate (rez slightly lean).
local BONUS_REZ = RATE_REZ_TICK * 5.5
local BONUS_CAPTURE = RATE_REPAIR * PHI3 * 6
local BONUS_BUILD_FINISH = RATE_BUILD * 3

local BP_PER_XP = 0.35
local BP_CAP = 1.80
local RANGE_PER_XP = 0.12
local RANGE_CAP = 1.25

local enabled = true
local playerTeam = 0
local lastThink = -999999
local THINK_PERIOD = 15 -- 0.5s @ 30fps
local DT = THINK_PERIOD / 30

local CMD_REPAIR = (CMD and CMD.REPAIR) or 40
local CMD_RECLAIM = (CMD and CMD.RECLAIM) or 90
local CMD_RESURRECT = (CMD and CMD.RESURRECT) or 125
local CMD_CAPTURE = (CMD and CMD.CAPTURE) or 130

-- unitID -> { craftXp, baseBp, baseRange, lastBpMult, lastRangeMult }
local craft = {}
local lastNodeClaimed = 0

local function truthy(v)
  if v == true or v == 1 then return true end
  if type(v) == "string" then
    v = v:lower()
    return v == "1" or v == "true" or v == "yes" or v == "on"
  end
  return false
end

local function resolvePlayerTeam()
  -- Parentheses force a single value; bare GetGameRulesParam can return nothing.
  local fromRules = tonumber((Spring.GetGameRulesParam("va_player_team")))
  if fromRules and Spring.GetTeamInfo(fromRules, false) then return fromRules end
  local opts = Spring.GetModOptions() or {}
  local fromOpt = tonumber(opts.va_player_team or opts.playerteam)
  if fromOpt and Spring.GetTeamInfo(fromOpt, false) then return fromOpt end
  return 0
end

local function isPlayerConstructor(unitID, ud)
  if not Spring.ValidUnitID(unitID) or Spring.GetUnitIsDead(unitID) then return false end
  local team = Spring.GetUnitTeam(unitID)
  if team ~= playerTeam then return false end
  if not ud then
    local dID = Spring.GetUnitDefID(unitID)
    ud = dID and UnitDefs[dID]
  end
  if not ud then return false end
  if ud.isFactory then return false end
  local bp = tonumber(ud.buildSpeed) or 0
  if bp <= 0 and not ud.isBuilder and not ud.canResurrect and not ud.canRepair and not ud.canReclaim then
    return false
  end
  -- Builders / rezbots / anything with worker time.
  return (ud.isBuilder == true) or (bp > 0) or ud.canResurrect or ud.canRepair
end

local function ensureCraft(unitID, ud)
  local rec = craft[unitID]
  if rec then return rec end
  if not ud then
    local dID = Spring.GetUnitDefID(unitID)
    ud = dID and UnitDefs[dID]
  end
  if not ud then return nil end
  local baseBp = tonumber(ud.buildSpeed) or 0
  local baseRange = tonumber(ud.buildDistance) or 0
  -- Prefer live params if engine already mutated them.
  if Spring.GetUnitBuildParams then
    local live = Spring.GetUnitBuildParams(unitID, "buildDistance")
      or Spring.GetUnitBuildParams(unitID, "buildRange")
    if type(live) == "number" and live > 0 then baseRange = live end
  end
  if Spring.GetUnitCurrentBuildPower then
    local liveBp = Spring.GetUnitCurrentBuildPower(unitID)
    if type(liveBp) == "number" and liveBp > 0 and baseBp <= 0 then baseBp = liveBp end
  end
  rec = {
    craftXp = tonumber((Spring.GetUnitRulesParam(unitID, "va_craft_xp"))) or 0,
    baseBp = baseBp,
    baseRange = baseRange,
    lastBpMult = 1,
    lastRangeMult = 1,
  }
  craft[unitID] = rec
  return rec
end

local function applyCraftRewards(unitID, rec)
  if not rec then return end
  local xp = math.max(0, tonumber(rec.craftXp) or 0)
  local bpMult = math.min(BP_CAP, 1 + BP_PER_XP * xp)
  local rangeMult = math.min(RANGE_CAP, 1 + RANGE_PER_XP * xp)

  Spring.SetUnitRulesParam(unitID, "va_craft_xp", xp, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_craft_bp_mult", bpMult, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_craft_range_mult", rangeMult, { public = true })

  if rec.baseBp > 0 and Spring.SetUnitBuildSpeed and math.abs(bpMult - rec.lastBpMult) > 0.001 then
    -- Keep repair/rez/reclaim speeds in proportion to build speed.
    local bp = rec.baseBp * bpMult
    pcall(Spring.SetUnitBuildSpeed, unitID, bp, bp, bp * 0.15, bp, bp, bp)
    rec.lastBpMult = bpMult
  end

  if rec.baseRange > 0 and Spring.SetUnitBuildParams and math.abs(rangeMult - rec.lastRangeMult) > 0.001 then
    local dist = rec.baseRange * rangeMult
    local ok = pcall(Spring.SetUnitBuildParams, unitID, "buildDistance", dist)
    if not ok then
      pcall(Spring.SetUnitBuildParams, unitID, "buildRange", dist)
    end
    rec.lastRangeMult = rangeMult
  end
end

local function addCraftXp(unitID, amount, reason)
  if not amount or amount <= 0 then return end
  if not isPlayerConstructor(unitID) then return end
  local rec = ensureCraft(unitID)
  if not rec then return end
  rec.craftXp = (tonumber(rec.craftXp) or 0) + amount
  applyCraftRewards(unitID, rec)
  -- Intentionally do NOT bleed into Spring combat XP. Combat veterancy
  -- (game_verdance_veterancy.lua) owns the engine XP → HP/RoF curve.
  -- Craft stays on va_craft_* rules params + build speed/range only.
  if reason and amount >= 0.05 then
    Spring.Echo(string.format("VA_CRAFT_XP unit=%s +%.3f (%s) total=%.3f bp=%.2f range=%.2f",
      tostring(unitID), amount, tostring(reason), rec.craftXp,
      rec.lastBpMult, rec.lastRangeMult))
  end
end

local function grantCaptureSplash(amount)
  local units = Spring.GetTeamUnits(playerTeam) or {}
  local n = 0
  for i = 1, #units do
    local uid = units[i]
    if isPlayerConstructor(uid) then
      addCraftXp(uid, amount, "capture")
      n = n + 1
    end
  end
  if n > 0 then
    Spring.Echo("VA_CRAFT_CAPTURE_SPLASH constructors=" .. tostring(n)
      .. " each=+" .. string.format("%.3f", amount)
      .. " ratio=φ^3")
  end
end

local function workerTaskKind(unitID)
  if not Spring.GetUnitWorkerTask then return nil, nil end
  local cmdID, targetID = Spring.GetUnitWorkerTask(unitID)
  if not cmdID then return nil, nil end
  if cmdID == CMD_REPAIR then return "repair", targetID end
  if cmdID == CMD_RECLAIM then return "reclaim", targetID end
  if cmdID == CMD_RESURRECT then return "rez", targetID end
  if cmdID == CMD_CAPTURE then return "capture_cmd", targetID end
  if cmdID < 0 then return "build", targetID end
  return nil, nil
end

local function tickWorker(unitID)
  local kind = workerTaskKind(unitID)
  if not kind then return end
  if kind == "reclaim" then
    -- Explicitly nothing. Rocks, trees, wrecks — no craft XP.
    return
  elseif kind == "repair" then
    addCraftXp(unitID, RATE_REPAIR * DT, nil)
  elseif kind == "build" then
    addCraftXp(unitID, RATE_BUILD * DT, nil)
  elseif kind == "rez" then
    addCraftXp(unitID, RATE_REZ_TICK * DT, nil)
  elseif kind == "capture_cmd" then
    -- Engine capture-command tick; campaign node claim still pays the big splash.
    addCraftXp(unitID, RATE_REPAIR * PHI3 * DT * 0.35, nil)
  end
end

-- Public hook: campaign re-seeds va_craft_xp on spawn between rounds.
GG = GG or {}
GG.VA_CraftRefresh = function(unitID)
  if not unitID or not Spring.ValidUnitID(unitID) then return end
  craft[unitID] = nil
  local rec = ensureCraft(unitID)
  if rec then
    applyCraftRewards(unitID, rec)
  end
end

function gadget:Initialize()
  local opts = Spring.GetModOptions() or {}
  if opts.va_craft_xp ~= nil then
    enabled = truthy(opts.va_craft_xp)
  end
  if truthy(opts.va_autoplay) then
    -- Still allow craft XP during autoplay tests unless explicitly off.
  end
  -- pcall: never let craft XP abort the entire LuaRules load (no units / no Tnb).
  local okTeam, teamOrErr = pcall(resolvePlayerTeam)
  playerTeam = (okTeam and teamOrErr) or 0
  local okClaim, claimOrErr = pcall(function()
    return tonumber((Spring.GetGameRulesParam("va_node_claimed"))) or 0
  end)
  lastNodeClaimed = (okClaim and claimOrErr) or 0
  if enabled then
    Spring.Echo(string.format(
      "VA_CRAFT_XP_ARMED φ=%.4f rates repair=%.4f build=%.4f rezTick=%.4f reclaim=0 bonuses rez=%.3f capture=%.3f",
      PHI, RATE_REPAIR, RATE_BUILD, RATE_REZ_TICK, BONUS_REZ, BONUS_CAPTURE))
  else
    Spring.Echo("VA_CRAFT_XP_OFF")
  end
end

function gadget:GameStart()
  local ok, teamOrErr = pcall(resolvePlayerTeam)
  playerTeam = (ok and teamOrErr) or playerTeam or 0
end

function gadget:UnitDestroyed(unitID)
  craft[unitID] = nil
end

function gadget:UnitTaken(unitID, unitDefID, oldTeam, newTeam)
  if newTeam ~= playerTeam then
    craft[unitID] = nil
  end
end

function gadget:UnitGiven(unitID, unitDefID, newTeam, oldTeam)
  if newTeam == playerTeam and isPlayerConstructor(unitID) then
    ensureCraft(unitID)
  end
end

function gadget:UnitFinished(unitID, unitDefID, teamID)
  -- Pay build-finish bonus to constructors assisting this buildee.
  if teamID ~= playerTeam then return end
  local bx, _, bz = Spring.GetUnitPosition(unitID)
  if not bx then return end
  local units = Spring.GetTeamUnits(playerTeam) or {}
  for i = 1, #units do
    local uid = units[i]
    if uid ~= unitID and isPlayerConstructor(uid) then
      local kind, target = workerTaskKind(uid)
      if kind == "build" and (target == unitID or target == nil) then
        local ux, _, uz = Spring.GetUnitPosition(uid)
        if ux then
          local d2 = (ux - bx) * (ux - bx) + (uz - bz) * (uz - bz)
          if target == unitID or d2 <= (420 * 420) then
            addCraftXp(uid, BONUS_BUILD_FINISH, "build_finish")
          end
        end
      end
    end
  end
end

function gadget:UnitCreated(unitID, unitDefID, teamID, builderID)
  -- Resurrection: rezbot as builder, unit not a factory product mid-build from lab.
  if not builderID or builderID <= 0 then return end
  if not isPlayerConstructor(builderID) then return end
  local bDefID = Spring.GetUnitDefID(builderID)
  local bud = bDefID and UnitDefs[bDefID]
  if not bud or not (bud.canResurrect or (bud.customParams and bud.customParams.canresurrect == "1")) then
    return
  end
  -- Factory builds also pass builderID; skip factories.
  if bud.isFactory then return end
  -- Newly rez'd units usually aren't "being built" by a factory nanoframe path.
  local beingBuilt = Spring.GetUnitIsBeingBuilt and Spring.GetUnitIsBeingBuilt(unitID)
  if beingBuilt then
    -- Could be a fresh nanoframe from a con; only pay rez bonus if worker task was resurrect.
    local kind = workerTaskKind(builderID)
    if kind ~= "rez" then return end
  end
  addCraftXp(builderID, BONUS_REZ, "rez_complete")
end

function gadget:UnitCmdDone(unitID, unitDefID, teamID, cmdID, cmdParams, cmdOpts, cmdTag)
  if teamID ~= playerTeam then return end
  if not isPlayerConstructor(unitID) then return end
  if cmdID == CMD_RESURRECT then
    addCraftXp(unitID, BONUS_REZ * 0.35, "rez_cmd_done") -- light; UnitCreated pays the main chunk
  elseif cmdID == CMD_CAPTURE then
    addCraftXp(unitID, BONUS_CAPTURE * 0.45, "capture_cmd_done")
  end
end

function gadget:GameFrame(frame)
  if not enabled or frame < 45 then return end
  if frame - lastThink < THINK_PERIOD then return end
  lastThink = frame

  -- Campaign node claim splash (capture > rez).
  local claimed = tonumber((Spring.GetGameRulesParam("va_node_claimed"))) or 0
  if claimed == 1 and lastNodeClaimed ~= 1 then
    grantCaptureSplash(BONUS_CAPTURE)
  end
  lastNodeClaimed = claimed

  local units = Spring.GetTeamUnits(playerTeam) or {}
  for i = 1, #units do
    local uid = units[i]
    if isPlayerConstructor(uid) then
      ensureCraft(uid)
      tickWorker(uid)
    end
  end
end
