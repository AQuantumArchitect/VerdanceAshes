-- Verdance pack mechanical overlay.
-- Chassis-agnostic layer that sits on crew packs: speed share + order drag.
-- Not a hero-tag perk. Units with baked mobility (Saloon marks, etc.) opt out
-- of the speed leg via customParams.verdance_baked_mobility.

local M = {}

M.SPEED_MULT = 1.18          -- swarm stride (was 1.50 — too slippery on Phobos)
M.SPEED_RADIUS = 1400        -- near-pad / zone fallback
M.DRAG_IDLE_RADIUS = 1100
-- Only swarm minds get order-drag + pack speed. pair/solo keep line-spread.
M.SWARM_MIND = "swarm"

local Mobility = nil
local Crew = nil
do
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_mobility.lua")
  if ok and type(mod) == "table" then Mobility = mod end
end
do
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_crew_roster.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_crew_roster.lua")
  end
  if ok and type(mod) == "table" then Crew = mod end
end

function M.packMindFor(packId, unitID)
  local stamped = Spring.GetUnitRulesParam(unitID, "va_pack_mind")
  if stamped and tostring(stamped) ~= "" then
    return string.lower(tostring(stamped))
  end
  packId = tostring(packId or Spring.GetUnitRulesParam(unitID, "va_pack_id")
    or Spring.GetUnitRulesParam(unitID, "va_hero_id") or "")
  local row = Crew and Crew.HEROES and Crew.HEROES[packId]
  local mind = row and row.packMind
  if mind and tostring(mind) ~= "" then
    return string.lower(tostring(mind))
  end
  -- Legacy heuristic if roster row missing packMind.
  local n = row and tonumber(row.packTotal) or 0
  if n >= 6 then return "swarm" end
  if n == 2 then return "pair" end
  return "solo"
end

function M.isSwarmMind(packId, unitID)
  return M.packMindFor(packId, unitID) == (M.SWARM_MIND or "swarm")
end

function M.hasBakedMobility(unitDefID)
  if Mobility and Mobility.hasBakedMobility then
    return Mobility.hasBakedMobility(unitDefID)
  end
  return false
end

function M.packIdFromPackage(pkg)
  pkg = tostring(pkg or "")
  -- crew_<id> / crew_pack_<id> / crew_escort_<id>_N / crew_mint_<id>
  local id = pkg:match("^crew_pack_(.+)$")
    or pkg:match("^crew_escort_([^_]+)")
    or pkg:match("^crew_mint_(.+)$")
    or pkg:match("^crew_([^_]+)$")
  return id
end

function M.samePackFamily(pkg, packId)
  pkg = tostring(pkg or "")
  packId = tostring(packId or "")
  if pkg == "" or packId == "" then return false end
  return pkg:find(packId, 1, true) ~= nil
end

function M.sameZone(a, b)
  local za = Spring.GetUnitRulesParam(a, "va_shell_zone")
  local zb = Spring.GetUnitRulesParam(b, "va_shell_zone")
  if za and zb and tostring(za) ~= "" and tostring(za) == tostring(zb) then
    return true
  end
  return false
end

-- Stamp pack leg + compose with field/vet via va_mobility (elmos/sec, never /30).
function M.applySpeedMult(unitID, speedMult)
  if not unitID or not Spring.ValidUnitID(unitID) then return false end
  if not speedMult or math.abs(speedMult - 1) < 0.01 then return false end
  if Mobility and Mobility.setPackMult then
    return Mobility.setPackMult(unitID, speedMult)
  end
  return false
end

function M.stampMember(unitID, packId, role)
  if not unitID or not Spring.ValidUnitID(unitID) then return end
  packId = tostring(packId or "")
  role = tostring(role or "mate")
  if packId ~= "" then
    Spring.SetUnitRulesParam(unitID, "va_pack_id", packId, { public = true })
  end
  Spring.SetUnitRulesParam(unitID, "va_pack_role", role, { public = true })
  Spring.SetUnitRulesParam(unitID, "va_pack_overlay", 1, { public = true })
  local mind = M.packMindFor(packId, unitID)
  Spring.SetUnitRulesParam(unitID, "va_pack_mind", mind, { public = true })
end

-- Swarm-only stride to lead + same-def mates in pack / zone / nearby.
-- Skips baked-mobility chassis (Saloon Stride gunslingers, etc.).
function M.applyPackSpeed(leadUnitID, packId, speedMult)
  speedMult = tonumber(speedMult) or M.SPEED_MULT
  if not leadUnitID or not Spring.ValidUnitID(leadUnitID) then return 0 end
  packId = tostring(packId or Spring.GetUnitRulesParam(leadUnitID, "va_pack_id")
    or Spring.GetUnitRulesParam(leadUnitID, "va_hero_id") or "")
  M.stampMember(leadUnitID, packId, "lead")
  if not M.isSwarmMind(packId, leadUnitID) then
    Spring.SetUnitRulesParam(leadUnitID, "va_pack_speed_mult", 1, { public = true })
    Spring.SetUnitRulesParam(leadUnitID, "va_pack_speed_skip", "pack_mind", { public = true })
    return 0
  end
  local dID = Spring.GetUnitDefID(leadUnitID)
  if not dID then return 0 end
  if M.hasBakedMobility(dID) then
    Spring.SetUnitRulesParam(leadUnitID, "va_pack_speed_mult", 1, { public = true })
    Spring.SetUnitRulesParam(leadUnitID, "va_pack_speed_skip", "baked_mobility", { public = true })
    return 0
  end
  local team = Spring.GetUnitTeam(leadUnitID)
  if team == nil then return 0 end
  local hx, _, hz = Spring.GetUnitPosition(leadUnitID)
  if not hx then return 0 end
  M.applySpeedMult(leadUnitID, speedMult)

  local r2 = M.SPEED_RADIUS * M.SPEED_RADIUS
  local n = 0
  local units = Spring.GetTeamUnitsByDefs(team, dID) or {}
  for i = 1, #units do
    local uid = units[i]
    if uid ~= leadUnitID and Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local pkg = Spring.GetUnitRulesParam(uid, "va_package_tag")
      local pid = Spring.GetUnitRulesParam(uid, "va_pack_id")
      local near = false
      local ux, _, uz = Spring.GetUnitPosition(uid)
      if ux then
        local dx, dz = ux - hx, uz - hz
        near = (dx * dx + dz * dz) <= r2
      end
      local inFamily = M.samePackFamily(pkg, packId)
        or (pid and tostring(pid) == packId)
        or M.sameZone(leadUnitID, uid)
        or near
      if inFamily then
        M.stampMember(uid, packId, "mate")
        if M.applySpeedMult(uid, speedMult) then
          n = n + 1
        end
      end
    end
  end
  return n
end

-- Mirror MOVE/FIGHT/PATROL from pack lead onto same-def pack mates (swarm only).
function M.dragPack(leadUnitID, cmdID, cmdParams, cmdOptions)
  if not leadUnitID or not Spring.ValidUnitID(leadUnitID) then return 0 end
  local dID = Spring.GetUnitDefID(leadUnitID)
  local team = Spring.GetUnitTeam(leadUnitID)
  if not dID or team == nil then return 0 end
  local packId = tostring(Spring.GetUnitRulesParam(leadUnitID, "va_pack_id")
    or Spring.GetUnitRulesParam(leadUnitID, "va_hero_id") or "")
  if packId == "" then return 0 end
  if not M.isSwarmMind(packId, leadUnitID) then
    return 0
  end
  local hx, _, hz = Spring.GetUnitPosition(leadUnitID)
  if not hx then return 0 end
  local opts = {}
  if type(cmdOptions) == "table" then
    if cmdOptions.shift then opts[#opts + 1] = "shift" end
    if cmdOptions.alt then opts[#opts + 1] = "alt" end
    if cmdOptions.ctrl then opts[#opts + 1] = "ctrl" end
  end
  if type(cmdParams) ~= "table" then return 0 end

  local function queueLen(uid)
    local n = Spring.GetUnitCommands(uid, 0)
    if type(n) == "number" then return n end
    local q = Spring.GetUnitCommands(uid, 1)
    return (q and #q) or 0
  end

  local dragged = 0
  local idleR2 = M.DRAG_IDLE_RADIUS * M.DRAG_IDLE_RADIUS
  local mates = Spring.GetTeamUnitsByDefs(team, dID) or {}
  for i = 1, #mates do
    local uid = mates[i]
    if uid ~= leadUnitID and Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local pkg = tostring(Spring.GetUnitRulesParam(uid, "va_package_tag") or "")
      local pid = tostring(Spring.GetUnitRulesParam(uid, "va_pack_id") or "")
      local isPack = M.samePackFamily(pkg, packId) or (pid == packId)
      if not isPack then
        local ux, _, uz = Spring.GetUnitPosition(uid)
        if ux and queueLen(uid) <= 0 then
          local dx, dz = ux - hx, uz - hz
          if (dx * dx + dz * dz) <= idleR2 then
            isPack = true
          end
        end
      end
      if isPack then
        if pcall(Spring.GiveOrderToUnit, uid, cmdID, cmdParams, opts) then
          dragged = dragged + 1
          Spring.SetUnitRulesParam(uid, "va_behavior", "pack_drag", { public = true })
          M.stampMember(uid, packId, "mate")
        end
      end
    end
  end
  if dragged > 0 then
    Spring.SetUnitRulesParam(leadUnitID, "va_pack_drag_n", dragged, { public = true })
  end
  return dragged
end

return M
