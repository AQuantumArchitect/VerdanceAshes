-- The Spire Jump (finale C on the Rock Jungle, verdance.campaign.acts): the company leaves the jungle
-- through the Spire Gate (va_jump_gate). mission.jumpGate places it:
--   1. its frame stands unfinished on the spires (the company's; constructors finish it);
--   2. finished, it charges while the company owns needAfus advanced fusions within radius of it,
--      and drains when it owns fewer;
--   3. charged, a named hero who holds on the gate's pad for channelSeconds is ported out (removed,
--      no wreck, reported survived and going home); the rest of the army holds the line;
--   4. every step makes the raptors angrier (GG.VA_RaptorRage in raptor_spawner_defense.lua), and the
--      last hero through wakes the queen. Every surviving named hero through = the objective.
function gadget:GetInfo()
  return {
    name = "Verdance Spire Gate",
    desc = "The Rock Jungle's way out: finish the gate, power it from four advanced fusions, port the named heroes",
    author = "Verdance",
    layer = 0,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local cfg
local gateID
local charge = 0                 -- 0..1
local channel = {}               -- unitID -> seconds held on the pad
local ported = {}                -- ordered { heroId, name, unitDef }
local portedById = {}
local onlineAnnounced, chargedAnnounced, done = false, false, false
local endFrame                   -- the sortie closes a few seconds after the last hero goes through
local playerTeam = 0
local AFUS = {}
local heldBuilt = 0              -- the frame never decays below what the company has built of it

function gadget:Initialize()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  cfg = ok and type(data) == "table" and data.jumpGate or nil
  if type(cfg) ~= "table" or not UnitDefNames["va_jump_gate"] then
    gadgetHandler:RemoveGadget(self)
    return
  end
  playerTeam = tonumber(data.balance and data.balance.playerTeamID) or 0
  for id, ud in pairs(UnitDefs) do
    local n = ud.name or ""
    if n == "armafus" or n == "corafus" or n == "legafus" or n:find("^va_.*afus") then AFUS[id] = true end
  end
  GG.VA_JumpPorted = function() return ported end
end

local function rage(aggression, anger)
  if GG.VA_RaptorRage then pcall(GG.VA_RaptorRage, aggression, anger) end
end

local placedX, placedZ           -- where the frame actually stands (sited near the zone's anchor)

local function anchorXZ()
  local x, z = tonumber(cfg.x) or 0.5, tonumber(cfg.z) or 0.5
  if x <= 1.5 then x = x * Game.mapSizeX end
  if z <= 1.5 then z = z * Game.mapSizeZ end
  return x, z
end

local function xz()
  if placedX then return placedX, placedZ end
  return anchorXZ()
end

-- Can a ground constructor walk from the drop pad to (x, z)? The anchor of TRJ_NW_MUSTER sits on rock
-- the company's builders cannot climb: in the finale-C rehearsals (2026-11-03) both stood 560 elmos
-- off with a repair order for 45 minutes and the frame never left 5%.
local function walkable(x, z)
  local px = tonumber((Spring.GetGameRulesParam("va_pad_x"))) or 0
  local pz = tonumber((Spring.GetGameRulesParam("va_pad_z"))) or 0
  if px <= 0 or not Spring.RequestPath then return true end
  local ud = UnitDefNames["legck"] or UnitDefNames["armck"]
  local md = ud and ud.moveDef and ud.moveDef.name
  if not md then return true end
  local ok, path = pcall(Spring.RequestPath, md, px, Spring.GetGroundHeight(px, pz) or 0, pz,
    x, Spring.GetGroundHeight(x, z) or 0, z, 160)
  if not ok or not path then return false end
  local okw, pts = pcall(path.GetPathWayPoints, path)
  if not okw or type(pts) ~= "table" or #pts == 0 then return false end
  local last = pts[#pts]
  local lx, lz = last[1], last[3]
  return lx ~= nil and ((lx - x) ^ 2 + (lz - z) ^ 2) <= 260 * 260
end

-- The nearest place to the anchor where the gate fits on the ground and a builder can reach it.
local function siteGate(gateDef)
  local ax, az = anchorXZ()
  for _, r in ipairs({ 0, 200, 400, 600, 800, 1000, 1300, 1600, 2000 }) do
    local steps = (r == 0) and 1 or 16
    for k = 0, steps - 1 do
      local a = (k / steps) * 2 * math.pi
      local x, z = ax + math.cos(a) * r, az + math.sin(a) * r
      if x > 100 and z > 100 and x < Game.mapSizeX - 100 and z < Game.mapSizeZ - 100 then
        local y = Spring.GetGroundHeight(x, z) or 0
        local fits = (Spring.TestBuildOrder(gateDef, x, y, z, 0) or 0) > 0
        if fits and walkable(x, z) then return x, z, r end
      end
    end
  end
  return ax, az, -1
end

-- Where the gate and its pad are, for the HUD and the autopilot rig (game_verdance_autopilot.lua).
local function publishGate(x, z)
  Spring.SetGameRulesParam("va_gate_x", math.floor(x), { public = true })
  Spring.SetGameRulesParam("va_gate_z", math.floor(z), { public = true })
  Spring.SetGameRulesParam("va_gate_unit", gateID or 0, { public = true })
  Spring.SetGameRulesParam("va_gate_pad_r", tonumber(cfg.padRadius) or 220, { public = true })
end

local function placeFrame()
  -- A gate from an earlier try (company footprints rehydrate the works) is the gate: adopt it.
  local gateDef = UnitDefNames["va_jump_gate"].id
  for _, uid in ipairs(Spring.GetTeamUnits(playerTeam) or {}) do
    if Spring.GetUnitDefID(uid) == gateDef then
      gateID = uid
      local ux, _, uz = Spring.GetUnitPosition(uid)
      if ux then placedX, placedZ = ux, uz end
      publishGate(xz())   -- the pad is the gate's own place (GameFrame measures from xz())
      Spring.Echo("VA_GATE_ADOPTED unit=" .. uid)
      return
    end
  end
  local x, z, moved = siteGate(gateDef)
  placedX, placedZ = x, z
  Spring.Echo("VA_GATE_SITED at=" .. math.floor(x) .. "," .. math.floor(z) .. " off_anchor=" .. tostring(moved))
  local y = Spring.GetGroundHeight(x, z)
  -- Born finished, then set back to a frame: a nanoframe born with no live builder and ~0 hp is
  -- what BAR's Prevent Lab Hax2 kills on sight. Its health follows its build progress.
  gateID = Spring.CreateUnit("va_jump_gate", x, y, z, 0, playerTeam, false)
  if gateID then
    publishGate(x, z)
    local b = tonumber(cfg.startBuilt) or 0.05
    local _, maxHp = Spring.GetUnitHealth(gateID)
    Spring.SetUnitHealth(gateID, { build = b, health = math.max(100, (maxHp or 24000) * b) })
    Spring.SetUnitRulesParam(gateID, "va_label", "The Spire Gate", { public = true })
    local _, _, _, _, nowBuilt = Spring.GetUnitHealth(gateID)
    Spring.Echo("VA_GATE_FRAME at=" .. math.floor(x) .. "," .. math.floor(z) .. " built=" .. tostring(nowBuilt)
      .. " frame=" .. tostring(Spring.GetUnitIsBeingBuilt and Spring.GetUnitIsBeingBuilt(gateID)))
  else
    Spring.Echo("VA_GATE_FRAME_FAIL")
  end
end

local function afusNear(x, z, r)
  local n = 0
  for _, uid in ipairs(Spring.GetUnitsInCylinder(x, z, r, playerTeam) or {}) do
    if AFUS[Spring.GetUnitDefID(uid)] then
      local _, _, _, _, built = Spring.GetUnitHealth(uid)
      if (built or 1) >= 1 then n = n + 1 end
    end
  end
  return n
end

local function heroesLeft()
  local list = {}
  for _, uid in ipairs(Spring.GetTeamUnits(playerTeam) or {}) do
    local hid = Spring.GetUnitRulesParam(uid, "va_hero_id")
    local partner = Spring.GetUnitRulesParam(uid, "va_partner_of")
    if hid and hid ~= "" and hid ~= 0 and not (partner and partner ~= "") and not portedById[tostring(hid)] then
      list[#list + 1] = uid
    end
  end
  return list
end

local function port(uid)
  local hid = tostring(Spring.GetUnitRulesParam(uid, "va_hero_id") or "")
  local name = tostring(Spring.GetUnitRulesParam(uid, "va_hero_name") or hid)
  local ud = UnitDefs[Spring.GetUnitDefID(uid)]
  ported[#ported + 1] = { heroId = hid, name = name, unitDef = ud and ud.name or "", ported = true }
  portedById[hid] = true
  if GG.VA_HeroPorted then pcall(GG.VA_HeroPorted, hid) end
  local x, y, z = Spring.GetUnitPosition(uid)
  if x and Spring.SpawnCEG then pcall(Spring.SpawnCEG, "teleport", x, y + 20, z) end
  Spring.DestroyUnit(uid, false, true)
  Spring.SetGameRulesParam("va_gate_ported", #ported, { public = true })
  Spring.Echo("VA_GATE_PORTED hero=" .. hid .. " n=" .. #ported)
  rage(tonumber(cfg.ragePerHero) or 6, tonumber(cfg.angerPerHero) or 8)
end

function gadget:GameFrame(frame)
  if done then
    if endFrame and frame >= endFrame then
      endFrame = nil
      -- the company's ride home: the ported heroes go, the army that held the line stays as the garrison
      local okc, res = false, nil
      if GG.VA_ExfilCmd then okc, res = pcall(GG.VA_ExfilCmd, "extract:home") end
      if not (okc and res) and GG.VA_EndSortie then GG.VA_EndSortie("extracted") end
    end
    return
  end
  if frame == 6 then placeFrame() end
  if frame < 30 or frame % 30 ~= 0 then return end
  if not gateID or not Spring.ValidUnitID(gateID) or Spring.GetUnitIsDead(gateID) then
    if gateID then
      Spring.Echo("VA_GATE_LOST")
      Spring.SetGameRulesParam("va_gate_state", "lost", { public = true })
      gateID = nil
    end
    return
  end
  local x, z = xz()
  local hp, maxHp, _, _, built = Spring.GetUnitHealth(gateID)
  built = built or 0
  if built < 1 then
    -- BAR decays abandoned frames (modrules constructionDecay); this one waits for the company.
    if built < heldBuilt then
      -- give back only what the decay took (damage the raptors did stays done)
      Spring.SetUnitHealth(gateID, { build = heldBuilt, health = (hp or 0) + (maxHp or 24000) * (heldBuilt - built) })
      built = heldBuilt
    end
    heldBuilt = built
  end
  Spring.SetGameRulesParam("va_gate_built", built, { public = true })
  if built < 1 then
    Spring.SetGameRulesParam("va_gate_state", "frame", { public = true })
    return
  end
  local need = tonumber(cfg.needAfus) or 4
  local have = afusNear(x, z, tonumber(cfg.radius) or 2200)
  Spring.SetGameRulesParam("va_gate_afus", have, { public = true })
  Spring.SetGameRulesParam("va_gate_afus_need", need, { public = true })
  local chargeSeconds = tonumber(cfg.chargeSeconds) or 120
  if have >= need then
    if not onlineAnnounced then
      onlineAnnounced = true
      Spring.Echo("VA_GATE_ONLINE afus=" .. have)
      rage(tonumber(cfg.rageOnline) or 10, tonumber(cfg.angerOnline) or 10)
    end
    charge = math.min(1, charge + 1 / chargeSeconds)
  else
    charge = math.max(0, charge - 2 / chargeSeconds)
  end
  Spring.SetGameRulesParam("va_gate_charge", charge, { public = true })
  if charge < 1 then
    Spring.SetGameRulesParam("va_gate_state", have >= need and "charging" or "unpowered", { public = true })
    return
  end
  Spring.SetGameRulesParam("va_gate_state", "open", { public = true })
  if not chargedAnnounced then
    chargedAnnounced = true
    Spring.Echo("VA_GATE_OPEN")
  end
  -- Charged: the pad sends one hero at a time; whoever has held it longest goes when its channel fills.
  local padR = tonumber(cfg.padRadius) or 220
  local need_s = tonumber(cfg.channelSeconds) or 8
  local onPad, first = {}, nil
  for _, uid in ipairs(heroesLeft()) do
    local ux, _, uz = Spring.GetUnitPosition(uid)
    if ux and (ux - x) ^ 2 + (uz - z) ^ 2 <= padR * padR then
      onPad[uid] = true
      channel[uid] = channel[uid] or 0
      if not first or channel[uid] > channel[first] then first = uid end
    end
  end
  for uid in pairs(channel) do if not onPad[uid] then channel[uid] = nil end end
  if first then
    channel[first] = channel[first] + 1
    Spring.SetGameRulesParam("va_gate_channel", channel[first] / need_s, { public = true })
    if channel[first] >= need_s then
      channel[first] = nil
      port(first)
    end
  end
  if #ported > 0 and #heroesLeft() == 0 then
    done = true
    rage(50, 100)  -- the last one through wakes the queen
    Spring.Echo("VA_GATE_JUMPED heroes=" .. #ported)
    if GG.VA_ObjectiveComplete then GG.VA_ObjectiveComplete("jumped") end
    endFrame = frame + 150
  end
end
