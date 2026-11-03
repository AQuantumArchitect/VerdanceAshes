if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Field Marks",
    desc = "Rings on the ground for the authored beats: the staged first goal (gold, double ring), a wreck worth working (blue, dashed). The company is ringed on the pad until the player first selects it; that selection is reported to the campaign gadget. No pings, nothing centre-screen.",
    author = "Verdance",
    date = "2026-11-02",
    license = "GPL v2 or later",
    layer = 12,
    enabled = true,
  }
end

-- The beats decide when (beats.lua); this widget only draws what they say and reports the one fact
-- the synced side cannot see: that the player selected something.
--   the first goal   va_op_stage == 1, at va_op_goal_x/z/r (rules params: still there after a reload)
--   event marks      field_mark (id, x, z, "shape|radius|seconds") / clear_mark (id), handed over by
--                    the voice widget, which holds the VerdanceBeat global (WG.vaFieldMarks)
--   the company      ringed while the job is staged and nothing has been selected yet

local Hud = VFS.Include("luaui/Include/va_hud.lua")
local Ash = Hud.Ash
local num = Hud.num

local SEGS = 40
local COS, SIN = {}, {}
for i = 0, SEGS - 1 do
  local t = (i / SEGS) * math.pi * 2
  COS[i], SIN[i] = math.cos(t), math.sin(t)
end

-- shape -> colour name and how it is drawn. Shape carries the meaning as much as colour does.
local SHAPES = {
  goal = { col = "gold", dashed = false, double = true },    -- go here
  wreck = { col = "steam", dashed = true, double = false },  -- a wreck worth a builder
  threat = { col = "warn", dashed = false, double = false }, -- something coming
}

local marks = {}        -- id -> { x, z, r, shape, untilT, ys = { ground heights per segment } }
local selectedOnce = false
local reported = false

local function groundRing(x, z, r)
  local ys = {}
  for i = 0, SEGS - 1 do ys[i] = Spring.GetGroundHeight(x + COS[i] * r, z + SIN[i] * r) or 0 end
  return ys
end

local function addMark(id, x, z, spec)
  x, z = tonumber(x), tonumber(z)
  if not x or not z then return end
  local shape, r, seconds = tostring(spec or ""):match("^([^|]*)|([^|]*)|(.*)$")
  shape = SHAPES[shape or ""] and shape or "goal"
  r = tonumber(r) or 120
  local now = Spring.GetGameSeconds() or 0
  marks[tostring(id)] = { x = x, z = z, r = r, shape = shape, untilT = now + (tonumber(seconds) or 30), ys = groundRing(x, z, r) }
end

local function onBeat(kind, id, x, z, spec)
  if kind == "field_mark" then addMark(id, x, z, spec)
  elseif kind == "clear_mark" then marks[tostring(id or "")] = nil end
end

function widget:Initialize()
  if WG then WG.vaFieldMarks = onBeat end
end

function widget:Shutdown()
  if WG and WG.vaFieldMarks == onBeat then WG.vaFieldMarks = nil end
end

-- The first selection: the select beat's fact. Selection is unsynced, so the gadget hears it from here.
function widget:Update()
  if selectedOnce then return end
  local n = Spring.GetSelectedUnitsCount and Spring.GetSelectedUnitsCount() or 0
  if n > 0 and Hud.begun() then
    selectedOnce = true
    if not reported then
      reported = true
      Spring.SendLuaRulesMsg("VA_CMD:vabeatfact selected")
    end
  end
end

-- ---------------------------------------------------------------- draw
local ring = { x = 0, z = 0, r = 0, ys = nil, y = 0, dashed = false }
local function ringVerts()
  local x, z, r, ys, y0 = ring.x, ring.z, ring.r, ring.ys, ring.y
  if ring.dashed then
    for i = 0, SEGS - 1, 2 do
      local j = (i + 1) % SEGS
      gl.Vertex(x + COS[i] * r, ys and ys[i] or y0, z + SIN[i] * r)
      gl.Vertex(x + COS[j] * r, ys and ys[j] or y0, z + SIN[j] * r)
    end
  else
    for i = 0, SEGS - 1 do gl.Vertex(x + COS[i] * r, ys and ys[i] or y0, z + SIN[i] * r) end
  end
end

local function drawRing(x, z, r, ys, y0, col, alpha, width, dashed)
  ring.x, ring.z, ring.r, ring.ys, ring.y, ring.dashed = x, z, r, ys, y0 or 0, dashed
  gl.Color(col[1], col[2], col[3], alpha)
  gl.LineWidth(width)
  gl.BeginEnd(dashed and GL.LINES or GL.LINE_LOOP, ringVerts)
end

-- A small diamond flat on the ground: the board's ◇ for the first goal, so the ring and the board agree.
local dia = { x = 0, y = 0, z = 0, s = 0 }
local function diamondVerts()
  gl.Vertex(dia.x, dia.y, dia.z - dia.s); gl.Vertex(dia.x + dia.s, dia.y, dia.z)
  gl.Vertex(dia.x, dia.y, dia.z + dia.s); gl.Vertex(dia.x - dia.s, dia.y, dia.z)
end

local goalCache = { key = nil, ys = nil, inner = nil }
local function drawGoal(t)
  if num("va_op_stage", 0) ~= 1 then return end
  local gx, gz, gr = num("va_op_goal_x", -1), num("va_op_goal_z", -1), num("va_op_goal_r", 300)
  if gx < 0 or gz < 0 then return end
  local key = gx * 1e6 + gz + gr * 1e-3
  if goalCache.key ~= key then
    goalCache.key, goalCache.ys, goalCache.inner = key, groundRing(gx, gz, gr), groundRing(gx, gz, gr * 0.82)
    goalCache.y = Spring.GetGroundHeight(gx, gz) or 0
  end
  local gold = Ash.COL.gold
  local pulse = 0.45 + 0.35 * math.abs(math.sin(t * 1.4))
  drawRing(gx, gz, gr, goalCache.ys, 0, gold, pulse, 3, false)
  drawRing(gx, gz, gr * 0.82, goalCache.inner, 0, gold, pulse * 0.6, 1.5, false)
  dia.x, dia.y, dia.z, dia.s = gx, goalCache.y + 4, gz, math.max(24, gr * 0.12)
  gl.Color(gold[1], gold[2], gold[3], 0.85)
  gl.LineWidth(2)
  gl.BeginEnd(GL.LINE_LOOP, diamondVerts)
end

local function drawMarks(now, t)
  for id, m in pairs(marks) do
    if m.untilT <= now then
      marks[id] = nil
    else
      local spec = SHAPES[m.shape]
      local col = Ash.COL[spec.col] or Ash.COL.gold
      local fade = math.min(1, (m.untilT - now) / 2)
      local pulse = (0.5 + 0.35 * math.abs(math.sin(t * 2.2))) * fade
      drawRing(m.x, m.z, m.r, m.ys, 0, col, pulse, 2.5, spec.dashed)
      if spec.double then drawRing(m.x, m.z, m.r * 0.8, nil, Spring.GetGroundHeight(m.x, m.z) or 0, col, pulse * 0.6, 1.5, false) end
    end
  end
end

-- Until the first selection, every unit of ours wears a thin pulsing ring: "these are yours".
local function drawCompany(t)
  if selectedOnce or num("va_op_stage", 0) < 1 or not Hud.begun() then return end
  local team = Spring.GetMyTeamID and Spring.GetMyTeamID()
  local units = team and Spring.GetTeamUnits(team) or {}
  local col = Ash.COL.gold
  local alpha = 0.35 + 0.35 * math.abs(math.sin(t * 2.6))
  for i = 1, math.min(#units, 40) do
    local x, y, z = Spring.GetUnitPosition(units[i])
    if x then
      local r = (Spring.GetUnitRadius and Spring.GetUnitRadius(units[i])) or 20
      drawRing(x, z, math.max(14, r * 1.3), nil, y + 2, col, alpha, 1.5, false)
    end
  end
end

function widget:DrawWorld()
  if Spring.IsGUIHidden() or Hud.over() or not Ash then return end
  local t = os.clock()
  local now = Spring.GetGameSeconds() or 0
  if gl.DepthTest then gl.DepthTest(false) end
  drawGoal(t)
  drawMarks(now, t)
  drawCompany(t)
  gl.LineWidth(1)
  gl.Color(1, 1, 1, 1)
end
