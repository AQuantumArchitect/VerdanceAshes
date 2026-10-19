local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Playfeel",
    desc = "Selected-unit power chip, vet rank-up juice, bring-home nudges, wreck opportunity pings",
    author = "Verdance",
    date = "2026-09-06",
    license = "GPL v2 or later",
    layer = 7,
    enabled = true,
  }
end

--[[
  Easy-win playfeel layer (does not own mission rules):
  - Selected unit: hero · vet · craft stack line ("why am I strong?")
  - Rank-up flash + bark
  - Periodic bring-home nudge after objectives are done
  - Soft wreck/rez opportunity ping near constructors
  - Retreat corridor paint: deploy → extract guide + hurt-unit rays
]]

local vsx, vsy = Spring.GetViewGeometry()
local flashUntil = 0
local flashLabel = ""
local flashColor = { 0.49, 1.0, 0.54, 1 }
local lastBringHome = -99999
local lastWreckPing = -99999
local lastAllDone = false
local selectedChip = nil

local COL_GOOD = { 0.490, 1.000, 0.541, 1 }
local COL_GOLD = { 0.831, 0.769, 0.604, 1 }
local COL_STEAM = { 0.55, 0.78, 0.92, 1 }
local COL_INK = { 0.92, 0.94, 0.90, 1 }
local COL_DIM = { 0.65, 0.70, 0.66, 1 }
local COL_BAD = { 1.000, 0.490, 0.490, 1 }

do
  local ok, Ash = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(Ash) ~= "table" then
    ok, Ash = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua")
  end
  if ok and type(Ash) == "table" and Ash.COL then
    COL_GOOD = { Ash.COL.good[1], Ash.COL.good[2], Ash.COL.good[3], 1 }
    COL_GOLD = { Ash.COL.gold[1], Ash.COL.gold[2], Ash.COL.gold[3], 1 }
    COL_STEAM = { (Ash.COL.steam or Ash.COL.blue)[1], (Ash.COL.steam or Ash.COL.blue)[2], (Ash.COL.steam or Ash.COL.blue)[3], 1 }
    COL_INK = { Ash.COL.ink[1], Ash.COL.ink[2], Ash.COL.ink[3], 1 }
    COL_DIM = { Ash.COL.ash[1], Ash.COL.ash[2], Ash.COL.ash[3], 1 }
    COL_BAD = { Ash.COL.bad[1], Ash.COL.bad[2], Ash.COL.bad[3], 1 }
  end
end

local function numParam(key, default)
  local v = Spring.GetGameRulesParam(key)
  v = tonumber(v)
  if v == nil then return default end
  return v
end

local function playUi(file, vol)
  if not Spring.PlaySoundFile then return end
  local ok = Spring.PlaySoundFile(tostring(file), vol or 1.0, "ui")
  if not ok then
    Spring.PlaySoundFile("sounds/ui/" .. tostring(file) .. ".wav", vol or 1.0, "ui")
  end
end

local function unitLabel(unitID)
  local hero = Spring.GetUnitRulesParam(unitID, "va_hero_name")
  if type(hero) == "string" and hero ~= "" then return hero end
  local dID = Spring.GetUnitDefID(unitID)
  local ud = dID and UnitDefs[dID]
  if ud then
    local hn = ud.humanName or ud.translatedHumanName or ud.name
    if hn and hn ~= "" then return tostring(hn) end
  end
  return "Unit " .. tostring(unitID)
end

local function buildChip(unitID)
  if not Spring.ValidUnitID(unitID) or Spring.GetUnitIsDead(unitID) then return nil end
  local parts = {}
  local heroName = Spring.GetUnitRulesParam(unitID, "va_hero_name")
  local heroLvl = tonumber(Spring.GetUnitRulesParam(unitID, "va_hero_level") or 0) or 0
  local heroHp = tonumber(Spring.GetUnitRulesParam(unitID, "va_hero_hp_mult") or 0)
    or tonumber(Spring.GetUnitRulesParam(unitID, "va_hero_toughness") or 0)
  if type(heroName) == "string" and heroName ~= "" then
    local h = "Hero " .. heroName
    if heroLvl > 0 then h = h .. " L" .. tostring(math.floor(heroLvl)) end
    if heroHp and heroHp > 1.01 then h = h .. string.format(" · tough ×%.2f", heroHp) end
    parts[#parts + 1] = h
  end

  local vetRank = Spring.GetUnitRulesParam(unitID, "va_vet_rank")
  local vetHp = tonumber(Spring.GetUnitRulesParam(unitID, "va_vet_hp_mult") or 1) or 1
  local vetSpd = tonumber(Spring.GetUnitRulesParam(unitID, "va_vet_speed_mult") or 1) or 1
  local vetRng = tonumber(Spring.GetUnitRulesParam(unitID, "va_vet_range_mult") or 1) or 1
  local vetReload = tonumber(Spring.GetUnitRulesParam(unitID, "va_vet_reload_mult") or 1) or 1
  if type(vetRank) == "string" and vetRank ~= "" and vetRank ~= "green" then
    local rof = 1 / math.max(0.01, vetReload)
    parts[#parts + 1] = string.format(
      "Vet %s · HP×%.2f spd×%.2f rng×%.2f RoF×%.2f",
      vetRank, vetHp, vetSpd, vetRng, rof)
  elseif vetHp > 1.02 or vetSpd > 1.02 or vetRng > 1.02 or vetReload < 0.98 then
    parts[#parts + 1] = string.format("Vet growing · HP×%.2f spd×%.2f", vetHp, vetSpd)
  end

  local craftXp = tonumber(Spring.GetUnitRulesParam(unitID, "va_craft_xp") or 0) or 0
  local craftBp = tonumber(Spring.GetUnitRulesParam(unitID, "va_craft_bp_mult") or 1) or 1
  if craftXp > 0.02 or craftBp > 1.02 then
    parts[#parts + 1] = string.format("Craft φ=%.2f · BP×%.2f", craftXp, craftBp)
  end

  local fieldStat = Spring.GetUnitRulesParam(unitID, "va_field_stat")
  local fieldMult = tonumber(Spring.GetUnitRulesParam(unitID, "va_field_mult") or 1) or 1
  local fieldSpd = tonumber(Spring.GetUnitRulesParam(unitID, "va_field_speed_mult") or 1) or 1
  local fieldE = tonumber(Spring.GetUnitRulesParam(unitID, "va_field_energy_mult") or 1) or 1
  local tagLabels = Spring.GetUnitRulesParam(unitID, "va_hero_tag_labels")
  if type(fieldStat) == "string" and fieldStat ~= "" and fieldMult > 1.01 then
    local line = string.format("Field %s ×%.2f", fieldStat, fieldMult)
    if fieldSpd > 1.01 and fieldStat ~= "speed" then
      line = line .. string.format(" · spd ×%.2f", fieldSpd)
    end
    if fieldE > 1.01 and fieldStat ~= "energy" then
      line = line .. string.format(" · e ×%.2f", fieldE)
    end
    parts[#parts + 1] = line
  elseif type(tagLabels) == "string" and tagLabels ~= "" then
    parts[#parts + 1] = "Field · " .. tagLabels
  end

  if #parts == 0 then
    -- Still show a thin identity line so selection always answers something.
    parts[1] = unitLabel(unitID) .. " · green"
  end

  return {
    unitID = unitID,
    title = unitLabel(unitID),
    lines = parts,
  }
end

local function refreshSelected()
  selectedChip = nil
  local sel = Spring.GetSelectedUnits() or {}
  if #sel == 1 then
    selectedChip = buildChip(sel[1])
  elseif #sel > 1 then
    -- Multi-select: summarize highest vet rank present.
    local bestRank, bestUid = nil, nil
    local order = { cracked = 4, hardened = 3, blooded = 2, green = 1 }
    for i = 1, #sel do
      local uid = sel[i]
      local r = Spring.GetUnitRulesParam(uid, "va_vet_rank") or "green"
      local score = order[tostring(r)] or 0
      if not bestRank or score > (order[bestRank] or 0) then
        bestRank, bestUid = tostring(r), uid
      end
    end
    if bestUid then
      selectedChip = {
        unitID = bestUid,
        title = string.format("%d selected", #sel),
        lines = { "Best vet: " .. tostring(bestRank or "green") },
      }
    end
  end
end

local function groundY(x, z)
  if Spring.GetGroundHeight then
    return (Spring.GetGroundHeight(x, z) or 0) + 8
  end
  return 8
end

local function drawCorridorLine(x1, z1, x2, z2, r, g, b, a, width)
  if not x1 or not z1 or not x2 or not z2 then return end
  if x1 < 0 or z1 < 0 or x2 < 0 or z2 < 0 then return end
  local y1, y2 = groundY(x1, z1), groundY(x2, z2)
  gl.LineWidth(width or 2.5)
  gl.Color(r, g, b, a or 0.55)
  gl.BeginEnd(GL.LINES, function()
    gl.Vertex(x1, y1, z1)
    gl.Vertex(x2, y2, z2)
  end)
  -- Soft dashed mid markers so the path reads as a corridor, not a laser.
  local mx, mz = (x1 + x2) * 0.5, (z1 + z2) * 0.5
  local my = groundY(mx, mz)
  gl.PointSize(6)
  gl.BeginEnd(GL.POINTS, function()
    gl.Vertex(mx, my, mz)
  end)
  gl.PointSize(1)
  gl.LineWidth(1)
  gl.Color(1, 1, 1, 1)
end

function widget:DrawWorld()
  if Spring.IsGUIHidden and Spring.IsGUIHidden() then return end
  -- Deploy↔extract corridor + extract markers live in objectives (WG.vaRoute).
  -- Playfeel only draws hurt-retreat rays to the unit's chosen safe point.
  local dx = numParam("va_deploy_x", -1)
  local dz = numParam("va_deploy_z", -1)
  local ex = numParam("va_extract_x", -1)
  local ez = numParam("va_extract_z", -1)

  local myTeam = Spring.GetMyTeamID and Spring.GetMyTeamID()
  if myTeam ~= nil then
    local units = Spring.GetTeamUnits(myTeam) or {}
    for i = 1, #units do
      local uid = units[i]
      if Spring.ValidUnitID(uid) and not Spring.GetUnitIsDead(uid) then
        local beh = Spring.GetUnitRulesParam(uid, "va_behavior")
        if beh == "hurt_retreat" or beh == "skittish" then
          local ux, _, uz = Spring.GetUnitPosition(uid)
          local rx = tonumber(Spring.GetUnitRulesParam(uid, "va_retreat_x") or -1)
          local rz = tonumber(Spring.GetUnitRulesParam(uid, "va_retreat_z") or -1)
          local safeX, safeZ = rx, rz
          if not (safeX and safeX > 0) then
            safeX, safeZ = dx, dz
          end
          if not (safeX and safeX > 0) then
            safeX, safeZ = ex, ez
          end
          if ux and safeX and safeX > 0 and safeZ and safeZ > 0 then
            drawCorridorLine(ux, uz, safeX, safeZ,
              COL_BAD[1], COL_BAD[2], COL_BAD[3], 0.7, 2.0)
          end
        end
      end
    end
  end
end

function widget:Initialize()
  widgetHandler:RegisterGlobal(widget, "VerdanceVetRank", function(unitID, prev, rank, x, y, z, mults)
    widget:VerdanceVetRank(unitID, prev, rank, x, y, z, mults)
  end)
  refreshSelected()
  Spring.Echo("VA_PLAYFEEL_ARMED chip+rank+bringhome+wreckflash+retreat")
end

function widget:Shutdown()
  widgetHandler:DeregisterGlobal(widget, "VerdanceVetRank")
end

function widget:ViewResize(x, y)
  vsx, vsy = x, y
end

function widget:SelectionChanged()
  refreshSelected()
end

function widget:VerdanceVetRank(unitID, prev, rank, x, y, z, mults)
  local name = unitLabel(unitID)
  flashLabel = string.format("%s · %s", name, tostring(rank):upper())
  flashUntil = os.clock() + 2.4
  if rank == "cracked" then
    flashColor = COL_GOLD
  elseif rank == "hardened" then
    flashColor = COL_STEAM
  else
    flashColor = COL_GOOD
  end
  playUi("beep6", 0.85)
  if Spring.MarkerAddPoint and x and z then
    pcall(Spring.MarkerAddPoint, x, y or 0, z, tostring(rank):upper() .. ": " .. name, true)
  end
  Spring.Echo(string.format("VA_PLAYFEEL_RANK %s %s→%s mults=%s", name, tostring(prev), tostring(rank), tostring(mults)))
  refreshSelected()
end

local function drawChip()
  if not selectedChip or Spring.IsGUIHidden() then return end
  local w = 320
  local lineH = 14
  local h = 28 + (#selectedChip.lines * lineH)
  local x = 18
  local y = 110
  gl.Color(0.05, 0.08, 0.07, 0.72)
  gl.Rect(x, y, x + w, y + h)
  gl.Color(COL_GOLD[1], COL_GOLD[2], COL_GOLD[3], 0.85)
  gl.Rect(x, y, x + 3, y + h)
  gl.Color(COL_INK[1], COL_INK[2], COL_INK[3], 1)
  gl.Text(tostring(selectedChip.title):sub(1, 34), x + 10, y + h - 16, 12, "o")
  local yy = y + h - 32
  for i = 1, #selectedChip.lines do
    gl.Color(COL_DIM[1], COL_DIM[2], COL_DIM[3], 1)
    gl.Text(tostring(selectedChip.lines[i]):sub(1, 42), x + 10, yy, 11, "o")
    yy = yy - lineH
  end
  gl.Color(1, 1, 1, 1)
end

local function drawFlash()
  if os.clock() > flashUntil or flashLabel == "" then return end
  local a = math.max(0, math.min(1, (flashUntil - os.clock()) / 0.6))
  if a < 0.15 then a = (flashUntil - os.clock()) / 2.4 end
  a = math.max(0.25, math.min(1, a))
  local cx = vsx * 0.5
  local cy = vsy * 0.72
  gl.Color(flashColor[1], flashColor[2], flashColor[3], a)
  gl.Text(flashLabel, cx, cy, 22, "co")
  gl.Color(COL_DIM[1], COL_DIM[2], COL_DIM[3], a * 0.9)
  gl.Text("VETERANCY", cx, cy + 22, 11, "co")
  gl.Color(1, 1, 1, 1)
end

local lastRescueFailFlash = false
local function maybeBringHome(frame)
  local allDone = numParam("va_all_objectives_done", 0) == 1
  local primary = numParam("va_objective_complete", 0) == 1
  local rescueFailed = numParam("va_objective_failed", 0) == 1
  local extractOpen = numParam("va_extract_open", 0) == 1
  local terminal = numParam("va_status", "") 
  if type(terminal) ~= "string" then terminal = tostring(Spring.GetGameRulesParam("va_status") or "") end
  if terminal == "victory" or terminal == "defeat" or terminal == "partial" then return end

  -- Soft-continue clears the gadget latch; re-arm flash for a later fail.
  if not rescueFailed then
    lastRescueFailFlash = false
  elseif not lastRescueFailFlash then
    lastRescueFailFlash = true
    playUi("warning1", 1.0)
    flashLabel = "RESCUE FAILED — EXTRACT"
    flashUntil = os.clock() + 3.2
    flashColor = COL_BAD or COL_GOLD
  end

  if not allDone then
    lastAllDone = false
  elseif not lastAllDone then
    lastAllDone = true
    -- Flash only — objectives owns extract MarkerAddPoint + EXTRACT OPEN bark.
    playUi("beep6", 1.0)
    flashLabel = "BRING THEM HOME"
    flashUntil = os.clock() + 3.0
    flashColor = COL_STEAM
  end

  if (allDone or (rescueFailed and extractOpen)) and frame - lastBringHome > 45 * 30 then
    lastBringHome = frame
    flashLabel = rescueFailed and "RTB — extract (rescue failed)" or "Extract open — rally the pad"
    flashUntil = os.clock() + 2.2
    flashColor = COL_STEAM
    playUi("beep4", 0.55)
  elseif primary and not allDone and not rescueFailed and frame - lastBringHome > 70 * 30 then
    lastBringHome = frame
    flashLabel = "Primary done — finish required marks"
    flashUntil = os.clock() + 2.0
    flashColor = COL_GOLD
  end
end

local function maybeWreckPing(frame)
  if frame - lastWreckPing < 25 * 30 then return end
  local myTeam = Spring.GetMyTeamID()
  local units = Spring.GetTeamUnits(myTeam) or {}
  local hasCon = false
  for i = 1, #units do
    local uid = units[i]
    local dID = Spring.GetUnitDefID(uid)
    local ud = dID and UnitDefs[dID]
    if ud and (ud.canResurrect or ud.isBuilder) then
      hasCon = true
      break
    end
  end
  if not hasCon then return end

  local feats = Spring.GetAllFeatures and Spring.GetAllFeatures() or {}
  for i = 1, #feats do
    local fid = feats[i]
    local heroName = Spring.GetFeatureRulesParam and Spring.GetFeatureRulesParam(fid, "va_hero_wreck_name")
    if type(heroName) == "string" and heroName ~= "" then
      local fx, fy, fz = Spring.GetFeaturePosition(fid)
      if fx and Spring.IsUnitInView == nil then
        -- always ping heroes
      end
      lastWreckPing = frame
      -- Flash/SFX only — objectives owns RECOVER map markers from va_sec*.
      flashLabel = "REZ OPPORTUNITY · " .. tostring(heroName)
      flashUntil = os.clock() + 2.5
      flashColor = COL_BAD
      playUi("warning2", 0.45)
      return
    end
  end
end

function widget:GameFrame(frame)
  if frame % 15 == 0 then
    refreshSelected()
  end
  if frame % 30 == 0 then
    maybeBringHome(frame)
  end
  if frame % 45 == 0 then
    maybeWreckPing(frame)
  end
end

function widget:DrawScreen()
  if Spring.IsGUIHidden() then return end
  drawChip()
  drawFlash()
end
