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
  local moved = GG.VA_PadToCompany and GG.VA_PadToCompany()
  Spring.Echo("VA_AUTOPILOT_EXTRACT reason=" .. reason .. " frame=" .. f .. " padMoved=" .. tostring(moved == true))
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

function gadget:Initialize()
  local ok, m = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  mission = ok and type(m) == "table" and m or nil
  playerTeam = tonumber(mission and mission.balance and mission.balance.playerTeamID) or 0
  Spring.Echo("VA_AUTOPILOT armed team=" .. playerTeam .. " cap=" .. CAP_FRAMES .. " settle=" .. SETTLE_FRAMES
    .. " mission=" .. tostring(mission and mission.missionId))
end

function gadget:GameFrame(f)
  if extracted or f % 30 ~= 11 then return end
  if rp("va_terminal") == 1 then extracted = true; return end
  if rp("va_objective_complete") == 1 and not doneAt then
    doneAt = f
    Spring.Echo("VA_AUTOPILOT objective complete frame=" .. f)
  end
  if doneAt and f - doneAt >= SETTLE_FRAMES then return leave("objective", f) end
  if rp("va_objective_failed") == 1 then return leave("objective_failed", f) end
  if f >= CAP_FRAMES then return leave("clock", f) end
  if not doneAt and f % NUDGE_EVERY < 30 then nudge() end
end
