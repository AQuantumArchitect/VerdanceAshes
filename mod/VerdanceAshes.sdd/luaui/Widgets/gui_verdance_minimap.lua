if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Minimap Board",
    desc = "The minimap is the company's belief board: faction colour = who we believe holds it, alpha = confidence, line of sight replaces belief, bad hatch = how much of us they see, one pad, marks, people. Yeva says when the ground disagrees.",
    author = "Verdance",
    date = "2026-10-20",
    license = "GPL v2 or later",
    layer = 9,
    enabled = true,
  }
end

-- Pass seven. Replaces gui_verdance_zone_minimap.lua + gui_verdance_belief_overlay.lua.
-- Owns the one Board instance (WG.vaBoard) that the sidebar, infil and exfil screens share,
-- and the live contradiction record (WG.vaContradicted). Draws the pad ring on the ground.

local Board, Ash
do
  local ok, mod = pcall(VFS.Include, "luaui/Include/va_board.lua")
  if not ok or type(mod) ~= "table" then ok, mod = pcall(VFS.Include, "LuaUI/Include/va_board.lua") end
  Board = (ok and type(mod) == "table") and mod or nil
  ok, mod = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(mod) ~= "table" then ok, mod = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua") end
  Ash = (ok and type(mod) == "table") and mod or nil
end

local board = nil
local enabled = true
local lastTick = -1
local lastRoleKey = ""
local checked = {}       -- zoneId -> true once judged
local contradicted = {}  -- zoneId -> "held" | "empty"

-- Yeva, quartermaster of bad news. Plain speech; the numbers stay on the board.
local LINES = {
  ours_found_enemy = { "%s was supposed to be ours. It is not.", "We briefed %s as held. Somebody else is holding it." },
  dark_found_enemy = { "Nobody had looked at %s. There is a column in it.", "%s was a blank on the map. It is not blank." },
  theirs_found_empty = { "%s was briefed as theirs. There is nobody there.", "We came expecting a fight at %s. The ground is empty." },
}

local function say(kind, id)
  local pool = LINES[kind]
  if not pool or not board then return end
  local n = 0
  for c in tostring(id):gmatch(".") do n = n + c:byte() end
  local line = string.format(pool[(n % #pool) + 1], board:label(id))
  if WG and WG.vaVoice and WG.vaVoice.say then WG.vaVoice.say("Yeva", line, 12) end
  Spring.Echo("VA_SURPRISE_LIVE zone=" .. tostring(id) .. " kind=" .. kind)
end

-- Once a zone is well seen, judge the brief once. The verdict glyph never fades.
local function checkSurprises()
  for _, z in ipairs(board.zones) do
    local id = z.id
    if not checked[id] then
      local eta = board:eta(id)
      if eta >= 0.5 then
        local state, conf = board:believed(id)
        local enemies = board:enemySeen(id)
        if state == "ours" and conf >= 0.3 and enemies >= 3 then
          checked[id] = true; contradicted[id] = "held"; say("ours_found_enemy", id)
        elseif state == "dark" and enemies >= 5 then
          checked[id] = true; contradicted[id] = "held"; say("dark_found_enemy", id)
        elseif state == "held" and conf >= 0.4 and eta >= 0.75 and enemies == 0 then
          checked[id] = true; contradicted[id] = "empty"; say("theirs_found_empty", id)
        elseif eta >= 0.9 then
          checked[id] = true
        end
      end
    end
  end
  if WG then WG.vaContradicted = contradicted end
end

-- The live report: what this board shows, written beside BAR every observation tick so the
-- hub can paint it on a second screen. Company view only (our sight, our people, the pad);
-- the hub keeps it apart from belief, which still moves only at homecoming.
local LIVE_PATH = "LuaUI/Config/verdance/live.json"
local function q(v) return '"' .. tostring(v):gsub('[%c"\\]', function(c) return string.format("\\u%04x", c:byte()) end) .. '"' end
local function n(v)
  v = tonumber(v) or 0
  if v == math.floor(v) and math.abs(v) < 1e9 then return string.format("%d", v) end
  return string.format("%.3f", v)
end
local function writeLive()
  if not (io and io.open) then return end
  local m = board.mission or {}
  local zs = {}
  for _, z in ipairs(board.zones) do
    local eta, enemy, seen = board:eta(z.id), board:enemySeen(z.id), board:exposure(z.id)
    if eta > 0.01 or enemy > 0 or seen > 0.01 or contradicted[z.id] then
      zs[#zs + 1] = q(z.id) .. ':{"eta":' .. n(eta) .. ',"enemy":' .. n(enemy) .. ',"exposure":' .. n(seen)
        .. (contradicted[z.id] and (',"found":' .. q(contradicted[z.id])) or "") .. "}"
    end
  end
  local function rule(name) return tonumber((Spring.GetGameRulesParam(name))) or 0 end
  local heroes = Spring.GetGameRulesParam("va_hud_heroes_json")
  if type(heroes) ~= "string" or heroes:sub(1, 1) ~= "[" then heroes = "[]" end
  local body = '{"schema":"verdance-live/1","missionId":' .. q(m.missionId or "") .. ',"mapId":' .. q(m.deploymentMapId or "")
    .. ',"frame":' .. n(Spring.GetGameFrame()) .. ',"mapX":' .. n(board.mapX) .. ',"mapZ":' .. n(board.mapZ)
    .. ',"padZoneId":' .. q(board.padId or "") .. ',"status":' .. q(Spring.GetGameRulesParam("va_status") or "")
    .. ',"pad":{"people":' .. n(rule("va_pad_people")) .. ',"units":' .. n(rule("va_pad_units")) .. ',"enemy":' .. n(rule("va_pad_enemy_live")) .. "}"
    .. ',"objective":{"done":' .. n(rule("va_objective_destroyed")) .. ',"total":' .. n(rule("va_objective_total")) .. "}"
    .. ',"zones":{' .. table.concat(zs, ",") .. '},"heroes":' .. heroes .. "}"
  local path = (WG and WG.vaLivePath) or LIVE_PATH
  if Spring.CreateDir then pcall(Spring.CreateDir, path:match("^(.*)/") or ".") end
  local fh = io.open(path, "w") -- one small write; the hub retries a torn read
  if not fh then return end
  fh:write(body); fh:close()
end

function widget:Initialize()
  if not Board then
    Spring.Echo("VA_MINIMAP no va_board.lua include; widget idle")
    return
  end
  board = Board.new()
  lastRoleKey = board.roleKey
  if WG then
    WG.vaBoard = board
    WG.vaContradicted = contradicted
  end
end

function widget:Shutdown()
  if WG then
    if WG.vaBoard == board then WG.vaBoard = nil end
    WG.vaContradicted = nil
  end
end

function widget:Update()
  if not board then return end
  local key = board:roleKeyNow()
  if key ~= lastRoleKey then
    lastRoleKey = key
    board:refreshRoles()
  end
  local tick = tonumber((Spring.GetGameRulesParam("va_obs_tick"))) or -1
  if tick ~= lastTick then
    lastTick = tick
    checkSurprises()
    writeLive()
  end
end

function widget:TextCommand(cmd)
  if cmd == "vaboard" then
    enabled = not enabled
    Spring.Echo("VA_MINIMAP board " .. (enabled and "on" or "off"))
    return true
  end
  if cmd == "vaboardreload" and board then
    board:reload()
    Spring.Echo("VA_MINIMAP reloaded zones=" .. #board.zones)
    return true
  end
  return false
end

-- People for the board: heroes off the pad (○) and down (✚), from the sidebar's parsed roster.
local function peopleGlyphs()
  local out = {}
  local heroes = WG and WG.vaHeroes
  if type(heroes) ~= "table" then return out end
  for _, h in ipairs(heroes) do
    if h.x and h.z then
      if h.state == "down" then
        out[#out + 1] = { x = h.x, z = h.z, glyph = Ash.GLYPH.down, col = Ash.COL.bad, size = 12 }
      elseif h.state == "alive" and not h.onPad then
        out[#out + 1] = { x = h.x, z = h.z, glyph = Ash.GLYPH.offPad, col = h.critical and Ash.COL.gold or Ash.COL.ink, size = 10 }
      end
    end
  end
  return out
end

function widget:DrawInMiniMap(sx, sy)
  if not enabled or not board or #board.zones == 0 then return end
  local proj = board:minimapProj(sx, sy)
  board:paint(proj, { fade = true, contradicted = contradicted, people = peopleGlyphs(), roleOnly = true, glyphSize = 11, unknownAlpha = 0.35 })
  -- the live route stage, thin, in the stage colour (the painted battlefield line is the real one)
  local route = WG and WG.vaRoute
  if route and route.from and route.to then
    local ax, ay = proj(route.from.x, route.from.z)
    local bx, by = proj(route.to.x, route.to.z)
    local col = (route.stage == "extract" and Ash.COL.steam) or (route.stage == "marks" and Ash.COL.gold) or Ash.COL.warn
    Ash.setColor(Ash.with(col, 0.8))
    gl.LineWidth(1.6)
    gl.BeginEnd(GL.LINES, function() gl.Vertex(ax, ay); gl.Vertex(bx, by) end)
    gl.LineWidth(1)
  end
  gl.Color(1, 1, 1, 1)
end

-- The pad ring on the ground: steam LINE_LOOP, pulsing; inner dashed ring turns warn while
-- enemies stand inside (va_pad_enemy_live from the exfil gadget). No other reticles.
local function groundY(x, z) return (Spring.GetGroundHeight(x, z) or 0) end

function widget:DrawWorld()
  if not board or Spring.IsGUIHidden() then return end
  if (tonumber((Spring.GetGameRulesParam("va_terminal"))) or 0) == 1 then return end
  local px, pz, pr = board:pad()
  if not px then return end
  local steam = Ash.COL.steam
  local segs = 48
  local twoPi = math.pi * 2
  local pulse = 0.35 + 0.35 * math.abs(math.sin(os.clock() * 1.6))
  gl.Color(steam[1], steam[2], steam[3], pulse)
  gl.LineWidth(3)
  gl.BeginEnd(GL.LINE_LOOP, function()
    for i = 0, segs - 1 do
      local a = (i / segs) * twoPi
      local x, z = px + math.cos(a) * pr, pz + math.sin(a) * pr
      gl.Vertex(x, groundY(x, z) + 10, z)
    end
  end)
  local hostile = (tonumber((Spring.GetGameRulesParam("va_pad_enemy_live"))) or 0) > 0
  local inner = math.max(60, pr - 40)
  local ic = hostile and Ash.COL.warn or steam
  local ia = hostile and (0.55 + 0.4 * math.abs(math.sin(os.clock() * 4))) or 0.3
  gl.Color(ic[1], ic[2], ic[3], ia)
  gl.LineWidth(2)
  gl.BeginEnd(GL.LINES, function()
    for i = 0, segs - 1, 2 do
      local a1 = (i / segs) * twoPi
      local a2 = ((i + 1) / segs) * twoPi
      local x1, z1 = px + math.cos(a1) * inner, pz + math.sin(a1) * inner
      local x2, z2 = px + math.cos(a2) * inner, pz + math.sin(a2) * inner
      gl.Vertex(x1, groundY(x1, z1) + 10, z1)
      gl.Vertex(x2, groundY(x2, z2) + 10, z2)
    end
  end)
  gl.LineWidth(1)
  gl.Color(1, 1, 1, 1)
end
