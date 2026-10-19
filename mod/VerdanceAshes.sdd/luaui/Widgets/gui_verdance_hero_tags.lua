local widget = widget

function widget:GetInfo()
  return {
    name = "Verdance Hero Tags",
    desc = "Floating name tags over named heroes and their recoverable wrecks",
    author = "Claude / Luke Spooner",
    date = "2026-07-12",
    license = "GPL v2 or later",
    layer = 6,
    enabled = true,
  }
end

-- Modeled on BAR's gui_com_nametags: unsynced scan of public rules params,
-- projected with WorldToScreenCoords in DrawScreenEffects so tags survive
-- post-processing. At most a handful of heroes exist, so a 1 Hz rescan plus
-- per-frame projection is cheap.

local trackedUnits = {}   -- unitID -> { name, critical, height }
local trackedWrecks = {}  -- featureID -> { name }
local lastScan = -100

-- Ash Console tokens (docs/UI_ASH_CONSOLE.md)
local HERO_COL = { 0.490, 1.000, 0.541, 1.0 }  -- good
local CRIT_COL = { 0.831, 0.769, 0.604, 1.0 }  -- gold
local WRECK_COL = { 1.000, 0.490, 0.490, 1.0 } -- bad
do
  local ok, Ash = pcall(VFS.Include, "luaui/Include/va_ash_tokens.lua")
  if not ok or type(Ash) ~= "table" then
    ok, Ash = pcall(VFS.Include, "LuaUI/Include/va_ash_tokens.lua")
  end
  if ok and type(Ash) == "table" and Ash.COL then
    HERO_COL = { Ash.COL.good[1], Ash.COL.good[2], Ash.COL.good[3], 1 }
    CRIT_COL = { Ash.COL.gold[1], Ash.COL.gold[2], Ash.COL.gold[3], 1 }
    WRECK_COL = { Ash.COL.bad[1], Ash.COL.bad[2], Ash.COL.bad[3], 1 }
  end
end

local function scan()
  trackedUnits = {}
  local myTeam = Spring.GetMyTeamID()
  local units = Spring.GetTeamUnits(myTeam) or {}
  for i = 1, #units do
    local unitID = units[i]
    local name = Spring.GetUnitRulesParam(unitID, "va_hero_name")
    if type(name) == "string" and name ~= "" then
      local defID = Spring.GetUnitDefID(unitID)
      local ud = defID and UnitDefs[defID]
      local level = tonumber(Spring.GetUnitRulesParam(unitID, "va_hero_level") or 1) or 1
      local rank = Spring.GetUnitRulesParam(unitID, "va_hero_rank")
      if type(rank) ~= "string" or rank == "" then rank = "Runner" end
      local vetRank = Spring.GetUnitRulesParam(unitID, "va_vet_rank")
      if type(vetRank) ~= "string" or vetRank == "" or vetRank == "green" then
        vetRank = nil
      end
      trackedUnits[unitID] = {
        name = name,
        critical = (Spring.GetUnitRulesParam(unitID, "va_hero_critical") or 0) == 1,
        level = level,
        rank = rank,
        vetRank = vetRank,
        height = (ud and ud.height or 40) + 22,
      }
    end
  end
  trackedWrecks = {}
  local features = Spring.GetAllFeatures and Spring.GetAllFeatures() or {}
  for i = 1, #features do
    local featureID = features[i]
    local name = Spring.GetFeatureRulesParam and Spring.GetFeatureRulesParam(featureID, "va_hero_wreck_name")
    if type(name) == "string" and name ~= "" then
      trackedWrecks[featureID] = { name = name }
    end
  end
end

function widget:GameFrame(frame)
  if frame - lastScan >= 30 then
    lastScan = frame
    scan()
  end
end

local function drawTag(sx, sy, label, color)
  gl.Color(color[1], color[2], color[3], color[4])
  gl.Text(label, sx, sy, 13, "co")
end

function widget:DrawScreenEffects()
  if Spring.IsGUIHidden() then return end
  for unitID, rec in pairs(trackedUnits) do
    if Spring.ValidUnitID(unitID) and Spring.IsUnitVisible(unitID, 50, true) then
      local x, y, z = Spring.GetUnitPosition(unitID)
      if x then
        local sx, sy, sz = Spring.WorldToScreenCoords(x, y + rec.height, z)
        if sz and sz <= 1 then
          -- Clarity: "Vane L5 Captain · hardened" so farmed power is visible mid-fight.
          local label = string.format("%s  L%d %s", rec.name, rec.level or 1, rec.rank or "")
          if rec.vetRank then
            label = label .. " · " .. tostring(rec.vetRank)
          end
          drawTag(sx, sy, label, rec.critical and CRIT_COL or HERO_COL)
        end
      end
    end
  end
  for featureID, rec in pairs(trackedWrecks) do
    if Spring.ValidFeatureID and Spring.ValidFeatureID(featureID) then
      local x, y, z = Spring.GetFeaturePosition(featureID)
      if x then
        local sx, sy, sz = Spring.WorldToScreenCoords(x, y + 50, z)
        if sz and sz <= 1 then
          drawTag(sx, sy, string.upper(rec.name) .. " (DOWN)", WRECK_COL)
        end
      end
    end
  end
  gl.Color(1, 1, 1, 1)
end
