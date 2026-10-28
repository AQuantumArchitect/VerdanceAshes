if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Lab Tier",
    desc = "The company raises T1 labs only, except at All That Simmers: every constructor on the "
        .. "player's side sees its T2 and experimental factories greyed out, and creating one is refused.",
    author = "Verdance",
    date = "2026-10-26",
    license = "GPL v2 or later",
    layer = 4,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then
  return
end

-- Factories the company may never raise (owner, 2026-10-26: "no building t2 labs"). Named, and any
-- factory whose techlevel is 2 or more, so a lab BAR adds later is caught too.
local NAMED = {
  "armalab", "coralab", "legalab", "armavp", "coravp", "legavp", "armaap", "coraap", "legaap",
  "armasy", "corasy", "legadvshipyard", "armhaapuw", "corhaapuw",
  "armhalab", "corhalab", "leghalab", "armhavp", "corhavp", "leghavp", "armhaap", "corhaap", "leghaap",
  "armhasy", "corhasy", "armapt3", "corapt3", "legapt3",
  "armshltx", "armshltxuw", "corgant", "corgantuw", "leggant", "leggantuw",
}

local blocked = {}   -- unitDefID -> true
for _, name in ipairs(NAMED) do
  local ud = UnitDefNames and UnitDefNames[name]
  if ud then blocked[ud.id] = true end
end
for id, ud in pairs(UnitDefs or {}) do
  local tl = tonumber((ud.customParams or {}).techlevel) or 1
  if ud.isFactory and tl >= 2 then blocked[id] = true end
end

local function playerTeam()
  local t = tonumber((Spring.GetGameRulesParam("va_player_team")))
  if t and Spring.GetTeamInfo(t, false) then return t end
  local opts = Spring.GetModOptions() or {}
  return tonumber(opts.va_player_team or opts.playerteam) or 0
end

-- All That Simmers is where the company may raise T2 factories (owner, 2026-10-26).
local T2_MAPS = { all_that_simmers = true }
local T2_MAP_NAMES = { "all that simmers" }

-- The mission seed's map, else BAR's map name. Asked on every build order, so decided once.
local t2Here = nil
local function t2Allowed()
  if t2Here ~= nil then return t2Here end
  local ok, m = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  local mid = ok and type(m) == "table" and tostring(m.deploymentMapId or m.mapId or "") or ""
  t2Here = T2_MAPS[mid] == true
  local name = string.lower(tostring((Game and Game.mapName) or ""))
  for _, n in ipairs(T2_MAP_NAMES) do
    if name:find(n, 1, true) then t2Here = true end
  end
  return t2Here
end

local TOOLTIP = "Not on this ground: the company raises T2 factories only at All That Simmers."

-- Grey the blocked factories out of one unit's build menu (they stay visible, with the reason).
local function grey(unitID, unitDefID)
  if t2Allowed() then return end
  local ud = UnitDefs[unitDefID]
  if not ud or not ud.buildOptions or #ud.buildOptions == 0 then return end
  for _, opt in ipairs(ud.buildOptions) do
    if blocked[opt] then
      local i = Spring.FindUnitCmdDesc(unitID, -opt)
      if i then Spring.EditUnitCmdDesc(unitID, i, { disabled = true, tooltip = TOOLTIP }) end
    end
  end
end

function gadget:AllowUnitCreation(unitDefID, builderID, builderTeam)
  if blocked[unitDefID] and builderTeam == playerTeam() and not t2Allowed() then
    return false
  end
  return true
end

function gadget:UnitCreated(unitID, unitDefID, unitTeam)
  if unitTeam == playerTeam() then grey(unitID, unitDefID) end
end

function gadget:UnitGiven(unitID, unitDefID, newTeam)
  if newTeam == playerTeam() then grey(unitID, unitDefID) end
end

function gadget:Initialize()
  local team = playerTeam()
  for _, unitID in ipairs(Spring.GetTeamUnits(team) or {}) do
    grey(unitID, Spring.GetUnitDefID(unitID))
  end
end
