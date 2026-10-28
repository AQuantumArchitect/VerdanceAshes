if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
function widget:GetInfo()
  return {
    name    = "Verdance Queen's Nest",
    desc    = "Paints the Queen's Nest in the raptors' colours and calls it out the first time the "
           .. "company sees it, and again when it falls and the queen wakes.",
    author  = "Verdance",
    date    = "2026-10-24",
    license = "GNU GPL, v2 or later",
    layer   = 5,
    enabled = true,
  }
end

-- The nest is units/va_queen_nest.lua; raptor_spawner_defense.lua wakes the queen when it falls
-- (va_queen_nest_fallen). This widget only shows what the company can see.

local NEST_DEF = UnitDefNames and UnitDefNames.va_queen_nest and UnitDefNames.va_queen_nest.id
if not NEST_DEF then return false end

local BANNER_SECONDS = 7
local COLOURS = { { 1.00, 0.25, 0.85 }, { 0.20, 1.00, 0.85 }, { 1.00, 0.80, 0.20 } }

local Hud = VFS.Include("luaui/Include/va_hud.lua")
local Ash = Hud.Ash

local nest = nil          -- unitID, once seen
local seen = false
local fallenSaid = false
local banner = nil        -- { title, line, untilClock }

local function say(text)
  if WG and WG.vaVoice and WG.vaVoice.say then WG.vaVoice.say("Ketha", text, 8) end
end

local function show(title, line)
  banner = { title = title, line = line, untilClock = os.clock() + BANNER_SECONDS }
end

local function discover(unitID)
  nest = unitID
  if seen then return end
  seen = true
  show("The Queen's Nest", "Burn the roosts if you like. Burn this, and the queen wakes.")
  say("That's her nest. Leave it standing unless you want the queen up.")
  Hud.sound("beep4", 1.0)
end

function widget:UnitEnteredLos(unitID)
  if Spring.GetUnitDefID(unitID) == NEST_DEF then discover(unitID) end
end

function widget:Initialize()
  -- a reload mid-game: find a nest already in sight
  for _, uid in ipairs(Spring.GetVisibleUnits(-1, nil, false) or {}) do
    if Spring.GetUnitDefID(uid) == NEST_DEF then discover(uid) end
  end
end

function widget:GameFrame(f)
  if f % 30 ~= 11 or fallenSaid then return end
  if Hud.on("va_queen_nest_fallen") then
    fallenSaid = true
    nest = nil
    show("The nest is burning", "The queen is awake.")
    say("The nest is down. She's coming.")
  end
end

local function ring(x, y, z, r, segs, phase)
  gl.BeginEnd(GL.LINE_LOOP, function()
    for i = 0, segs - 1 do
      local a = phase + i / segs * math.pi * 2
      local px, pz = x + math.cos(a) * r, z + math.sin(a) * r
      gl.Vertex(px, (Spring.GetGroundHeight(px, pz) or y) + 6, pz)
    end
  end)
end

-- Three rings in the raptors' colours, turning against each other, and a pulse rising off the nest.
function widget:DrawWorld()
  if not nest or Spring.IsGUIHidden() or not Spring.ValidUnitID(nest) or Spring.GetUnitIsDead(nest) then return end
  local x, y, z = Spring.GetUnitPosition(nest)
  if not x then return end
  local t = os.clock()
  gl.DepthTest(true)
  for i, c in ipairs(COLOURS) do
    local pulse = 0.55 + 0.35 * math.abs(math.sin(t * (1.1 + i * 0.3)))
    gl.Color(c[1], c[2], c[3], pulse)
    gl.LineWidth(5 - i)
    ring(x, y, z, 150 + i * 46, 56, (i % 2 == 0 and -1 or 1) * t * 0.35 * i)
  end
  local k = (t * 0.6) % 1
  local c = COLOURS[1 + math.floor(t * 0.6) % #COLOURS]
  gl.Color(c[1], c[2], c[3], 0.8 * (1 - k))
  gl.LineWidth(2)
  ring(x, y, z, 120 + 240 * k, 48, 0)
  gl.LineWidth(1)
  gl.DepthTest(false)
  gl.Color(1, 1, 1, 1)
end

function widget:DrawScreenEffects()
  if not nest or Spring.IsGUIHidden() or not Spring.ValidUnitID(nest) then return end
  local x, y, z = Spring.GetUnitPosition(nest)
  if not x then return end
  local sx, sy, sz = Spring.WorldToScreenCoords(x, y + 260, z)
  if not sx or not sz or sz >= 1 then return end
  if Ash then Ash.text("QUEEN'S NEST", sx, sy, 15, { 1.0, 0.45, 0.9, 1 }, "c")
  else gl.Color(1, 0.45, 0.9, 1); gl.Text("QUEEN'S NEST", sx, sy, 15, "co") end
  gl.Color(1, 1, 1, 1)
end

function widget:DrawScreen()
  if not banner or Spring.IsGUIHidden() then return end
  local left = banner.untilClock - os.clock()
  if left <= 0 then banner = nil return end
  local vsx, vsy = Spring.GetViewGeometry()
  local a = math.min(1, left)
  local w = math.min(vsx - 40, 620)
  local x1, y1 = (vsx - w) / 2, vsy * 0.72
  if Ash then
    Ash.panel(x1, y1, x1 + w, y1 + 82, {})
    Ash.text(banner.title, vsx / 2, y1 + 48, 24, { 1.0, 0.45, 0.9, a }, "c")
    Ash.text(banner.line, vsx / 2, y1 + 18, 14, { 0.93, 0.96, 0.93, a }, "c")
  else
    gl.Color(1, 0.45, 0.9, a); gl.Text(banner.title, vsx / 2, y1 + 48, 24, "co")
    gl.Color(1, 1, 1, a); gl.Text(banner.line, vsx / 2, y1 + 18, 14, "co")
  end
  gl.Color(1, 1, 1, 1)
end
