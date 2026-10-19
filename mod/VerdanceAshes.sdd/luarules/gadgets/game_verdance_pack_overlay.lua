local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Pack Overlay",
    desc = "Mechanical pack layer: +50% same-chassis stride + order drag. Not tag-driven.",
    author = "Verdance",
    date = "2026-09-07",
    license = "GPL v2 or later",
    layer = 3,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  return
end

--[[
  Overlapping mechanical overlay for crew packs.

  - Stamp va_pack_id / va_pack_role on hero + crew_pack_* mates at spawn.
  - Swarm packMind only: modest pack stride + order drag.
  - pair/solo (Javelins, singles) keep player line-spread — no drag.
  - Baked-mobility chassis skip the speed leg.

  Tags stay fiction/HP/range/build. Mobility cohesion lives here.
]]

local Pack = nil
local Mobility = nil
do
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_pack_overlay.lua")
  if not ok then
    ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_pack_overlay.lua")
  end
  if ok and type(mod) == "table" then
    Pack = mod
  else
    Spring.Echo("VA_PACK_OVERLAY_LOAD_FAIL " .. tostring(mod))
    Pack = nil
  end
end
do
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_mobility.lua")
  if ok and type(mod) == "table" then Mobility = mod end
end

local enabled = true
local dragEnabled = true -- order-mirror; line-spread dies when this is on
local playerTeam = 0
local packDragBusy = {}
local pendingRefresh = {} -- packId -> frame to re-apply after late mates spawn

local CMD_MOVE = CMD and CMD.MOVE
local CMD_FIGHT = CMD and CMD.FIGHT
local CMD_PATROL = CMD and CMD.PATROL
local PACK_DRAG_CMDS = {}
if CMD_MOVE then PACK_DRAG_CMDS[CMD_MOVE] = true end
if CMD_FIGHT then PACK_DRAG_CMDS[CMD_FIGHT] = true end
if CMD_PATROL then PACK_DRAG_CMDS[CMD_PATROL] = true end

local Util = nil
do
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_util.lua")
  if ok and type(mod) == "table" then Util = mod end
end
local function truthy(v)
  return Util and Util.truthy and Util.truthy(v)
    or (v == true or v == 1)
end
local function resolvePlayerTeam()
  if Util and Util.resolvePlayerTeam then return Util.resolvePlayerTeam() end
  return 0
end

local function echoStatus(tag)
  Spring.Echo((tag or "VA_PACK")
    .. " enabled=" .. tostring(enabled and true or false)
    .. " drag=" .. tostring(dragEnabled and true or false)
    .. " pack_mod=" .. tostring(Pack ~= nil)
    .. " team=" .. tostring(playerTeam)
    .. " spd×" .. tostring(Pack and Pack.SPEED_MULT or "?"))
  Spring.SetGameRulesParam("va_pack_overlay", enabled and 1 or 0, { public = true })
  Spring.SetGameRulesParam("va_pack_drag", dragEnabled and 1 or 0, { public = true })
end

local function clearPackSpeedOnTeam()
  if not Pack or not Mobility then return 0 end
  local n = 0
  local units = Spring.GetTeamUnits(playerTeam) or {}
  for i = 1, #units do
    local uid = units[i]
    if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
      local marked = Spring.GetUnitRulesParam(uid, "va_pack_overlay")
        or Spring.GetUnitRulesParam(uid, "va_pack_id")
      if marked then
        if Mobility.setPackMult and Mobility.setPackMult(uid, 1) then
          n = n + 1
        end
      end
    end
  end
  return n
end

local function refreshPackFromLead(leadUnitID, packId)
  if not Pack or not leadUnitID then return end
  packId = tostring(packId or Spring.GetUnitRulesParam(leadUnitID, "va_pack_id")
    or Spring.GetUnitRulesParam(leadUnitID, "va_hero_id") or "")
  if packId == "" then return end
  local n = Pack.applyPackSpeed(leadUnitID, packId, Pack.SPEED_MULT)
  Spring.Echo("VA_PACK_OVERLAY lead=" .. tostring(leadUnitID)
    .. " pack=" .. packId
    .. " mates_sped=" .. tostring(n)
    .. " baked=" .. tostring(Pack.hasBakedMobility(Spring.GetUnitDefID(leadUnitID))))
end

-- Public hook for campaign after crew pack spawn.
GG = GG or {}
GG.VA_PackOverlayRefresh = function(leadUnitID, packId)
  if not enabled or not Pack then return 0 end
  if not leadUnitID or not Spring.ValidUnitID(leadUnitID) then return 0 end
  packId = tostring(packId or Spring.GetUnitRulesParam(leadUnitID, "va_hero_id") or "")
  Pack.stampMember(leadUnitID, packId, "lead")
  return Pack.applyPackSpeed(leadUnitID, packId, Pack.SPEED_MULT)
end

GG.VA_PackOverlayStamp = function(unitID, packId, role)
  if not Pack or not unitID then return end
  Pack.stampMember(unitID, packId, role or "mate")
end

-- Pack leg only (legacy name kept for call sites).
GG.VA_PackApplySpeed = function(unitID, speedMult)
  if not Pack or not unitID then return false end
  return Pack.applySpeedMult(unitID, speedMult)
end

-- Mid-Drop A/B: /vapack off|on|drag off|drag on|status
GG.VA_PackSet = function(opts)
  opts = opts or {}
  if opts.enabled ~= nil then enabled = opts.enabled and true or false end
  if opts.drag ~= nil then dragEnabled = opts.drag and true or false end
  if not enabled then
    dragEnabled = false
    local cleared = clearPackSpeedOnTeam()
    Spring.Echo("VA_PACK_CLEARED_SPEED n=" .. tostring(cleared))
  end
  echoStatus("VA_PACK_SET")
  return enabled, dragEnabled
end

GG.VA_PackStatus = function()
  echoStatus("VA_PACK_STATUS")
  return enabled, dragEnabled
end

-- Shared mobility composer (pack × field × vet).
GG.VA_MobilityApply = function(unitID, opts)
  if not Mobility or not unitID then return false end
  return Mobility.apply(unitID, opts)
end
GG.VA_MobilitySetField = function(unitID, speedMult)
  if not Mobility or not unitID then return false end
  return Mobility.setFieldMult(unitID, speedMult)
end
GG.VA_MobilitySetVet = function(unitID, speedMult, move)
  if not Mobility or not unitID then return false end
  return Mobility.setVetMult(unitID, speedMult, move)
end
GG.VA_MobilitySetPack = function(unitID, speedMult)
  if not Mobility or not unitID then return false end
  return Mobility.setPackMult(unitID, speedMult)
end

local function parseOnOff(tok)
  tok = string.lower(tostring(tok or ""))
  if tok == "on" or tok == "1" or tok == "true" or tok == "yes" then return true end
  if tok == "off" or tok == "0" or tok == "false" or tok == "no" then return false end
  return nil
end

-- /vapack [status|on|off|drag on|drag off]
local function runVapackCommand(command)
  if type(command) ~= "string" then return false end
  local head = command:match("^(%S+)")
  if not head or string.lower(head) ~= "vapack" then return false end
  local rest = command:match("^%S+%s+(.+)$") or ""
  rest = string.lower(rest:match("^%s*(.-)%s*$") or "")
  if rest == "" or rest == "status" or rest == "?" then
    echoStatus("VA_PACK_STATUS")
    return true
  end
  if rest == "help" then
    Spring.Echo("VA_PACK help: /vapack status|on|off|drag on|drag off")
    Spring.Echo("VA_PACK tip: line-spread fails when drag=on (lead MOVE mirrors to mates)")
    return true
  end
  local dragTok = rest:match("^drag%s+(%S+)")
  if dragTok then
    local on = parseOnOff(dragTok)
    if on == nil then
      Spring.Echo("VA_PACK_BAD use /vapack drag on|off")
      return true
    end
    if GG.VA_PackSet then GG.VA_PackSet({ drag = on }) end
    return true
  end
  local on = parseOnOff(rest)
  if on == nil then
    Spring.Echo("VA_PACK_BAD use /vapack status|on|off|drag on|drag off")
    return true
  end
  if GG.VA_PackSet then
    if on then
      GG.VA_PackSet({ enabled = true, drag = true })
    else
      GG.VA_PackSet({ enabled = false, drag = false })
    end
  end
  return true
end

function gadget:Initialize()
  local opts = Spring.GetModOptions() or {}
  if opts.va_pack_overlay ~= nil then
    enabled = truthy(opts.va_pack_overlay)
  end
  if opts.va_pack_drag ~= nil then
    dragEnabled = truthy(opts.va_pack_drag)
  end
  if not enabled then dragEnabled = false end
  playerTeam = resolvePlayerTeam()
  if enabled and Pack then
    Spring.Echo("VA_PACK_OVERLAY_ARMED team=" .. tostring(playerTeam)
      .. " spd×" .. tostring(Pack.SPEED_MULT)
      .. " drag=" .. tostring(dragEnabled)
      .. " (baked-mobility chassis skip speed; /vapack to A/B)")
  else
    Spring.Echo("VA_PACK_OVERLAY_OFF pack=" .. tostring(Pack ~= nil))
  end
  echoStatus("VA_PACK_INIT")
end

function gadget:GameStart()
  playerTeam = resolvePlayerTeam()
end

function gadget:TextCommand(command)
  -- Backup path when the campaign widget is not loaded; widget uses VA_CMD → campaign → GG.VA_PackSet.
  return runVapackCommand(command)
end

function gadget:UnitFinished(unitID, unitDefID, unitTeam)
  if not enabled or not Pack or unitTeam ~= playerTeam then return end
  local heroId = Spring.GetUnitRulesParam(unitID, "va_hero_id")
  local pkg = Spring.GetUnitRulesParam(unitID, "va_package_tag")
  if heroId and (Spring.GetUnitRulesParam(unitID, "va_hero") or 0) == 1 then
    Pack.stampMember(unitID, heroId, "lead")
    -- Mates may still be spawning — schedule refresh.
    pendingRefresh[tostring(heroId)] = (Spring.GetGameFrame() or 0) + 8
    refreshPackFromLead(unitID, heroId)
    return
  end
  local packId = Pack.packIdFromPackage(pkg)
  if packId then
    Pack.stampMember(unitID, packId, "mate")
    pendingRefresh[packId] = (Spring.GetGameFrame() or 0) + 5
  end
end

function gadget:UnitDestroyed(unitID)
  packDragBusy[unitID] = nil
end

function gadget:UnitCommand(unitID, unitDefID, unitTeam, cmdID, cmdParams, cmdOptions, _cmdTag)
  if not enabled or not dragEnabled or not Pack or unitTeam ~= playerTeam then return end
  if not PACK_DRAG_CMDS[cmdID] then return end
  if (Spring.GetUnitRulesParam(unitID, "va_hero") or 0) ~= 1
    and tostring(Spring.GetUnitRulesParam(unitID, "va_pack_role") or "") ~= "lead" then
    return
  end
  local frame = Spring.GetGameFrame() or 0
  if packDragBusy[unitID] and frame - packDragBusy[unitID] < 2 then return end
  local packId = Spring.GetUnitRulesParam(unitID, "va_pack_id")
    or Spring.GetUnitRulesParam(unitID, "va_hero_id")
  if not packId then return end
  Pack.stampMember(unitID, packId, "lead")
  local n = Pack.dragPack(unitID, cmdID, cmdParams, cmdOptions)
  if n > 0 then
    packDragBusy[unitID] = frame
    Spring.Echo("VA_PACK_DRAG n=" .. tostring(n)
      .. " lead=" .. tostring(unitID)
      .. " pack=" .. tostring(packId)
      .. " cmd=" .. tostring(cmdID))
  end
end

function gadget:GameFrame(frame)
  if not enabled or not Pack then return end
  if frame % 4 ~= 0 then return end
  for packId, due in pairs(pendingRefresh) do
    if frame >= due then
      pendingRefresh[packId] = nil
      -- Find lead by hero id / pack role.
      local units = Spring.GetTeamUnits(playerTeam) or {}
      for i = 1, #units do
        local uid = units[i]
        local role = Spring.GetUnitRulesParam(uid, "va_pack_role")
        local pid = Spring.GetUnitRulesParam(uid, "va_pack_id")
          or Spring.GetUnitRulesParam(uid, "va_hero_id")
        if tostring(pid) == tostring(packId)
          and (role == "lead" or (Spring.GetUnitRulesParam(uid, "va_hero") or 0) == 1) then
          refreshPackFromLead(uid, packId)
          break
        end
      end
    end
  end
end
