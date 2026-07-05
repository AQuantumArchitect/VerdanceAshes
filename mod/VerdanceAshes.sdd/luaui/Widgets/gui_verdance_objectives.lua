local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Objectives HUD",
    desc = "Mission objective, extraction and story panel for Verdance's Ashes",
    author = "Claude / Luke Spooner",
    date = "2026-07-05",
    license = "GPL v2 or later",
    layer = 5,
    enabled = true,
  }
end

local mission
local kethaLine = nil
local lastPoll = 0
local vsx, vsy = Spring.GetViewGeometry()

local state = {
  status = "inactive",
  objectiveTotal = 0,
  objectiveDestroyed = 0,
  objectiveComplete = false,
  terminal = false,
  resultCode = 0,
  zoneHold = 0,
  extractionHold = 0,
}

local EXTRACTION_HOLD_FRAMES = 450
local PRESENCE_HOLD_DEFAULT = 900

local function readMission()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if ok and type(data) == "table" then return data end
  ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_001.lua")
  if ok and type(data) == "table" then return data end
  return nil
end

function widget:Initialize()
  mission = readMission()
  if mission and mission.storyIntent and mission.storyIntent.storyReason then
    kethaLine = mission.storyIntent.storyReason
  end
  -- Expose the mission-event receiver so the gadget's SendToUnsynced bridge
  -- (Script.LuaUI.VerdanceMissionEvent) can reach this widget.
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
  local st = sp("va_status")
  if type(st) == "string" and st ~= "" then state.status = st end
end

function widget:GameFrame(frame)
  if frame - lastPoll >= 30 then
    lastPoll = frame
    poll()
  end
end

local function centeredText(text, y, size, color)
  gl.Color(color[1], color[2], color[3], color[4] or 1)
  gl.Text(text, vsx * 0.5, y, size, "co")
end

function widget:DrawScreen()
  if Spring.IsGUIHidden() then return end
  if not mission then return end

  local y = vsy - 40
  local obj = mission.objective or {}

  if state.terminal then
    local banner, color
    if state.resultCode == 1 or state.status == "victory" then
      banner, color = "VICTORY - SORTIE COMPLETE", { 0.4, 1.0, 0.4 }
    elseif state.resultCode == 2 or state.status == "defeat" then
      banner, color = "DEFEAT", { 1.0, 0.35, 0.3 }
    else
      banner, color = "PARTIAL - EXTRACTED", { 1.0, 0.8, 0.3 }
    end
    centeredText(banner, vsy * 0.55, 32, color)
    centeredText("Result recorded. Exit the game to continue the campaign.", vsy * 0.55 - 34, 14, { 0.9, 0.9, 0.9 })
  end

  centeredText(mission.title or "Verdance's Ashes", y, 15, { 0.92, 0.86, 0.72 })
  y = y - 20

  if obj.description then
    local marker = state.objectiveComplete and "[DONE] " or "[  ] "
    local col = state.objectiveComplete and { 0.4, 1.0, 0.4 } or { 1.0, 1.0, 1.0 }
    centeredText(marker .. obj.description, y, 13, col)
    y = y - 17
  end

  if state.objectiveTotal > 0 and not state.objectiveComplete then
    centeredText(string.format("Targets destroyed: %d / %d", state.objectiveDestroyed, state.objectiveTotal), y, 12, { 0.85, 0.85, 0.85 })
    y = y - 15
  end

  if not state.objectiveComplete and state.zoneHold > 0 then
    local required = (obj.requiredHoldFrames) or PRESENCE_HOLD_DEFAULT
    centeredText(string.format("Holding zone: %ds / %ds", math.floor(state.zoneHold / 30), math.floor(required / 30)), y, 12, { 0.7, 0.85, 1.0 })
    y = y - 15
  end

  if state.objectiveComplete and not state.terminal then
    local held = math.floor(state.extractionHold / 30)
    local need = math.floor(EXTRACTION_HOLD_FRAMES / 30)
    centeredText(string.format("Return to extraction zone: %ds / %ds", held, need), y, 13, { 1.0, 0.8, 0.3 })
    y = y - 17
  end

  if kethaLine and not state.terminal then
    centeredText('Ketha: "' .. kethaLine .. '"', y, 11, { 0.65, 0.75, 0.65 })
  end
end

-- Receives mission events forwarded by the unsynced gadget bridge.
function widget:VerdanceMissionEvent(eventStatus, reason)
  poll()
  if eventStatus == "objective_complete" then
    Spring.Echo("Verdance: objective complete (" .. tostring(reason) .. ") - return to extraction.")
  end
end
