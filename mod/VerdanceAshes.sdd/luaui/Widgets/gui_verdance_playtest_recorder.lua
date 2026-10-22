if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
function widget:GetInfo()
  return {
    name    = "Verdance Playtest Recorder",
    desc    = "Records a tracked campaign session to disk from inside the client: "
           .. "zone occupancy over time, border crossings, your orders, the outcome.",
    author  = "Verdance",
    date    = "2026",
    license = "GNU GPL, v2 or later",
    layer   = 0,
    -- Auto-loads, then removes itself immediately unless the session was launched
    -- with tracking armed. Costs nothing in an ordinary match.
    enabled = true,
  }
end

--------------------------------------------------------------------------------
-- Why this widget exists
--
-- The synced gadget already computes everything a tracked session needs and
-- writes it to the infolog. Reading it back out meant a PowerShell harvester
-- parsing infolog.txt after the process exited, which put the campaign loop
-- outside the game. LuaUI can write files (BAR's own gui_restart_with_state.lua
-- does exactly this), so the session can record itself and the client becomes
-- self-contained.
--
-- Packets arrive as raw JSON strings from the gadget over the VERDANCE_TRACK sync
-- action. They are stored verbatim and concatenated at commit time: the gadget is
-- the only JSON author, so the widget never needs a serializer and cannot
-- disagree with it about a shape.
--------------------------------------------------------------------------------

local SESSION_DIR = "LuaUI/Config/verdance"
local COMMIT_EVERY = 4          -- snapshots between incremental writes
local MAX_SNAPSHOTS = 2000      -- ~16h at one per 5s; a bound, not a target

local armed = false
local sessionPath = nil
local committed = false

local snapshots = {}            -- raw telemetry JSON strings
local devSamples = {}           -- raw dev-sample JSON strings
local zoneFlow = nil            -- raw, last wins (it is cumulative)
local resultJson = nil
local sinceCommit = 0
local dropped = 0

-- Display-only, scraped from the packets with patterns rather than parsed.
local hud = {
  frame = 0,
  zonesHeld = 0,
  orders = 0,
  ratio = nil,
  verdict = nil,
  topZone = nil,
  topZoneValue = 0,
  crossings = 0,
}

local function jsonString(key, s)
  -- Only ever called on values this widget itself produced (ids, paths, stamps).
  local escaped = tostring(s or ""):gsub('\\', '\\\\'):gsub('"', '\\"')
  return '"' .. key .. '":"' .. escaped .. '"'
end

local function sessionStamp()
  -- Spring.GetGameRulesParam is not reliable this early; the engine's own game id
  -- is stable across the match and unique per match, which is exactly the key a
  -- session file wants.
  local gid = nil
  if Spring.GetGameRulesParam then gid = Spring.GetGameRulesParam("va_mission_id") end
  local t = os.date("%Y%m%d_%H%M%S")
  if gid and gid ~= "" then return t .. "_" .. tostring(gid) end
  return t
end

local function commit(reason)
  if not armed then return end
  if #snapshots == 0 and not zoneFlow and not resultJson then return end

  Spring.CreateDir(SESSION_DIR)
  local f, err = io.open(sessionPath, "w")
  if not f then
    Spring.Echo("[Verdance Recorder] Could not write " .. tostring(sessionPath)
      .. ": " .. tostring(err))
    return
  end

  local parts = {}
  parts[#parts + 1] = '{'
  parts[#parts + 1] = jsonString("schemaVersion", "verdance-client-session/1.0")
  parts[#parts + 1] = ',' .. jsonString("sourceKind", "human_session")
  parts[#parts + 1] = ',' .. jsonString("recordedBy", "gui_verdance_playtest_recorder")
  parts[#parts + 1] = ',' .. jsonString("committedAt", os.date("!%Y-%m-%dT%H:%M:%SZ"))
  parts[#parts + 1] = ',' .. jsonString("commitReason", reason or "periodic")
  parts[#parts + 1] = ',' .. jsonString("mapName", Game.mapName or "")
  parts[#parts + 1] = ',"playerTeamID":' .. tostring(Spring.GetMyTeamID() or 0)
  parts[#parts + 1] = ',"lastFrame":' .. tostring(hud.frame or 0)
  parts[#parts + 1] = ',"droppedPackets":' .. tostring(dropped)
  parts[#parts + 1] = ',"snapshots":[' .. table.concat(snapshots, ',') .. ']'
  parts[#parts + 1] = ',"devSamples":[' .. table.concat(devSamples, ',') .. ']'
  parts[#parts + 1] = ',"zoneFlow":' .. (zoneFlow or 'null')
  parts[#parts + 1] = ',"result":' .. (resultJson or 'null')
  parts[#parts + 1] = '}'

  f:write(table.concat(parts))
  f:close()
  committed = true
  sinceCommit = 0
  Spring.Echo("[Verdance Recorder] " .. reason .. ": " .. tostring(#snapshots)
    .. " snapshot(s) -> " .. tostring(sessionPath))
end

--------------------------------------------------------------------------------

function widget:Initialize()
  local mo = (Spring.GetModOptions and Spring.GetModOptions()) or {}
  local v = mo.va_play_track
  armed = (v == true or v == 1 or v == "1" or v == "true")
  if not armed then
    -- Not a tracked session. Nothing to record, so do not sit in the draw loop.
    widgetHandler:RemoveWidget(self)
    return
  end
  sessionPath = SESSION_DIR .. "/session_" .. sessionStamp() .. ".json"
  Spring.Echo("[Verdance Recorder] Armed. Recording to " .. sessionPath)
end

-- Called by the gadget's unsynced half via Script.LuaUI.VerdanceTrack.
function widget:VerdanceTrack(kind, jsonStr)
  if not armed or type(jsonStr) ~= "string" or jsonStr == "" then return end

  if kind == "telemetry" then
    if #snapshots >= MAX_SNAPSHOTS then
      dropped = dropped + 1
      return
    end
    snapshots[#snapshots + 1] = jsonStr
    sinceCommit = sinceCommit + 1

    local frame = jsonStr:match('"frame":(%d+)')
    if frame then hud.frame = tonumber(frame) or hud.frame end
    local ratio = jsonStr:match('"valueRatio":([%d%.%-eE]+)')
    if ratio then hud.ratio = tonumber(ratio) end
    -- Zones the local player holds any value in.
    local held = 0
    for _ in jsonStr:gmatch('"zoneId":"') do held = held + 1 end
    hud.zonesHeld = held

    if sinceCommit >= COMMIT_EVERY then commit("periodic") end

  elseif kind == "zoneflow" then
    zoneFlow = jsonStr
    local total = 0
    for n in jsonStr:gmatch('"crossings":(%d+)') do total = total + (tonumber(n) or 0) end
    -- Every edge contributes a total plus one per team, so this double counts by
    -- construction. Halved for display only; the file keeps the exact packet.
    hud.crossings = math.floor(total / 2)

  elseif kind == "devsample" then
    if #devSamples < MAX_SNAPSHOTS then
      devSamples[#devSamples + 1] = jsonStr
    else
      dropped = dropped + 1
    end
    local n = jsonStr:match('"playerCommandTotal":(%d+)')
    if n then hud.orders = hud.orders + (tonumber(n) or 0) end

  elseif kind == "result" then
    resultJson = jsonStr
    hud.verdict = jsonStr:match('"status":"(%a+)"')
    -- The outcome is the one packet that must never be lost to a crash on the way
    -- out, so commit on arrival rather than waiting for Shutdown.
    commit("terminal")
  end
end

function widget:GameOver()
  commit("gameover")
end

function widget:Shutdown()
  -- Catches the alt-F4 / quit-to-menu path, where no terminal ever fires. The
  -- movement record is still valid; only the outcome is missing.
  commit("shutdown")
end

--------------------------------------------------------------------------------
-- A small readout, so "is this actually recording?" is answerable at a glance
-- rather than by going and looking for a file afterwards.
--------------------------------------------------------------------------------

local function fmtClock(frame)
  local secs = math.floor((frame or 0) / 30)
  return string.format("%d:%02d", math.floor(secs / 60), secs % 60)
end

function widget:DrawScreen()
  if not armed then return end
  local vsx, vsy = Spring.GetViewGeometry()
  local x = 12
  local y = vsy - 120
  local line = 14

  gl.PushMatrix()
  gl.Color(0, 0, 0, 0.55)
  gl.Rect(x - 6, y - (line * 4) - 6, x + 214, y + 16)
  gl.Color(1, 1, 1, 1)

  gl.Text("\255\140\200\140REC\255\255\255\255  Verdance playtest", x, y, 12, "o")
  y = y - line
  gl.Text(string.format("\255\190\190\190t %s   zones %d   orders %d",
    fmtClock(hud.frame), hud.zonesHeld, hud.orders), x, y, 11, "o")
  y = y - line
  local ratioText = hud.ratio and string.format("%.2f", hud.ratio) or "-"
  gl.Text(string.format("\255\190\190\190crossings %d   ratio %s",
    hud.crossings, ratioText), x, y, 11, "o")
  y = y - line
  if hud.verdict then
    gl.Text("\255\255\210\120" .. tostring(hud.verdict):upper() .. " - session filed", x, y, 11, "o")
  else
    gl.Text(string.format("\255\140\140\140%d snapshot(s) written", #snapshots), x, y, 11, "o")
  end
  gl.PopMatrix()
  gl.Color(1, 1, 1, 1)
end
