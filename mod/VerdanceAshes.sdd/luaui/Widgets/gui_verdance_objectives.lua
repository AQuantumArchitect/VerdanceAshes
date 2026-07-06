local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Objectives HUD",
    desc = "Mission briefing, objective flow, and campaign debrief for Verdance's Ashes",
    author = "Claude / Luke Spooner",
    date = "2026-07-06",
    license = "GPL v2 or later",
    layer = 5,
    enabled = true,
  }
end

local mission
local briefingLines = {}
local debriefCandidates = {}
local missionTitle = "Verdance's Ashes"
local storyReason = nil
local difficultyLabel = nil
local lastPoll = 0
local briefingDismissed = false
local vsx, vsy = Spring.GetViewGeometry()

local BRIEFING_SECONDS = 45
local EXTRACTION_HOLD_FRAMES = 450
local PRESENCE_HOLD_DEFAULT = 900

local state = {
  status = "inactive",
  objectiveTotal = 0,
  objectiveDestroyed = 0,
  objectiveComplete = false,
  terminal = false,
  resultCode = 0,
  zoneHold = 0,
  extractionHold = 0,
  extractionClean = true,
  terminalReason = "",
}

local COL = {
  panel = { 0.04, 0.09, 0.06, 0.82 },
  edge = { 0.35, 0.85, 0.45, 0.55 },
  title = { 0.92, 0.86, 0.72 },
  text = { 0.92, 0.95, 0.9 },
  ketha = { 0.65, 0.82, 0.65 },
  dim = { 0.7, 0.72, 0.7 },
  good = { 0.4, 1.0, 0.4 },
  bad = { 1.0, 0.35, 0.3 },
  warn = { 1.0, 0.8, 0.3 },
  blue = { 0.7, 0.85, 1.0 },
}

local function readMission()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if ok and type(data) == "table" then return data end
  ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_001.lua")
  if ok and type(data) == "table" then return data end
  return nil
end

function widget:Initialize()
  mission = readMission()
  if mission then
    missionTitle = mission.title or missionTitle
    local intent = mission.storyIntent or {}
    if type(intent.briefing) == "table" and type(intent.briefing.lines) == "table" then
      briefingLines = intent.briefing.lines
    end
    if type(intent.debriefCandidates) == "table" then
      debriefCandidates = intent.debriefCandidates
    end
    storyReason = intent.storyReason
    local diff = mission.difficulty
    if type(diff) == "table" and diff.enemyScale then
      local scale = tonumber(diff.enemyScale) or 1.0
      if scale >= 1.6 then difficultyLabel = "Expected opposition: heavy"
      elseif scale >= 1.2 then difficultyLabel = "Expected opposition: reinforced"
      elseif scale <= 0.85 then difficultyLabel = "Expected opposition: light"
      else difficultyLabel = "Expected opposition: standard" end
      if diff.fortified then difficultyLabel = difficultyLabel .. ", fortified" end
      if (tonumber(diff.hazardLevel) or 0) > 0.3 then difficultyLabel = difficultyLabel .. ", wild pressure rising" end
    end
  end
  pcall(function()
    widgetHandler:RegisterGlobal(widget, "VerdanceMissionEvent", function(eventStatus, reason)
      widget:VerdanceMissionEvent(eventStatus, reason)
    end)
  end)
end

function widget:Shutdown()
  pcall(function() widgetHandler:DeregisterGlobal(widget, "VerdanceMissionEvent") end)
end

function widget:ViewResize(x, y)
  vsx, vsy = x, y
end

local function poll()
  local sp = Spring.GetGameRulesParam
  state.objectiveTotal = tonumber(sp("va_objective_total")) or 0
  state.objectiveDestroyed = tonumber(sp("va_objective_destroyed")) or 0
  state.objectiveComplete = (tonumber(sp("va_objective_complete")) or 0) == 1
  state.terminal = (tonumber(sp("va_terminal")) or 0) == 1
  state.resultCode = tonumber(sp("va_result_code")) or 0
  state.zoneHold = tonumber(sp("va_zone_hold")) or 0
  state.extractionHold = tonumber(sp("va_extraction_hold")) or 0
  state.extractionClean = (tonumber(sp("va_extraction_clean")) or 1) == 1
  local st = sp("va_status")
  if type(st) == "string" and st ~= "" then state.status = st end
  local reason = sp("va_terminal_reason")
  if type(reason) == "string" then state.terminalReason = reason end
end

function widget:GameFrame(frame)
  if frame - lastPoll >= 30 then
    lastPoll = frame
    poll()
  end
end

function widget:KeyPress(key)
  -- space or escape dismisses the briefing card early
  if not briefingDismissed and (key == 32 or key == 27) and not state.terminal then
    local frame = Spring.GetGameFrame() or 0
    if frame < BRIEFING_SECONDS * 30 then
      briefingDismissed = true
      return false
    end
  end
  return false
end

local function text(str, x, y, size, color, align)
  gl.Color(color[1], color[2], color[3], color[4] or 1)
  gl.Text(str, x, y, size, (align or "c") .. "o")
end

local function panel(x1, y1, x2, y2)
  gl.Color(COL.panel[1], COL.panel[2], COL.panel[3], COL.panel[4])
  gl.Rect(x1, y1, x2, y2)
  gl.Color(COL.edge[1], COL.edge[2], COL.edge[3], COL.edge[4])
  gl.Rect(x1, y2 - 2, x2, y2)
  gl.Rect(x1, y1, x2, y1 + 2)
end

local function pickDebriefLine()
  if state.resultCode == 1 then
    if state.extractionClean and debriefCandidates.victoryClean then return debriefCandidates.victoryClean end
    if debriefCandidates.objectiveDestroyed and state.objectiveTotal > 0 then return debriefCandidates.objectiveDestroyed end
    return debriefCandidates.victory
  elseif state.resultCode == 2 then
    if state.terminalReason == "commander_lost" and debriefCandidates.defeatCommander then return debriefCandidates.defeatCommander end
    return debriefCandidates.defeat
  end
  return debriefCandidates.partial
end

local function drawBriefingCard()
  local w = math.min(640, vsx * 0.6)
  local cx = vsx * 0.5
  local lineCount = #briefingLines
  local h = 120 + lineCount * 22 + (storyReason and 36 or 0) + (difficultyLabel and 20 or 0)
  local top = vsy * 0.78
  local bottom = top - h
  panel(cx - w / 2, bottom, cx + w / 2, top)

  local y = top - 30
  text(missionTitle, cx, y, 20, COL.title); y = y - 26
  if mission and mission.objective and mission.objective.description then
    text("Objective: " .. mission.objective.description, cx, y, 13, COL.text); y = y - 22
  end
  if difficultyLabel then
    text(difficultyLabel, cx, y, 11, COL.dim); y = y - 20
  end
  y = y - 6
  for _, line in ipairs(briefingLines) do
    text('Ketha: "' .. tostring(line.text) .. '"', cx, y, 12, COL.ketha); y = y - 22
  end
  if storyReason then
    y = y - 4
    text(tostring(storyReason), cx, y, 10, COL.dim); y = y - 18
  end
  text("[ Space to dismiss ]", cx, bottom + 12, 10, COL.dim)
end

local function drawObjectiveBar()
  local y = vsy - 40
  local obj = mission and mission.objective or {}
  text(missionTitle, vsx * 0.5, y, 14, COL.title); y = y - 19

  if obj.description then
    local marker = state.objectiveComplete and "[DONE] " or "[  ] "
    local col = state.objectiveComplete and COL.good or COL.text
    text(marker .. obj.description, vsx * 0.5, y, 13, col); y = y - 17
  end

  if state.objectiveTotal > 0 and not state.objectiveComplete then
    text(string.format("Targets destroyed: %d / %d", state.objectiveDestroyed, state.objectiveTotal), vsx * 0.5, y, 12, COL.dim)
    y = y - 15
  end

  if not state.objectiveComplete and state.zoneHold > 0 then
    local required = (obj.requiredHoldFrames) or PRESENCE_HOLD_DEFAULT
    text(string.format("Holding zone: %ds / %ds", math.floor(state.zoneHold / 30), math.floor(required / 30)), vsx * 0.5, y, 12, COL.blue)
    y = y - 15
  end

  if state.objectiveComplete and not state.terminal then
    local held = math.floor(state.extractionHold / 30)
    local need = math.floor(EXTRACTION_HOLD_FRAMES / 30)
    text(string.format("Return to extraction zone: %ds / %ds", held, need), vsx * 0.5, y, 13, COL.warn)
  end
end

local function drawDebriefScreen()
  local w = math.min(680, vsx * 0.62)
  local cx = vsx * 0.5
  local top = vsy * 0.66
  local bottom = top - 190
  panel(cx - w / 2, bottom, cx + w / 2, top)

  local banner, color
  if state.resultCode == 1 or state.status == "victory" then
    banner, color = "VICTORY - SORTIE COMPLETE", COL.good
  elseif state.resultCode == 2 or state.status == "defeat" then
    banner, color = "DEFEAT", COL.bad
  else
    banner, color = "PARTIAL - EXTRACTED", COL.warn
  end

  local y = top - 36
  text(banner, cx, y, 26, color); y = y - 34

  local debrief = pickDebriefLine()
  if debrief then
    text('Ketha: "' .. tostring(debrief) .. '"', cx, y, 13, COL.ketha); y = y - 26
  end

  local bits = {}
  if state.objectiveTotal > 0 then
    bits[#bits + 1] = string.format("targets %d/%d", state.objectiveDestroyed, state.objectiveTotal)
  end
  if state.resultCode == 1 then
    bits[#bits + 1] = state.extractionClean and "clean extraction" or "contested extraction"
  end
  if state.terminalReason ~= "" then
    bits[#bits + 1] = state.terminalReason:gsub("_", " ")
  end
  if #bits > 0 then
    text(table.concat(bits, "  ·  "), cx, y, 11, COL.dim); y = y - 22
  end

  text("Result recorded. Exit the game - the campaign advances itself.", cx, bottom + 18, 12, COL.text)
end

function widget:DrawScreen()
  if Spring.IsGUIHidden() then return end
  if not mission then return end

  if state.terminal then
    drawDebriefScreen()
    drawObjectiveBar()
    return
  end

  local frame = Spring.GetGameFrame() or 0
  if not briefingDismissed and frame < BRIEFING_SECONDS * 30 and not state.objectiveComplete and #briefingLines > 0 then
    drawBriefingCard()
  end
  drawObjectiveBar()
end

function widget:VerdanceMissionEvent(eventStatus, reason)
  poll()
  briefingDismissed = true
  if eventStatus == "objective_complete" then
    Spring.Echo("Verdance: objective complete (" .. tostring(reason) .. ") - return to extraction.")
  end
end
