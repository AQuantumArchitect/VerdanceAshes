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
--
-- BARb fights; it knows nothing of the campaign. This rig only, on top of it:
--   nudge      idle units fight toward the wound
--   rescue     a hero's wreck on the field gets a squad: the four nearest guns go to it, and once
--              the ground is quiet, the rez bots raise it (critical rez bots only if no other)
--   departure  the objective done, failed, or the clock out: everyone walks to the real pad
--              (va_pad_x/z/r), and the company leaves once all of it stands there (or after
--              three settles, for stuck units)
--   leaving    through the HUD when there is one: this publishes va_autopilot_leave, the rig
--              player widget (gui_verdance_rig_player.lua, which says VA_RIG:hud at start)
--              presses EXTRACT and confirms the manifest; if the HUD has not ended the sortie
--              HUD_WAIT later, VA_AUTOPILOT_HUD_SILENT and the autopilot extracts by itself.
--              A run without LuaUI (the Windows headless rig) extracts directly.
-- Units the rig gives an order to are held (AllowCommand) so BARb's next update does not undo it;
-- everyone else stays BARb's.

local opts = (Spring.GetModOptions and Spring.GetModOptions()) or {}
if tostring(opts.va_autopilot) ~= "1" then return false end

local function num(k, d) local v = tonumber(opts[k]); if v == nil then return d end; return v end
local SPEED = num("va_autopilot_speed", 8)
local CAP_FRAMES = math.floor(num("va_autopilot_minutes", 15) * 60 * 30)
local SETTLE_FRAMES = math.floor(num("va_autopilot_settle", 40) * 30)
local NUDGE_EVERY = 600
local RESCUE_EVERY = 600
local HUD_WAIT = 20 * 30
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
local extracted = false
local departureAt, departureWhy = nil, nil  -- the company was told to go to the pad
local leaveAt, leaveWhy = nil, nil          -- ...and to leave (the HUD's turn)
local hudPresent = false                    -- the rig player widget said VA_RIG:hud
local tx, tz = nil, nil
local held = {}                             -- unitID -> true: the rig's order stands
local issuing = false

local function rp(k) return tonumber((Spring.GetGameRulesParam(k))) or 0 end

-- ---------------------------------------------------------------- orders that BARb keeps its hands off
local function order(units, cmd, params, hold)
  if hold then for _, uid in ipairs(units) do held[uid] = true end end
  issuing = true
  local ok, err = pcall(Spring.GiveOrderToUnitArray, units, cmd, params, 0)
  issuing = false
  if not ok then Spring.Echo("VA_AUTOPILOT order failed: " .. tostring(err)) end
end

function gadget:AllowCommand(unitID)
  return issuing or not held[unitID]
end

function gadget:RecvLuaMsg(msg)
  if msg == "VA_RIG:hud" and not hudPresent then
    hudPresent = true
    Spring.Echo("VA_AUTOPILOT the HUD is here: the company leaves through it")
    return true
  end
end

local function mobile(ud) return ud and (ud.speed or 0) > 0 and not ud.isBuilding end

local function companyUnits(filter)
  local out = {}
  for _, uid in ipairs(Spring.GetTeamUnits(playerTeam) or {}) do
    local ud = UnitDefs[Spring.GetUnitDefID(uid) or -1]
    if filter(ud, uid) then out[#out + 1] = uid end
  end
  return out
end

-- ---------------------------------------------------------------- nudge
local function target()
  if tx or not mission then return tx, tz end
  local zid = (mission.objective and mission.objective.targetZoneId) or mission.targetZoneId
  if zid and GG.VA_ZoneAnchor then tx, tz = GG.VA_ZoneAnchor(zid) end
  return tx, tz
end

local function nudge()
  local x, z = target()
  if not x then return end
  local idle = companyUnits(function(ud, uid)
    if not mobile(ud) or (ud.isBuilder and not ud.canAttack) or held[uid] then return false end
    local q = Spring.GetUnitCommands(uid, 1)
    return q == nil or #q == 0
  end)
  if #idle == 0 then return end
  order(idle, CMD.FIGHT, { x, Spring.GetGroundHeight(x, z) or 0, z })
  Spring.Echo("VA_AUTOPILOT nudge idle=" .. #idle)
end

-- ---------------------------------------------------------------- rescue
-- A hero's wreck (va_hero_wreck: ours gone down, or a wild hero's to raise into the company); the
-- one nearest the pad, kept until it is raised or gone.
local rescueFid = nil
local function rescueWreck()
  if rescueFid and Spring.ValidFeatureID(rescueFid) then return rescueFid end
  rescueFid = nil
  local px, pz = rp("va_pad_x"), rp("va_pad_z")
  local best
  for _, f in ipairs(Spring.GetAllFeatures() or {}) do
    if tostring(Spring.GetFeatureRulesParam(f, "va_hero_wreck") or "") ~= "" then
      local x, _, z = Spring.GetFeaturePosition(f)
      local d = x and ((x - px) ^ 2 + (z - pz) ^ 2)
      if d and (not best or d < best) then best, rescueFid = d, f end
    end
  end
  return rescueFid
end

local function threatsNear(x, z, r)
  local myAlly = select(6, Spring.GetTeamInfo(playerTeam, false))
  local n = 0
  for _, u in ipairs(Spring.GetUnitsInCylinder(x, z, r) or {}) do
    local t = Spring.GetUnitTeam(u)
    local ud = UnitDefs[Spring.GetUnitDefID(u) or -1]
    if t and select(6, Spring.GetTeamInfo(t, false)) ~= myAlly and t ~= Spring.GetGaiaTeamID()
        and ud and ud.weapons and #ud.weapons > 0 and not Spring.GetUnitIsDead(u) then
      n = n + 1
    end
  end
  return n
end

local function rescue()
  local fid = rescueWreck()
  if not fid then held = {}; return end
  local hid = tostring(Spring.GetFeatureRulesParam(fid, "va_hero_wreck") or "?")
  local wx, _, wz = Spring.GetFeaturePosition(fid)
  if not wx then return end
  -- the squad: the four nearest guns fight to the wreck
  local guns = companyUnits(function(ud) return mobile(ud) and ud.canAttack and not ud.isBuilder end)
  local dist = {}
  for _, uid in ipairs(guns) do
    local x, _, z = Spring.GetUnitPosition(uid)
    dist[uid] = x and ((x - wx) ^ 2 + (z - wz) ^ 2) or math.huge
  end
  table.sort(guns, function(a, b) if dist[a] == dist[b] then return a < b end return dist[a] < dist[b] end)
  local squad = {}
  for i = 1, math.min(4, #guns) do squad[i] = guns[i] end
  if #squad > 0 then order(squad, CMD.FIGHT, { wx, Spring.GetGroundHeight(wx, wz) or 0, wz }, true) end
  -- the rez: only once the ground is quiet (armed enemies near a wreck turn a rescue into a
  -- feeding), or nearly quiet when the pocket is mostly wrecked anyway
  local threats = threatsNear(wx, wz, 700)
  local total, down = rp("va_objective_total"), rp("va_objective_destroyed")
  local crippled = total > 0 and down / total >= 0.6
  if threats > 0 and not (crippled and threats <= 12) then
    Spring.Echo("VA_AUTOPILOT rez waiting hero=" .. hid .. " threats=" .. threats)
    return
  end
  local rez, crit = {}, {}
  for _, uid in ipairs(companyUnits(function(ud) return ud and ud.canResurrect end)) do
    local q = Spring.GetUnitCommands(uid, 1)
    local busy = q and q[1] and q[1].id == CMD.RESURRECT and q[1].params and q[1].params[1] == fid + Game.maxUnits
    if busy then held[uid] = true
    elseif (tonumber((Spring.GetUnitRulesParam(uid, "va_hero_critical"))) or 0) == 1 then crit[#crit + 1] = uid
    else rez[#rez + 1] = uid end
  end
  if #rez == 0 then rez = crit end
  if #rez == 0 then return end
  order(rez, CMD.RESURRECT, { fid + Game.maxUnits }, true)
  Spring.Echo("VA_AUTOPILOT rez hero=" .. hid .. " feature=" .. fid .. " builders=" .. #rez)
end

-- ---------------------------------------------------------------- departure and leaving
local function regroup()
  local px, pz = tonumber((Spring.GetGameRulesParam("va_pad_x"))), tonumber((Spring.GetGameRulesParam("va_pad_z")))
  if not px then return end
  local mob = companyUnits(mobile)
  if #mob == 0 then return end
  order(mob, CMD.MOVE, { px, Spring.GetGroundHeight(px, pz) or 0, pz }, true)
  Spring.Echo("VA_AUTOPILOT regroup units=" .. #mob .. " pad=" .. tostring((Spring.GetGameRulesParam("va_pad_zone"))))
end

local function depart(why, f)
  if departureAt then return end
  departureAt, departureWhy = f, why
  held = {}
  Spring.Echo("VA_AUTOPILOT depart reason=" .. why .. " frame=" .. f)
  regroup()
end

-- Everyone mobile inside the pad's own radius, or three settles gone (a unit stuck on a cliff).
local function readyToLeave(f)
  if f - departureAt < SETTLE_FRAMES then return false end
  local px, pz, pr = rp("va_pad_x"), rp("va_pad_z"), math.max(1, rp("va_pad_r"))
  local mob, on = 0, 0
  for _, uid in ipairs(companyUnits(mobile)) do
    mob = mob + 1
    local x, _, z = Spring.GetUnitPosition(uid)
    if x and ((x - px) ^ 2 + (z - pz) ^ 2) <= pr ^ 2 then on = on + 1 end
  end
  if mob == 0 or on == mob or f - departureAt >= SETTLE_FRAMES * 3 then
    Spring.Echo("VA_AUTOPILOT on pad " .. on .. "/" .. mob)
    return true
  end
  return false
end

local function extractDirectly(reason, f, why)
  if not GG.VA_ExfilCmd then
    if f % 300 == 0 then Spring.Echo("VA_AUTOPILOT waiting: exfil gadget has no command hook") end
    return
  end
  extracted = true
  Spring.Echo(why .. " reason=" .. reason .. " frame=" .. f .. " pad=" .. tostring((Spring.GetGameRulesParam("va_pad_zone"))))
  GG.VA_ExfilCmd("extract:home")
end

local function leave(reason, f)
  if extracted then return end
  if not hudPresent then return extractDirectly(reason, f, "VA_AUTOPILOT_EXTRACT") end   -- no LuaUI in this run
  if not leaveAt then
    leaveAt, leaveWhy = f, reason
    Spring.SetGameRulesParam("va_autopilot_leave", reason, { public = true })
    Spring.Echo("VA_AUTOPILOT_LEAVE reason=" .. reason .. " frame=" .. f .. " pad=" .. tostring((Spring.GetGameRulesParam("va_pad_zone"))))
    return
  end
  if f - leaveAt >= HUD_WAIT then extractDirectly(reason, f, "VA_AUTOPILOT_HUD_SILENT (the HUD did not extract; extracting directly)") end
end

-- ---------------------------------------------------------------- call-ins
function gadget:Initialize()
  gadgetHandler:RegisterAllowCommand(CMD.ANY)
  local ok, m = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  mission = ok and type(m) == "table" and m or nil
  playerTeam = tonumber(mission and mission.balance and mission.balance.playerTeamID) or 0
  Spring.Echo("VA_AUTOPILOT armed team=" .. playerTeam .. " cap=" .. CAP_FRAMES .. " settle=" .. SETTLE_FRAMES
    .. " mission=" .. tostring(mission and mission.missionId))
end

local function memWatch(f)
  local lm = ""
  if Spring.GetLuaMemUsage then
    local a, b, c, d, e, g = Spring.GetLuaMemUsage()
    lm = " luamem=" .. tostring(a) .. "," .. tostring(b) .. "," .. tostring(c) .. "," .. tostring(d) .. "," .. tostring(e) .. "," .. tostring(g)
  end
  Spring.Echo("VA_AUTOPILOT_MEM frame=" .. f .. " synced_kb=" .. tostring(gcinfo and gcinfo() or "?") .. lm
    .. " units=" .. #(Spring.GetAllUnits() or {}) .. " features=" .. #(Spring.GetAllFeatures() or {})
    .. " projectiles=" .. tostring(Spring.GetProjectilesInRectangle and #(Spring.GetProjectilesInRectangle(0, 0, Game.mapSizeX, Game.mapSizeZ) or {}) or "?"))
end

function gadget:GameFrame(f)
  if f % 900 == 13 then memWatch(f) end
  if extracted or f % 30 ~= 11 then return end
  if rp("va_terminal") == 1 then extracted = true; return end
  if leaveAt then return leave(leaveWhy, f) end   -- told to leave: the HUD's turn, then the fallback
  if FORCE_AT and f >= FORCE_AT and rp("va_objective_complete") ~= 1 and GG.VA_ObjectiveComplete then
    Spring.Echo("VA_AUTOPILOT test: forcing objective complete frame=" .. f)
    GG.VA_ObjectiveComplete("test_forced")
  end
  if not departureAt then
    if rp("va_objective_complete") == 1 then depart("objective", f)
    elseif rp("va_objective_failed") == 1 then depart("objective_failed", f)
    elseif f >= CAP_FRAMES then depart("clock", f) end
  end
  if departureAt then
    if (f - departureAt) % 450 == 0 and f > departureAt then regroup() end
    if readyToLeave(f) then return leave(departureWhy, f) end
    return
  end
  if f % RESCUE_EVERY == 311 then rescue() end
  if f % NUDGE_EVERY < 30 then nudge() end
end
