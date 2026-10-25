if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Autopilot",
    desc = "A BARbarian AI plays the company's seat; this decides when the company leaves",
    author = "Verdance tools",
    date = "2026-10-24",
    license = "GPL v2 or later",
    layer = 5,        -- after the campaign and exfil gadgets have registered their GG hooks
    enabled = true,
  }
end

-- Modoptions (tools/autopilot_campaign_v1.py writes them into the startscript):
--   va_autopilot=1            the company's team is an AI (BARb); a spectator hosts
--   va_autopilot_speed=N      sim speed (default 8)
--   va_autopilot_minutes=M    game minutes before the company leaves regardless (default 15)
--   va_autopilot_settle=S     game seconds to hold after the objective completes (default 40)
-- The AI fights; it knows nothing of the campaign. This rig only: unpauses, nudges idle units
-- toward the wound, and calls the extraction (pad moves to the company: extract anywhere).

local opts = (Spring.GetModOptions and Spring.GetModOptions()) or {}
if tostring(opts.va_autopilot) ~= "1" then return false end

local function num(k, d) local v = tonumber(opts[k]); if v == nil then return d end; return v end
local SPEED = num("va_autopilot_speed", 8)
local CAP_FRAMES = math.floor(num("va_autopilot_minutes", 15) * 60 * 30)
local SETTLE_FRAMES = math.floor(num("va_autopilot_settle", 40) * 30)
local NUDGE_EVERY = 600
-- test rig only: va_autopilot_force_complete=M marks the objective done at game minute M
local FORCE_AT = num("va_autopilot_force_complete", 0) > 0 and math.floor(num("va_autopilot_force_complete", 0) * 1800) or nil

if not gadgetHandler:IsSyncedCode() then
  local started, sped, echoed = false, false, false
  function gadget:GameStart() started = true end
  function gadget:Update()
    if not started then return end
    local _, _, paused = Spring.GetGameSpeed()
    if paused then
      pcall(Spring.SendCommands, "pause 0")
      if not echoed then echoed = true; Spring.Echo("VA_AUTOPILOT unpause") end
    end
    if not sped and (Spring.GetGameFrame() or 0) > 2 then
      sped = true
      pcall(Spring.SendCommands, "setmaxspeed " .. SPEED, "setminspeed " .. SPEED)
      Spring.Echo("VA_AUTOPILOT speed=" .. SPEED)
    end
  end
  return
end

local mission = nil
local playerTeam = 0
local doneAt, extracted = nil, false
local tx, tz = nil, nil

local function rp(k) return tonumber((Spring.GetGameRulesParam(k))) or 0 end

local function target()
  if tx or not mission then return tx, tz end
  local zid = (mission.objective and mission.objective.targetZoneId) or mission.targetZoneId
  if zid and GG.VA_ZoneAnchor then tx, tz = GG.VA_ZoneAnchor(zid) end
  return tx, tz
end

local function leave(reason, f)
  if extracted then return end
  if not GG.VA_ExfilCmd then
    if f % 300 == 0 then Spring.Echo("VA_AUTOPILOT waiting: exfil gadget has no command hook") end
    return
  end
  extracted = true
  Spring.Echo("VA_AUTOPILOT_EXTRACT reason=" .. reason .. " frame=" .. f .. " pad=" .. tostring(Spring.GetGameRulesParam("va_pad_zone")))
  GG.VA_ExfilCmd("extract:home")
end

local function nudge()
  local x, z = target()
  if not x then return end
  local idle = {}
  for _, uid in ipairs(Spring.GetTeamUnits(playerTeam) or {}) do
    local dID = Spring.GetUnitDefID(uid)
    local ud = dID and UnitDefs[dID]
    if ud and (ud.speed or 0) > 0 and not ud.isBuilding and not (ud.isBuilder and not ud.canAttack) then
      local q = Spring.GetUnitCommands(uid, 1)
      if q == nil or #q == 0 then idle[#idle + 1] = uid end
    end
  end
  if #idle == 0 then return end
  local y = Spring.GetGroundHeight(x, z) or 0
  Spring.GiveOrderToUnitArray(idle, CMD.FIGHT, { x, y, z }, 0)
  Spring.Echo("VA_AUTOPILOT nudge idle=" .. #idle)
end

-- The objective's named hero (mission.objective.rezHeroId): raise that wreck with whoever can rez.
local function rezWreck()
  local hid = mission and mission.objective and mission.objective.rezHeroId
  if not hid then return end
  local fid
  for _, f in ipairs(Spring.GetAllFeatures() or {}) do
    if tostring(Spring.GetFeatureRulesParam(f, "va_hero_wreck") or "") == tostring(hid) then fid = f; break end
  end
  if not fid then return end
  -- only once the ground is clear: armed enemies near the wreck turn a rescue into a feeding
  local wx, _, wz = Spring.GetFeaturePosition(fid)
  local myAlly = select(6, Spring.GetTeamInfo(playerTeam, false))
  local threats = 0
  for _, u in ipairs(Spring.GetUnitsInCylinder(wx, wz, 700) or {}) do
    local t = Spring.GetUnitTeam(u)
    local ud = UnitDefs[Spring.GetUnitDefID(u) or -1]
    if t and select(6, Spring.GetTeamInfo(t, false)) ~= myAlly and t ~= Spring.GetGaiaTeamID()
        and ud and ud.weapons and #ud.weapons > 0 and not Spring.GetUnitIsDead(u) then
      threats = threats + 1
    end
  end
  local total, down = rp("va_objective_total"), rp("va_objective_destroyed")
  local crippled = total > 0 and down / total >= 0.6
  if threats > 0 and not (crippled and threats <= 12) then
    Spring.Echo("VA_AUTOPILOT rez waiting hero=" .. tostring(hid) .. " threats=" .. threats)
    return
  end
  local rez, crit = {}, {}
  for _, uid in ipairs(Spring.GetTeamUnits(playerTeam) or {}) do
    local ud = UnitDefs[Spring.GetUnitDefID(uid) or -1]
    if ud and ud.canResurrect then
      local q = Spring.GetUnitCommands(uid, 1)
      local busy = q and q[1] and q[1].id == CMD.RESURRECT and q[1].params and q[1].params[1] == fid + Game.maxUnits
      if not busy then
        if (tonumber((Spring.GetUnitRulesParam(uid, "va_hero_critical"))) or 0) == 1 then crit[#crit + 1] = uid
        else rez[#rez + 1] = uid end
      end
    end
  end
  if #rez == 0 then rez = crit end
  if #rez == 0 then return end
  Spring.GiveOrderToUnitArray(rez, CMD.RESURRECT, { fid + Game.maxUnits }, 0)
  Spring.Echo("VA_AUTOPILOT rez hero=" .. tostring(hid) .. " feature=" .. fid .. " builders=" .. #rez)
end

-- Once the job is done: everyone mobile walks to the pad (the company's zone, extract anywhere).
local function regroup()
  local px, pz = tonumber((Spring.GetGameRulesParam("va_pad_x"))), tonumber((Spring.GetGameRulesParam("va_pad_z")))
  if not px then return end
  local mob = {}
  for _, uid in ipairs(Spring.GetTeamUnits(playerTeam) or {}) do
    local ud = UnitDefs[Spring.GetUnitDefID(uid) or -1]
    if ud and (ud.speed or 0) > 0 and not ud.isBuilding then mob[#mob + 1] = uid end
  end
  if #mob > 0 then
    Spring.GiveOrderToUnitArray(mob, CMD.MOVE, { px, Spring.GetGroundHeight(px, pz) or 0, pz }, 0)
    Spring.Echo("VA_AUTOPILOT regroup units=" .. #mob .. " pad=" .. tostring(Spring.GetGameRulesParam("va_pad_zone")))
  end
end

function gadget:Initialize()
  local ok, m = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  mission = ok and type(m) == "table" and m or nil
  playerTeam = tonumber(mission and mission.balance and mission.balance.playerTeamID) or 0
  Spring.Echo("VA_AUTOPILOT armed team=" .. playerTeam .. " cap=" .. CAP_FRAMES .. " settle=" .. SETTLE_FRAMES
    .. " mission=" .. tostring(mission and mission.missionId))
end

function gadget:GameFrame(f)
  if f % 900 == 13 then
    local lm = ""
    if Spring.GetLuaMemUsage then
      local a, b, c, d, e, g = Spring.GetLuaMemUsage()
      lm = " luamem=" .. tostring(a) .. "," .. tostring(b) .. "," .. tostring(c) .. "," .. tostring(d) .. "," .. tostring(e) .. "," .. tostring(g)
    end
    Spring.Echo("VA_AUTOPILOT_MEM frame=" .. f .. " synced_kb=" .. tostring(gcinfo and gcinfo() or "?") .. lm
      .. " units=" .. #(Spring.GetAllUnits() or {}) .. " features=" .. #(Spring.GetAllFeatures() or {})
      .. " projectiles=" .. tostring(Spring.GetProjectilesInRectangle and #(Spring.GetProjectilesInRectangle(0, 0, Game.mapSizeX, Game.mapSizeZ) or {}) or "?"))
  end
  if extracted or f % 30 ~= 11 then return end
  if rp("va_terminal") == 1 then extracted = true; return end
  if FORCE_AT and f >= FORCE_AT and rp("va_objective_complete") ~= 1 and GG.VA_ObjectiveComplete then
    Spring.Echo("VA_AUTOPILOT test: forcing objective complete frame=" .. f)
    GG.VA_ObjectiveComplete("test_forced")
  end
  if rp("va_objective_complete") == 1 and not doneAt then
    doneAt = f
    Spring.Echo("VA_AUTOPILOT objective complete frame=" .. f)
    regroup()
  end
  if not doneAt and f % 600 == 311 then rezWreck() end
  if doneAt and (f - doneAt) % 450 == 0 and f > doneAt then regroup() end
  if doneAt and f - doneAt >= SETTLE_FRAMES then
    -- leave once most of the company stands on the pad, or after three settles regardless
    local px, pz, pr = rp("va_pad_x"), rp("va_pad_z"), math.max(560, rp("va_pad_r"))
    local mob, on = 0, 0
    for _, uid in ipairs(Spring.GetTeamUnits(playerTeam) or {}) do
      local ud = UnitDefs[Spring.GetUnitDefID(uid) or -1]
      if ud and (ud.speed or 0) > 0 and not ud.isBuilding then
        mob = mob + 1
        local x, _, z = Spring.GetUnitPosition(uid)
        if x and ((x - px) ^ 2 + (z - pz) ^ 2) <= (pr * 1.6) ^ 2 then on = on + 1 end
      end
    end
    if mob == 0 or on / mob >= 0.7 or f - doneAt >= SETTLE_FRAMES * 3 then
      Spring.Echo("VA_AUTOPILOT on pad " .. on .. "/" .. mob)
      return leave("objective", f)
    end
  end
  if rp("va_objective_failed") == 1 then return leave("objective_failed", f) end
  if f >= CAP_FRAMES then return leave("clock", f) end
  if not doneAt and f % NUDGE_EVERY < 30 then nudge() end
end
