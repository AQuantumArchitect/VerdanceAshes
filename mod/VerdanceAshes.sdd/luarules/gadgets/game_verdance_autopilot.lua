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
--   the gate   the Spire Jump (finale C, game_verdance_jump_gate.lua): builders finish the frame,
--              then build advanced fusions around it until it has its four, and once it is open
--              the heroes walk onto its pad one at a time. BARb knows none of this.
--   finales    get three times the clock (va_autopilot_minutes) before the company leaves
--   siege      a job with targets to break (the Overthrow; in the kings' showdown, the rival
--              commanders): once the company has SIEGE_GUNS guns, every gun not on another errand
--              fights to the target nearest the company
--   hold       a capture in its hold, the company short of presence there: every armed unit not
--              on another errand fights to the hold's centre (va_hold_cx/cz) and stays. BARb
--              wandered off and the hold never ran (stock rehearsal, 2026-11-02)
--   rescue     a hero's wreck on the field gets a squad: the four nearest guns go to it, and once
--              the ground is quiet, the rez bots raise it (critical rez bots only if no other)
--   departure  the objective done, failed, or the clock out: everyone walks to the real pad
--              (va_pad_x/z/r), and the company leaves once all of it stands there (or after
--              three settles, for stuck units)
--   muster     a Rock Jungle muster (mission.muster, the hub's muster card) does not leave when the
--              gate is secured: the builders stake the bank and the lab prints the army until the
--              waves' forecast or the clock says go (owner call, 2026-11-11)
--   raptors    on raptor ground (va_raptor_grace_seconds set: the Rock Jungle) the company leaves on
--              the waves' forecast (raptorsCall, below): now if it is losing the fight on its
--              hands, or in time to be on the pad before a wave that would tip it lands. It replaced
--              "60 s after the grace" (owner calls 2026-11-09; the baseline's six home wipes came
--              from staying)
--   caution    a named hero badly hurt, or hurt and outnumbered, walks back to the pad and is held
--              there until it is mostly whole again or the ground near it has been quiet a while;
--              heroes are never nudged into the wound (the baseline lost 20 named heroes)
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
-- raptor ground (the wave forecast decides when the company leaves: raptorsCall)
local RAPTOR_GRACE = tonumber(opts.va_raptor_grace_seconds)
-- hero caution, once a second: the safety field (include/va_safety_field.lua) weighs each place a hero
-- could be (its own orders; the pad; the middle of the company's strength; a ring as far as it walks
-- in the time it takes to cross the enemy's reach; for a rez hero, the wrecks it knows of) by the chance
-- it lives through getting there and staying, times what it keeps and gains, and the hero goes to the
-- best. Owner call 2026-11-09: no leash and no thresholds (this replaced health cut-offs at 0.55, 0.85
-- and 0.90, "five enemies within 700", Ketha's 1500 leash, a 700 step and a "hot pad" count; history
-- in git and docs/DEVLOG.md).
local CAUTION_EVERY = 30
-- va_autopilot_caution=0 turns hero caution off (A/B trials of the proxy player)
local CAUTION_ON = num("va_autopilot_caution", 1) ~= 0
local SafetyField = VFS.Include("luarules/gadgets/include/va_safety_field.lua")

if not gadgetHandler:IsSyncedCode() then
  local started, sped, echoed = false, false, false
  -- va_autopilot_shots=S: a screenshot every S game seconds (windowed runs only: the HUD review rig)
  local SHOT_EVERY = math.floor(num("va_autopilot_shots", 0) * 30)
  local nextShot = SHOT_EVERY > 0 and 30 * 20 or nil
  function gadget:GameStart() started = true end
  -- Lua memory, from here: synced code has no gcinfo, collectgarbage or GetLuaMemUsage in this engine,
  -- and LuaRules ran out of memory (its 1.6 GB cap) on Koom Valley's act-2 war, 11-10, with no curve
  -- to read. Every 30 game seconds, what the engine reports.
  local lastMem = -1
  local function memLine()
    local f = Spring.GetGameFrame() or 0
    if not Spring.GetLuaMemUsage or f - lastMem < 900 then return end
    lastMem = f
    local v = { Spring.GetLuaMemUsage() }
    for i = 1, #v do v[i] = tostring(v[i]) end
    Spring.Echo("VA_AUTOPILOT_LUAMEM frame=" .. f .. " " .. table.concat(v, ","))
  end
  function gadget:Update()
    if not started then return end
    memLine()
    if nextShot and (Spring.GetGameFrame() or 0) >= nextShot then
      nextShot = nextShot + SHOT_EVERY
      pcall(Spring.SendCommands, "screenshot png")
      Spring.Echo("VA_AUTOPILOT_SHOT frame=" .. tostring(Spring.GetGameFrame()))
    end
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
local retreating = {}                       -- unitID -> frame it was pulled back (hero caution)
local chosen = {}                           -- unitID -> the plan caution last ordered ({ kind, x, z, fid })
local field = nil                           -- the safety field (shared on GG with the hero doctrine)
local issuing = false
local MUSTER = false                        -- a Rock Jungle muster (mission.muster): see GameFrame
local boarding = {}                         -- unitID -> true: told to go at the departure (readyToLeave)

-- Drop the rig's holds (a rescue squad, a siege) but keep the heroes that are being pulled back.
local function releaseHolds()
  held = {}
  for uid in pairs(retreating) do held[uid] = true end
end

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

-- The company's commander is never nudged into the fight: it is the company's king in the showdown
-- (it falls, the sortie is lost) and its suit everywhere else, and BARb needs it home to build.
local COM = VFS.Include("luarules/gadgets/include/va_commanders.lua")

local function isHero(uid)
  local hid = Spring.GetUnitRulesParam(uid, "va_hero_id")
  return hid ~= nil and hid ~= "" and hid ~= 0
end

local function nudge()
  local x, z = target()
  if not x then return end
  local idle = companyUnits(function(ud, uid)
    if not mobile(ud) or (ud.isBuilder and not ud.canAttack) or held[uid] or COM.isCommander(ud) then return false end
    if isHero(uid) then return false end   -- heroes are never sent into the wound (hero caution)
    local q = Spring.GetUnitCommands(uid, 1)
    return q == nil or #q == 0
  end)
  if #idle == 0 then return end
  order(idle, CMD.FIGHT, { x, Spring.GetGroundHeight(x, z) or 0, z })
  Spring.Echo("VA_AUTOPILOT nudge idle=" .. #idle)
end

-- ---------------------------------------------------------------- siege
local SIEGE_GUNS = 12
-- The kings' showdown is BARb's war: on the container rig it brought down two kings of three on its
-- own (Cortex at 20 minutes, the Null Mercs at 43), and the run where the rig besieged the nearest
-- king took none (its 21 guns stood off the Armada king's base for an hour: that king was under the
-- sea, game_verdance_kings now walks it ashore). The rig goes for the last king, and after half an
-- hour for the nearest one, with a real army, attacking the commander itself rather than the place
-- it stood: in one run BARb took one king of three in ninety minutes and then sat.
local KING_SIEGE_GUNS = 40
-- ...and after 45 minutes with whatever army there is (twenty guns or more): with the kings on their
-- seats in the corners nobody came to anybody, and the company's army stood at 29 guns for an hour.
local KING_LATE_FRAMES, KING_LATE_GUNS = 45 * 60 * 30, 20
local KING_WAR_FRAMES = 30 * 60 * 30
-- The Spire Jump is won at the gate, not at the hive: the guns stand around the gate (and the
-- fusions going up beside it) instead of marching on the nests. In the finale-C rehearsal the
-- siege took 14 guns to the hive heart, 3,000 elmos off, and the raptors took the gate.
-- The guard stands 450 elmos off the gate toward the middle of the map, where the hive is: in front
-- of the generators going up around the gate, and off its pad. Guarding the gate's own centre crowded
-- the pad: on Luke's PC (run 20261103_010856) three heroes went through and the fourth stood off it for
-- fifteen minutes.
local function guardPoint(gx, gz)
  local dx, dz = Game.mapSizeX / 2 - gx, Game.mapSizeZ / 2 - gz
  local d = math.sqrt(dx * dx + dz * dz)
  if d < 1 then return gx, gz end
  return gx + dx / d * 450, gz + dz / d * 450
end

-- The units each standing job holds, so the job can order them again: held is one flag for every job,
-- and a unit the siege held stayed held while any wreck waited for a rescue. In the kings' showdown
-- (container rig, 2026-11-03) the first siege's guns sat where the Cortex king had died for an hour
-- while the other two kings lived.
local sieged, guarding = {}, {}

local function guardTheGate()
  local state = tostring(Spring.GetGameRulesParam("va_gate_state") or "")
  if state == "lost" then return false end
  -- the Spire Jump: never march on the nests, even in the first second, before the gate gadget has
  -- published the gate (frame 30): the siege at frame 11 took the whole army to the hive
  if state == "" then return mission ~= nil and type(mission.jumpGate) == "table" end
  local gx, gz = rp("va_gate_x"), rp("va_gate_z")
  if gx <= 0 then return true end
  local guns = companyUnits(function(ud, uid)
    local hid = Spring.GetUnitRulesParam(uid, "va_hero_id")
    local hero = hid ~= nil and hid ~= "" and hid ~= 0
    return mobile(ud) and ud.canAttack and not ud.isBuilder and (guarding[uid] or not held[uid])
      and not (state == "open" and hero)
  end)
  if #guns == 0 then return true end
  local px, pz = guardPoint(gx, gz)
  order(guns, CMD.FIGHT, { px, Spring.GetGroundHeight(px, pz) or 0, pz }, true)
  for _, uid in ipairs(guns) do guarding[uid] = true end
  Spring.Echo("VA_AUTOPILOT guard gate guns=" .. #guns .. " state=" .. state)
  return true
end

local striking = false                -- a king's siege has gathered and gone in (until it thins out)
local RALLY_SHORT, RALLY_RADIUS = 2200, 900
local RALLY_MAX_FRAMES = 3 * 60 * 30
local rallySince = nil                 -- frame the current rally began
local function siege()
  if guardTheGate() then return end
  local targets = GG.VA_ObjectiveTargets and GG.VA_ObjectiveTargets() or nil
  local kings = false
  if (not targets or next(targets) == nil) and GG.VA_RivalKings then
    targets = GG.VA_RivalKings()   -- the kings' showdown: the rival commanders are the targets
    local n = 0
    for _ in pairs(targets or {}) do n = n + 1 end
    kings = n > 0
    if kings and ((Spring.GetGameFrame and Spring.GetGameFrame()) or 0) % 3600 < 30 then
      -- where the kings stand, every two minutes, and how big the company's army is
      local rows, armed = {}, 0
      for _, uid in ipairs(companyUnits(function(ud) return mobile(ud) and ud.canAttack and not ud.isBuilder end)) do armed = armed + 1 end
      for uid, team in pairs(targets) do
        local x, y, z = Spring.GetUnitPosition(uid)
        local ud = UnitDefs[Spring.GetUnitDefID(uid) or -1]
        if x then
          rows[#rows + 1] = tostring(team) .. ":" .. tostring(ud and ud.name or "?") .. "@" .. math.floor(x) .. ","
            .. math.floor(z) .. " y=" .. math.floor(y or 0) .. " ground=" .. math.floor(Spring.GetGroundHeight(x, z) or 0)
        end
      end
      Spring.Echo("VA_AUTOPILOT kings standing=" .. n .. " company_guns=" .. armed .. " " .. table.concat(rows, " "))
    end
    -- more than one king standing: BARb's war, not the rig's, for the first half hour
    if n > 1 and ((Spring.GetGameFrame and Spring.GetGameFrame()) or 0) < KING_WAR_FRAMES then targets = nil end
  end
  local guns = companyUnits(function(ud, uid)
    return mobile(ud) and ud.canAttack and not ud.isBuilder and (sieged[uid] or not held[uid])
  end)
  local need = SIEGE_GUNS
  if kings then
    local late = ((Spring.GetGameFrame and Spring.GetGameFrame()) or 0) >= KING_LATE_FRAMES
    need = late and KING_LATE_GUNS or KING_SIEGE_GUNS
  end
  if not targets or next(targets) == nil or #guns < need then
    -- too thin to break anything: what is left of the siege goes back to BARb until there are more
    for uid in pairs(sieged) do held[uid] = nil end
    sieged = {}
    striking = false
    rallySince = nil
    return
  end
  local cx, cz, n = 0, 0, 0
  for _, uid in ipairs(guns) do
    local x, _, z = Spring.GetUnitPosition(uid)
    if x then cx, cz, n = cx + x, cz + z, n + 1 end
  end
  if n == 0 then return end
  cx, cz = cx / n, cz / n
  local bx, bz, bd = nil, nil, math.huge
  for uid in pairs(targets) do
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local x, _, z = Spring.GetUnitPosition(uid)
      local d = x and ((x - cx) ^ 2 + (z - cz) ^ 2) or math.huge
      if d < bd then bx, bz, bd = x, z, d end
    end
  end
  if not bx then return end
  local myAlly = select(6, Spring.GetTeamInfo(playerTeam, false))
  local king
  if kings then
    for uid in pairs(targets) do
      local x, _, z = Spring.GetUnitPosition(uid)
      if x and x == bx and z == bz then king = uid end
    end
  end
  -- A king's siege gathers first. Guns sent one by one from the factory walked the map alone: on the
  -- container rig (2026-11-03, run8) the siege's guns stood 2,500 to 4,700 elmos from the Armada king, on
  -- average, for 40 minutes, and the king never fell. They gather 2,200 elmos short of the king, on
  -- the company's side, and strike together once three in four of the guns needed are there.
  if kings and not striking then
    local d = math.sqrt(bd)
    local rx, rz = bx, bz
    if d > RALLY_SHORT then
      rx, rz = bx + (cx - bx) / d * RALLY_SHORT, bz + (cz - bz) / d * RALLY_SHORT
    end
    local near = 0
    for _, uid in ipairs(guns) do
      local x, _, z = Spring.GetUnitPosition(uid)
      if x and (x - rx) ^ 2 + (z - rz) ^ 2 < RALLY_RADIUS ^ 2 then near = near + 1 end
    end
    -- ...or after three minutes of rallying, whatever has come: on the rig (run9) the guns stopped to
    -- fight on the way, and for 18 minutes 6 of 60 stood at the rally while the Cortex king lived on
    local now = (Spring.GetGameFrame and Spring.GetGameFrame()) or 0
    rallySince = rallySince or now
    if near < math.ceil(need * 0.75) and now - rallySince < RALLY_MAX_FRAMES then
      order(guns, CMD.FIGHT, { rx, Spring.GetGroundHeight(rx, rz) or 0, rz }, true)
      for _, uid in ipairs(guns) do sieged[uid] = true end
      Spring.Echo("VA_AUTOPILOT siege rally guns=" .. #guns .. " gathered=" .. near .. " at=" .. math.floor(rx) .. "," .. math.floor(rz))
      return
    end
    striking = true
    rallySince = nil
  end
  -- attack the commander itself once the company can see it; until then fight the way to where it
  -- stands (an order to attack a unit out of sight does nothing: on the container rig 80 guns stood
  -- 5,000 elmos from the Cortex king for twenty minutes with one)
  if king and Spring.IsUnitInLos and Spring.IsUnitInLos(king, myAlly) then
    order(guns, CMD.ATTACK, { king }, true)
  else
    order(guns, CMD.FIGHT, { bx, Spring.GetGroundHeight(bx, bz) or 0, bz }, true)
  end
  for _, uid in ipairs(guns) do sieged[uid] = true end
  Spring.Echo("VA_AUTOPILOT siege guns=" .. #guns .. " at=" .. math.floor(bx) .. "," .. math.floor(bz)
    .. " ground=" .. math.floor(Spring.GetGroundHeight(bx, bz) or 0) .. " from=" .. math.floor(math.sqrt(bd)))
end

-- ---------------------------------------------------------------- scout marks
-- A sortie's scout marks (blue on the rail) are done once the company has had a good look at the
-- zone. BARb never scouts on its own, so the rig sends one quick fighter to each open mark: the
-- fastest armed mobile unit nobody else holds, not a hero, not a builder. It goes on FIGHT, so it
-- looks on the way; when the mark is done the unit goes back to BARb.
local scouting = {}           -- mark index -> unitID
local function scout()
  for i = 1, rp("va_secondary_total") do
    local kind = tostring(Spring.GetGameRulesParam("va_sec" .. i .. "_kind") or "")
    local uid = scouting[i]
    if kind == "scout" then
      local done = rp("va_sec" .. i .. "_done") == 1
      if done or (uid and Spring.GetUnitIsDead(uid) ~= false) then
        if uid then held[uid] = nil end
        scouting[i] = nil
        uid = nil
      end
      if not done and not uid then
        local x, z = rp("va_sec" .. i .. "_x"), rp("va_sec" .. i .. "_z")
        local best, bestSpeed = nil, 0
        for _, u in ipairs(companyUnits(function(ud, u)
          local hid = Spring.GetUnitRulesParam(u, "va_hero_id")
          local hero = hid ~= nil and hid ~= "" and hid ~= 0
          return mobile(ud) and ud.canAttack and not ud.isBuilder and not held[u] and not sieged[u] and not hero
        end)) do
          local sp = (UnitDefs[Spring.GetUnitDefID(u) or -1] or {}).speed or 0
          if sp > bestSpeed then best, bestSpeed = u, sp end
        end
        if best and x > 0 then
          order({ best }, CMD.FIGHT, { x, Spring.GetGroundHeight(x, z) or 0, z }, true)
          scouting[i] = best
          Spring.Echo("VA_AUTOPILOT scout mark=" .. i .. " unit=" .. tostring(best) .. " to=" .. math.floor(x) .. "," .. math.floor(z))
        end
      end
    end
  end
end

-- ---------------------------------------------------------------- hold
local function holdTheZone()
  local phase = tostring(Spring.GetGameRulesParam("va_capture_phase") or "")
  -- A capture with nothing booked to wreck (a Rock Jungle door) clears by standing in the zone in
  -- strength with no enemy fighting there (objective_presence.captureClearStep), so the clear phase
  -- needs the army there too: on campaign_hard_v2 the door jobs sat in "clear" all sortie.
  local emptyClear = phase == "clear" and rp("va_objective_total") <= 0
  if phase ~= "hold" and not emptyClear then return end
  local need = rp("va_claim_need")
  if phase == "hold" and need > 0 and rp("va_claim_value") >= need then return end
  local cx, cz = tonumber((Spring.GetGameRulesParam("va_hold_cx"))), tonumber((Spring.GetGameRulesParam("va_hold_cz")))
  if not cx or cx <= 0 then cx, cz = target() end
  if not cx then return end
  local guns = companyUnits(function(ud, uid)
    return mobile(ud) and ud.canAttack and not ud.isBuilder and not held[uid]
  end)
  if #guns == 0 then return end
  order(guns, CMD.FIGHT, { cx, Spring.GetGroundHeight(cx, cz) or 0, cz }, true)
  Spring.Echo("VA_AUTOPILOT hold phase=" .. phase .. " units=" .. #guns .. " presence=" .. rp("va_claim_value") .. "/" .. need)
end

-- ---------------------------------------------------------------- the Spire Gate (finale C)
local AFUS_DEFS = nil
local function afusDefs()
  if AFUS_DEFS then return AFUS_DEFS end
  AFUS_DEFS = {}
  for _, n in ipairs({ "legafus", "armafus", "corafus" }) do
    if UnitDefNames and UnitDefNames[n] then AFUS_DEFS[#AFUS_DEFS + 1] = UnitDefNames[n].id end
  end
  return AFUS_DEFS
end

local function canBuild(ud, defID)
  for _, b in ipairs((ud and ud.buildOptions) or {}) do if b == defID then return true end end
  return false
end

-- A free spot for a building near the gate: rings outward from it, the first place BAR accepts.
local function spotNear(defID, gx, gz)
  for _, r in ipairs({ 450, 650, 850, 1050, 1300, 1600 }) do
    for k = 0, 11 do
      local a = (k / 12) * 2 * math.pi
      local x, z = gx + math.cos(a) * r, gz + math.sin(a) * r
      local y = Spring.GetGroundHeight(x, z) or 0
      if (Spring.TestBuildOrder(defID, x, y, z, 0) or 0) > 0 then return x, y, z end
    end
  end
  return nil
end

local function busyWith(uid, test)
  local q = Spring.GetUnitCommands(uid, 1)
  return q ~= nil and q[1] ~= nil and test(q[1])
end

-- A factory's build queue is not in its unit commands (those are the orders its products get), so
-- a factory read through busyWith always looked idle: the rig queued another constructor every
-- second, 498 of them in the 2026-11-03 finale-C rehearsal.
local function factoryBusy(f)
  if Spring.GetFactoryCommands then
    local q = Spring.GetFactoryCommands(f, 1)
    if type(q) == "number" then return q > 0 end
    return type(q) == "table" and #q > 0
  end
  return busyWith(f, function(c) return c.id < 0 end)
end

-- What a building of each type makes at most, by its def: a solar its upkeep, a wind the map's
-- average wind, a reactor its output. Buildings only (the Spire Gate's power, game_verdance_jump_gate).
local GENERATORS = nil
local function generators()
  if GENERATORS then return GENERATORS end
  GENERATORS = {}
  local wind = ((Game.windMin or 0) + (Game.windMax or 0)) / 2
  for id, ud in pairs(UnitDefs) do
    if (ud.speed or 0) == 0 and not ud.isFactory then
      local out = (ud.energyMake or 0) + math.max(0, -(ud.energyUpkeep or 0))
      if (ud.windGenerator or 0) > 0 then out = out + math.min(ud.windGenerator, wind) end
      if out > 0 then GENERATORS[id] = out end
    end
  end
  return GENERATORS
end

-- The tech ladder to an advanced fusion, worked out from the unit defs (any faction):
--   fusionBuilders  can build one          t2Labs        factories that make a fusion builder
--   labBuilders     can build a t2Lab      t1Labs        factories that make a lab builder
local LADDER = nil
local function ladder()
  if LADDER then return LADDER end
  local function anyIn(ud, set)
    for _, b in ipairs((ud and ud.buildOptions) or {}) do if set[b] then return b end end
    return nil
  end
  local afus = {}
  for _, d in ipairs(afusDefs()) do afus[d] = true end
  local L = { fusionBuilders = {}, t2Labs = {}, labBuilders = {}, t1Labs = {} }
  for id, ud in pairs(UnitDefs) do if not ud.isFactory and anyIn(ud, afus) then L.fusionBuilders[id] = true end end
  for id, ud in pairs(UnitDefs) do if ud.isFactory and anyIn(ud, L.fusionBuilders) then L.t2Labs[id] = true end end
  for id, ud in pairs(UnitDefs) do if not ud.isFactory and anyIn(ud, L.t2Labs) then L.labBuilders[id] = true end end
  for id, ud in pairs(UnitDefs) do if ud.isFactory and anyIn(ud, L.labBuilders) then L.t1Labs[id] = true end end
  L.anyIn = anyIn
  LADDER = L
  return L
end

local function buildAt(uid, def, gx, gz)
  local x, y, z = spotNear(def, gx, gz)
  if not x then return false end
  held[uid] = true
  issuing = true
  pcall(Spring.GiveOrderToUnit, uid, -def, { x, y, z, 0 }, 0)
  issuing = false
  return true
end

-- No one can build an advanced fusion yet: climb one rung (a factory makes the builder, a builder
-- makes the factory), one order at a time. Returns what it ordered, for the log.
local function climbToFusion(gx, gz)
  local L = ladder()
  local have = { fusionBuilders = {}, t2Labs = {}, labBuilders = {}, t1Labs = {} }
  for _, uid in ipairs(Spring.GetTeamUnits(playerTeam) or {}) do
    local d = Spring.GetUnitDefID(uid)
    local _, _, _, _, built = Spring.GetUnitHealth(uid)
    if d and (built or 1) >= 1 then
      for k in pairs(have) do if L[k][d] then have[k][#have[k] + 1] = uid end end
    end
  end
  if #have.fusionBuilders > 0 then return nil end
  local idle = function(uid) return not busyWith(uid, function(c) return c.id < 0 end) end
  local function make(factories, set, what)
    for _, f in ipairs(factories) do
      if not factoryBusy(f) then
        local want = L.anyIn(UnitDefs[Spring.GetUnitDefID(f)], set)
        if want then
          issuing = true
          pcall(Spring.GiveOrderToUnit, f, -want, {}, 0)
          issuing = false
          return what
        end
      end
    end
  end
  if #have.t2Labs > 0 then return make(have.t2Labs, L.fusionBuilders, "fusion builder") end
  for _, uid in ipairs(have.labBuilders) do
    if idle(uid) then
      local lab = L.anyIn(UnitDefs[Spring.GetUnitDefID(uid)], L.t2Labs)
      if lab and buildAt(uid, lab, gx, gz) then return "advanced lab" end
    end
  end
  if #have.labBuilders == 0 and #have.t1Labs > 0 then return make(have.t1Labs, L.labBuilders, "lab builder") end
  return nil
end

local function gateRig()
  local state = tostring(Spring.GetGameRulesParam("va_gate_state") or "")
  if state == "" or state == "lost" then return end
  local gx, gz, gate = rp("va_gate_x"), rp("va_gate_z"), rp("va_gate_unit")
  if gx <= 0 then return end
  local builders = companyUnits(function(ud) return mobile(ud) and ud.isBuilder and (ud.buildOptions and #ud.buildOptions > 0) end)
  if ((Spring.GetGameFrame and Spring.GetGameFrame()) or 0) % 900 < 30 then
    -- where the gate work stands: each builder, how far from the gate, and what it is doing
    local rows = {}
    for _, uid in ipairs(builders) do
      local x, _, z = Spring.GetUnitPosition(uid)
      local q = Spring.GetUnitCommands(uid, 1)
      local ud = UnitDefs[Spring.GetUnitDefID(uid) or -1]
      rows[#rows + 1] = tostring(ud and ud.name or "?") .. "@" .. (x and math.floor(math.sqrt((x - gx) ^ 2 + (z - gz) ^ 2)) or "?")
        .. ":" .. tostring(q and q[1] and q[1].id or "idle")
    end
    local facs = #companyUnits(function(ud) return ud and ud.isFactory end)
    local m, mIn, e, eIn = 0, 0, 0, 0
    if Spring.GetTeamResources then
      m, _, _, mIn = Spring.GetTeamResources(playerTeam, "metal")
      e, _, _, eIn = Spring.GetTeamResources(playerTeam, "energy")
    end
    Spring.Echo("VA_AUTOPILOT gate " .. state .. " built=" .. rp("va_gate_built") .. " power=" .. rp("va_gate_power")
      .. "/" .. rp("va_gate_power_need") .. " afus=" .. rp("va_gate_afus")
      .. string.format(" metal=%d+%.1f energy=%d+%.1f", m or 0, mIn or 0, e or 0, eIn or 0)
      .. " factories=" .. facs .. " builders=" .. #builders .. " " .. table.concat(rows, " "))
  end
  if #builders < 4 and rp("va_tenebrium_bank") >= 1 then
    -- the finale kit brings a lab and few constructors: every idle factory that can make a
    -- constructor makes one, until there are four (a constructor costs Tenebrium: none queued
    -- that the bank cannot pay, or the factory asks for it every frame)
    local L = ladder()
    L.mobileBuilders = L.mobileBuilders or (function()
      local set = {}
      for id, ud in pairs(UnitDefs) do
        if ud.isBuilder and (ud.speed or 0) > 0 and ud.buildOptions and #ud.buildOptions > 0 then set[id] = true end
      end
      return set
    end)()
    for _, f in ipairs(companyUnits(function(ud) return ud and ud.isFactory end)) do
      if not factoryBusy(f) then
        local want = L.anyIn(UnitDefs[Spring.GetUnitDefID(f)], L.mobileBuilders)
        if want then
          issuing = true
          pcall(Spring.GiveOrderToUnit, f, -want, {}, 0)
          issuing = false
          Spring.Echo("VA_AUTOPILOT gate builders=" .. #builders .. " factory makes one")
        end
      end
    end
  end
  -- the gate crew: the builders nearest the gate, half of them (at least one). The rest stay BARb's,
  -- to raise the economy the gate and its power are built from: with every builder on the gate, the
  -- rehearsal's metal store ran dry at 44% and nothing ever refilled it.
  local dist = {}
  for _, uid in ipairs(builders) do
    local x, _, z = Spring.GetUnitPosition(uid)
    dist[uid] = x and ((x - gx) ^ 2 + (z - gz) ^ 2) or math.huge
  end
  local crew = {}
  for i, uid in ipairs(builders) do crew[i] = uid end
  table.sort(crew, function(a, b) if dist[a] == dist[b] then return a < b end return dist[a] < dist[b] end)
  for i = #crew, math.max(1, math.ceil(#builders / 2)) + 1, -1 do crew[i] = nil end
  if state == "frame" then
    local free = {}
    for _, uid in ipairs(crew) do
      if not busyWith(uid, function(c) return c.id == CMD.REPAIR end) then free[#free + 1] = uid end
    end
    if #free > 0 and gate > 0 then
      order(free, CMD.REPAIR, { gate }, true)
      local where = {}
      for _, uid in ipairs(free) do
        local x, _, z = Spring.GetUnitPosition(uid)
        local ud = UnitDefs[Spring.GetUnitDefID(uid) or -1]
        where[#where + 1] = tostring(ud and ud.name or "?") .. "@" .. (x and math.floor(math.sqrt((x - gx) ^ 2 + (z - gz) ^ 2)) or "?")
      end
      Spring.Echo("VA_AUTOPILOT gate repair builders=" .. #free .. " " .. table.concat(where, " ") .. " built=" .. rp("va_gate_built"))
    end
  elseif (state == "unpowered" or state == "charging") and rp("va_gate_power_need") > 0 then
    -- power: the crew builds the strongest generator it can, as near the gate as BAR allows, until
    -- what stands and what is going up covers the need with a tenth to spare
    local need, have = rp("va_gate_power_need"), rp("va_gate_power")
    local GEN = generators()
    local coming = 0
    for _, uid in ipairs(crew) do
      local q = Spring.GetUnitCommands(uid, 1)
      local c = q and q[1]
      if c and c.id < 0 and GEN[-c.id] then coming = coming + GEN[-c.id] end
    end
    if have + coming >= need * 1.1 then return end
    local placed = {}
    for _, uid in ipairs(crew) do
      if not busyWith(uid, function(c) return c.id < 0 end) then
        local ud = UnitDefs[Spring.GetUnitDefID(uid) or -1]
        local opts = {}
        for _, b in ipairs((ud and ud.buildOptions) or {}) do if GEN[b] then opts[#opts + 1] = b end end
        table.sort(opts, function(a, b) if GEN[a] == GEN[b] then return a < b end return GEN[a] > GEN[b] end)
        for _, def in ipairs(opts) do
          if buildAt(uid, def, gx, gz) then
            coming = coming + GEN[def]
            placed[#placed + 1] = tostring(UnitDefs[def] and UnitDefs[def].name or def)
            break
          end
        end
      end
      if have + coming >= need * 1.1 then break end
    end
    if #placed > 0 then
      Spring.Echo("VA_AUTOPILOT gate power orders=" .. table.concat(placed, ",") .. " have=" .. math.floor(have)
        .. " coming=" .. math.floor(coming) .. " need=" .. need)
    end
  elseif state == "unpowered" or state == "charging" then
    local need, have = math.max(1, rp("va_gate_afus_need")), rp("va_gate_afus")
    if have >= need then return end
    local placed = 0
    for _, uid in ipairs(builders) do
      if not busyWith(uid, function(c) return c.id < 0 end) then
        local ud = UnitDefs[Spring.GetUnitDefID(uid) or -1]
        for _, def in ipairs(afusDefs()) do
          if canBuild(ud, def) then
            local x, y, z = spotNear(def, gx, gz)
            if x then
              held[uid] = true
              issuing = true
              pcall(Spring.GiveOrderToUnit, uid, -def, { x, y, z, 0 }, 0)
              issuing = false
              placed = placed + 1
            end
            break
          end
        end
      end
      if have + placed >= need + 1 then break end   -- one spare in case one dies
    end
    if placed > 0 then Spring.Echo("VA_AUTOPILOT gate afus orders=" .. placed .. " have=" .. have .. "/" .. need) end
    if placed == 0 then
      local step = climbToFusion(gx, gz)
      if step then Spring.Echo("VA_AUTOPILOT gate tech " .. step) end
    end
  elseif state == "open" then
    -- one hero at a time: the nearest walks onto the pad and stays; the rest wait near it
    local heroes = companyUnits(function(ud, uid)
      local hid = Spring.GetUnitRulesParam(uid, "va_hero_id")
      local partner = Spring.GetUnitRulesParam(uid, "va_partner_of")
      return mobile(ud) and hid ~= nil and hid ~= "" and hid ~= 0 and not (partner and partner ~= "")
    end)
    if #heroes == 0 then return end
    local best, bd = nil, math.huge
    for _, uid in ipairs(heroes) do
      local x, _, z = Spring.GetUnitPosition(uid)
      local d = x and ((x - gx) ^ 2 + (z - gz) ^ 2) or math.huge
      if d < bd then best, bd = uid, d end
    end
    order({ best }, CMD.MOVE, { gx, Spring.GetGroundHeight(gx, gz) or 0, gz }, true)
    if ((Spring.GetGameFrame and Spring.GetGameFrame()) or 0) % 900 < 30 then
      local q = Spring.GetUnitCommands(best, 1)
      Spring.Echo("VA_AUTOPILOT gate next hero=" .. tostring(Spring.GetUnitRulesParam(best, "va_hero_id"))
        .. " off_pad=" .. math.floor(math.sqrt(bd)) .. " pad_r=" .. rp("va_gate_pad_r")
        .. " cmd=" .. tostring(q and q[1] and q[1].id or "idle") .. " waiting=" .. (#heroes - 1))
    end
    local rest = {}
    for _, uid in ipairs(heroes) do if uid ~= best then rest[#rest + 1] = uid end end
    local wait = math.max(300, rp("va_gate_pad_r") + 150)
    if #rest > 0 then order(rest, CMD.MOVE, { gx + wait, Spring.GetGroundHeight(gx + wait, gz) or 0, gz }, true) end
  end
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

local function healthOf(uid)
  local hp, maxHp = Spring.GetUnitHealth(uid)
  hp = tonumber(hp) or 0
  return hp, tonumber(maxHp) or hp
end

local function rescue(f)
  local fid = rescueWreck()
  if not fid then releaseHolds(); return end
  local hid = tostring(Spring.GetFeatureRulesParam(fid, "va_hero_wreck") or "?")
  local wx, _, wz = Spring.GetFeaturePosition(fid)
  if not wx then return end
  field:refresh(f)
  -- the squad: the nearest guns, as many as it takes to outfight what covers the wreck (Lanchester: the
  -- sums of (dps x hp)^1/2 on each side, the unseen enemy included)
  -- (once the Spire Gate is open the heroes belong on its pad, not in a rescue squad)
  local gateOpen = tostring(Spring.GetGameRulesParam("va_gate_state") or "") == "open"
  local guns = companyUnits(function(ud, uid)
    if gateOpen then
      local hid = Spring.GetUnitRulesParam(uid, "va_hero_id")
      if hid ~= nil and hid ~= "" and hid ~= 0 then return false end
    end
    return mobile(ud) and ud.canAttack and not ud.isBuilder
  end)
  local dist = {}
  for _, uid in ipairs(guns) do
    local x, _, z = Spring.GetUnitPosition(uid)
    dist[uid] = x and ((x - wx) ^ 2 + (z - wz) ^ 2) or math.huge
  end
  table.sort(guns, function(a, b) if dist[a] == dist[b] then return a < b end return dist[a] < dist[b] end)
  local need, have, squad = field:enemyFightAt(wx, wz), 0, {}
  for _, uid in ipairs(guns) do
    if have >= need then break end
    squad[#squad + 1] = uid
    have = have + SafetyField.profile(Spring.GetUnitDefID(uid)).fight
  end
  if #squad > 0 then order(squad, CMD.FIGHT, { wx, Spring.GetGroundHeight(wx, wz) or 0, wz }, true) end
  -- the rez: each rez bot raises it when that is worth more to it than staying where it is (the walk
  -- and the work weighed by the field; the hero raised is worth what it was worth alive). With caution
  -- on, the rez heroes make that choice in caution, among every wreck they know of.
  local name = Spring.GetFeatureResurrect and Spring.GetFeatureResurrect(fid)
  local wdef = name and UnitDefNames and UnitDefNames[name]
  local wp = SafetyField.profile(wdef and wdef.id)
  local gain = field.heroValue[hid] or wp.cost
  local rez = {}
  for _, uid in ipairs(companyUnits(function(ud) return ud and ud.canResurrect end)) do
    local q = Spring.GetUnitCommands(uid, 1)
    local busy = q and q[1] and q[1].id == CMD.RESURRECT and q[1].params and q[1].params[1] == fid + Game.maxUnits
    if busy then held[uid] = true
    elseif not (CAUTION_ON and isHero(uid)) then
      local x, _, z = Spring.GetUnitPosition(uid)
      local hp, maxHp = healthOf(uid)
      local h = { uid = uid, x = x, z = z, hp = hp, maxHp = maxHp, defID = Spring.GetUnitDefID(uid) }
      local H = x and field:horizon(h) or 0
      if x and h.speed > 0 and h.p.rez > 0 then
        local V = field:heroWorth(h)
        local go = field:planValue(h, V, wx, wz, gain, wp.buildTime / h.p.rez)
        local stay = field:planValue(h, V, x, z, 0, H)
        if go > stay then rez[#rez + 1] = uid end
      end
    end
  end
  if #rez == 0 then
    Spring.Echo("VA_AUTOPILOT rez waiting hero=" .. hid .. string.format(" need=%.0f have=%.0f", need, have))
    return
  end
  order(rez, CMD.RESURRECT, { fid + Game.maxUnits }, true)
  Spring.Echo("VA_AUTOPILOT rez hero=" .. hid .. " feature=" .. fid .. " builders=" .. #rez)
end

-- ---------------------------------------------------------------- hero caution
-- BARb treats a named hero as one more unit: on the 11-09 baseline 20 of them died. Once a second each
-- hero's plan is weighed against the alternatives (the safety field) and the best is taken: its own
-- orders (back to BARb), a refuge (held there), or a wreck to raise (a rez hero).

-- Where a unit's current orders take it: the order's point, or the unit or feature it is aimed at.
local function planOf(uid)
  local q = Spring.GetUnitCommands(uid, 1)
  local p = q and q[1] and q[1].params
  if not p or #p == 0 then return nil end
  if #p >= 3 then return { x = p[1], z = p[3] } end
  local id, x, z = p[1], nil, nil
  local _
  if id >= Game.maxUnits then x, _, z = Spring.GetFeaturePosition(id - Game.maxUnits)
  else x, _, z = Spring.GetUnitPosition(id) end
  if x then return { x = x, z = z } end
end

local function caution(f)
  local px, pz = tonumber((Spring.GetGameRulesParam("va_pad_x"))), tonumber((Spring.GetGameRulesParam("va_pad_z")))
  if not px then return end
  field:refresh(f)
  for _, uid in ipairs(Spring.GetTeamUnits(playerTeam) or {}) do
    if isHero(uid) and not Spring.GetUnitIsDead(uid) then
      local x, _, z = Spring.GetUnitPosition(uid)
      local hp, maxHp = healthOf(uid)
      if x and hp > 0 then
        local hid = Spring.GetUnitRulesParam(uid, "va_hero_id")
        -- its temper from camp (mission.heroTemper, on Umwelt): how large it sees danger and gain. The
        -- doctrine's copy on GG first: with va_hero_mind_live=1 the hero's mind keeps it current
        local t = (GG.VA_HeroTemper and GG.VA_HeroTemper[tostring(hid)])
          or (mission and type(mission.heroTemper) == "table" and mission.heroTemper[tostring(hid)]) or nil
        -- its own orders: BARb's now, or, while caution holds it, what BARb wanted when it was taken (it
        -- goes back only when that plan has become the best; weighing where it stands instead let it go
        -- every other second and BARb sent it straight back: 78 swaps in a sortie, field trial 11-09)
        local plan
        if retreating[uid] then plan = chosen[uid] and chosen[uid].was else plan = planOf(uid) end
        local h = { uid = uid, x = x, z = z, hp = hp, maxHp = maxHp, defID = Spring.GetUnitDefID(uid), hid = hid,
          nerve = t and tonumber(t.nerve) or 0, drive = t and tonumber(t.drive) or 0, plan = plan }
        local best = field:choose(h, px, pz)
        local name = tostring(h.hid)
        if best.kind == "stay" then
          if retreating[uid] then
            retreating[uid], held[uid], chosen[uid] = nil, nil, nil
            Spring.Echo("VA_AUTOPILOT hero back to work id=" .. name .. string.format(" hp=%.2f S=%.3f", hp / math.max(maxHp, 1), best.S))
          end
        else
          -- a new order only when the plan changed by more than the hero walks in a refresh
          local prev = chosen[uid]
          best.was = (prev and prev.was) or plan
          local same = prev and prev.kind == best.kind and ((best.fid and prev.fid == best.fid)
            or (not best.fid and math.sqrt((prev.x - best.x) ^ 2 + (prev.z - best.z) ^ 2) <= h.speed * field.dt))
          if same then best = prev end
          if not same then
            held[uid] = true
            issuing = true
            pcall(function()
              if best.kind == "rez" then
                Spring.GiveOrderToUnit(uid, CMD.RESURRECT, { best.fid + Game.maxUnits }, 0)
              else
                Spring.GiveOrderToUnit(uid, CMD.MOVE, { best.x, Spring.GetGroundHeight(best.x, best.z) or 0, best.z }, 0)
              end
            end)
            issuing = false
            retreating[uid] = retreating[uid] or f
            chosen[uid] = best
            Spring.Echo("VA_AUTOPILOT hero " .. (best.kind == "rez" and "raises" or "pulls back") .. " id=" .. name
              .. string.format(" hp=%.2f S=%.3f to=%d,%d", hp / math.max(maxHp, 1), best.S, math.floor(best.x), math.floor(best.z)))
          end
        end
      end
    elseif retreating[uid] then
      retreating[uid], held[uid], chosen[uid] = nil, nil, nil
    end
  end
  for uid in pairs(retreating) do
    if Spring.GetUnitIsDead(uid) ~= false then retreating[uid], held[uid], chosen[uid] = nil, nil, nil end
  end
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

local function departSaying(why, f, said)
  Spring.Echo("VA_AUTOPILOT raptors go" .. (said or ""))
  return why, f
end

local function depart(why, f)
  if departureAt then return end
  departureAt, departureWhy = f, why
  held, retreating = {}, {}
  boarding = {}
  for _, uid in ipairs(companyUnits(mobile)) do boarding[uid] = true end
  Spring.Echo("VA_AUTOPILOT depart reason=" .. why .. " frame=" .. f)
  regroup()
end

-- Everyone mobile inside the pad's own radius, or three settles gone (a unit stuck on a cliff).
local function readyToLeave(f)
  if f - departureAt < SETTLE_FRAMES then return false end
  local px, pz, pr = rp("va_pad_x"), rp("va_pad_z"), math.max(1, rp("va_pad_r"))
  -- who was told to go: a lab still printing during the walk home kept "everyone" out of reach. In
  -- trial 18's third campaign a muster's 172 units grew to 178 while they boarded, the company waited
  -- the full three settles, and wave 12 landed on the walk and killed Ketha (2026-11-11).
  local mob, on = 0, 0
  for _, uid in ipairs(companyUnits(mobile)) do
    if boarding[uid] then
    mob = mob + 1
    local x, _, z = Spring.GetUnitPosition(uid)
    if x and ((x - px) ^ 2 + (z - pz) ^ 2) <= pr ^ 2 then on = on + 1 end
    end
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

-- ---------------------------------------------------------------- raptor waves
-- On raptor ground the danger keeps a schedule. The spawner (raptor_spawner_defense.lua) publishes each
-- wave's strength (va_raptor_wave_fight: the sum of (dps x hp)^1/2 of what it queued), when the next is
-- due (va_raptor_next_wave, game seconds) and its team (va_raptor_team). Lanchester, as the safety
-- field reckons it: the company's strength is the sum of (dps x hp)^1/2 of all its guns at the health
-- they have (turrets too: the raptors come to it); the raptors' is what the waves have sent and still
-- stands (the spawner tags it va_wave; the wild dens' residents guard their dens and do not march: counted
-- as all coming, they read r = 1 at every pad and the company left each sortie in its first second, trial
-- 11, 11-10), and the next wave will add what the last one brought (the forecast is the last wave).
-- With r = theirs / ours the company keeps sqrt(1 - r^2) of itself by winning. The objective is worth
-- what it risked to come for it, and is won with what is left standing: staying is worth twice what it
-- keeps, going all of it (the walk home is paid either way). So it fights while sqrt(1 - r^2) >= 1/2:
--   the fight on its hands is lost on that reckoning: it goes now;
--   the next wave would tip it: it is on the pad before that wave comes (it goes once the time until it
--   is no more than the slowest named hero's walk to the pad; the wave's own walk is not counted).
-- This replaced "60 s after the grace" (owner call 2026-11-09; history in docs/DEVLOG.md).
local function strengthOf(team, wavesOnly)
  local s = 0
  for _, uid in ipairs(Spring.GetTeamUnits(team) or {}) do
    local p = SafetyField.profile(Spring.GetUnitDefID(uid))
    if p.dps > 0 and (not wavesOnly or Spring.GetUnitRulesParam(uid, "va_wave") == 1) then
      local hp = tonumber((Spring.GetUnitHealth(uid))) or 0
      if hp > 0 then s = s + math.sqrt(p.dps * hp) end
    end
  end
  return s
end

local function keepOf(r) return r < 1 and math.sqrt(1 - r * r) or 0 end

local raptorSaid = -1
local function raptorsCall(f)
  local team = tonumber((Spring.GetGameRulesParam("va_raptor_team")))
  local nextWave = rp("va_raptor_next_wave")
  if not team or team < 0 or nextWave <= 0 then return nil end
  local ours, live, wave = strengthOf(playerTeam, false), strengthOf(team, true), rp("va_raptor_wave_fight")
  local rNow = ours > 0 and live / ours or math.huge
  local rNext = ours > 0 and (live + wave) / ours or math.huge
  local untilNext = nextWave - f / 30
  local px, pz, home = rp("va_pad_x"), rp("va_pad_z"), 0
  for _, uid in ipairs(Spring.GetTeamUnits(playerTeam) or {}) do
    if isHero(uid) then
      local x, _, z = Spring.GetUnitPosition(uid)
      local speed = SafetyField.profile(Spring.GetUnitDefID(uid)).speed
      if x and speed > 0 then home = math.max(home, math.sqrt((x - px) ^ 2 + (z - pz) ^ 2) / speed) end
    end
  end
  local said = string.format(" r_now=%.2f r_next=%.2f ours=%.0f raptors=%.0f wave=%.0f next_in=%.0fs home_in=%.0fs",
    math.min(rNow, 99), math.min(rNext, 99), ours, live, wave, untilNext, home)
  if keepOf(rNow) < 0.5 then return "raptors_now", said end
  if keepOf(rNext) < 0.5 and untilNext <= home then return "raptors_next", said end
  if f - raptorSaid >= 1800 then
    raptorSaid = f
    Spring.Echo("VA_AUTOPILOT raptors hold" .. said)
  end
end

-- ---------------------------------------------------------------- call-ins
function gadget:Initialize()
  gadgetHandler:RegisterAllowCommand(CMD.ANY)
  local ok, m = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  mission = ok and type(m) == "table" and m or nil
  playerTeam = tonumber(mission and mission.balance and mission.balance.playerTeamID) or 0
  -- one safety field per ally team, shared on GG (the hero doctrine reads the same one)
  local myAlly = select(6, Spring.GetTeamInfo(playerTeam, false)) or playerTeam
  GG.VA_SafetyFields = GG.VA_SafetyFields or {}
  field = GG.VA_SafetyFields[myAlly] or SafetyField.new(myAlly)
  GG.VA_SafetyFields[myAlly] = field
  local act = mission and type(mission.act) == "table" and mission.act or {}
  field:setCampaign(mission and mission.missionNumber or act.missionNumber, act.act2EndMission)
  -- a finale is a long fight (the gate's fusions and charge, the kings' war): three times the clock
  if mission and type(mission.finale) == "table" then CAP_FRAMES = CAP_FRAMES * 3 end
  -- the kings' showdown ends only with the throne: twice that again before the company gives up
  if mission and type(mission.kings) == "table" and #mission.kings > 0 then CAP_FRAMES = CAP_FRAMES * 2 end
  MUSTER = mission ~= nil and type(mission.muster) == "table"
  -- va_autopilot_profiles=1: every unit's fight profile, once, for the hub's reckoning
  -- (tools/harvest_fight_profiles.py -> data/story/unit_fight.json): the same numbers both sides
  if tostring(opts.va_autopilot_profiles) == "1" then
    local n = 0
    for id, ud in pairs(UnitDefs) do
      local p = SafetyField.profile(id)
      Spring.Echo(string.format("VA_FIGHT_PROFILE %s fight=%.3f dps=%.3f hp=%.1f range=%.1f speed=%.3f",
        tostring(ud.name), p.fight, p.dps, p.hp, p.range, p.speed))
      n = n + 1
    end
    Spring.Echo("VA_FIGHT_PROFILES_DONE n=" .. n)
  end
  Spring.Echo("VA_AUTOPILOT armed team=" .. playerTeam .. " cap=" .. CAP_FRAMES .. " settle=" .. SETTLE_FRAMES
    .. " mission=" .. tostring(mission and mission.missionId) .. (MUSTER and " muster" or ""))
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
    -- a muster (owner call, 2026-11-11: the builders spend all the Tenebrium) is not over when the
    -- gate is secured: the company stays and builds until the waves' forecast or the clock says go
    if rp("va_objective_complete") == 1 and not MUSTER then depart("objective", f)
    elseif rp("va_objective_failed") == 1 then depart("objective_failed", f)
    elseif f >= CAP_FRAMES then depart("clock", f)
    elseif RAPTOR_GRACE then
      local why, said = raptorsCall(f)
      if why then depart(departSaying(why, f, said)) end
    end
  end
  if departureAt then
    if (f - departureAt) % 450 == 0 and f > departureAt then regroup() end
    if readyToLeave(f) then return leave(departureWhy, f) end
    return
  end
  gateRig()
  if CAUTION_ON then caution(f) end   -- every pass (frames run at f % 30 == 11: once a second)
  if f % RESCUE_EVERY == 311 then rescue(f) end
  if f % NUDGE_EVERY < 30 then siege(); holdTheZone(); nudge() end
  if f % NUDGE_EVERY == 341 then scout() end   -- (frames run at f % 30 == 11; 311 is the rescue)
end
