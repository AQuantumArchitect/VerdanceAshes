if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
local gadget = gadget

function gadget:GetInfo()
  return {
    name = "Verdance Lab Tier",
    desc = "The company raises T1 labs only: every constructor on the player's side, hero or built, "
        .. "loses its T2 and experimental factories (build menu and the creation itself).",
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

-- Strip the blocked factories from one unit's build menu.
local function strip(unitID, unitDefID)
  local ud = UnitDefs[unitDefID]
  if not ud or not ud.buildOptions or #ud.buildOptions == 0 then return end
  for _, opt in ipairs(ud.buildOptions) do
    if blocked[opt] then
      local i = Spring.FindUnitCmdDesc(unitID, -opt)
      if i then Spring.RemoveUnitCmdDesc(unitID, i) end
    end
  end
end

function gadget:AllowUnitCreation(unitDefID, builderID, builderTeam)
  if blocked[unitDefID] and builderTeam == playerTeam() then
    return false
  end
  return true
end

function gadget:UnitCreated(unitID, unitDefID, unitTeam)
  if unitTeam == playerTeam() then strip(unitID, unitDefID) end
end

function gadget:UnitGiven(unitID, unitDefID, newTeam)
  if newTeam == playerTeam() then strip(unitID, unitDefID) end
end

function gadget:Initialize()
  local team = playerTeam()
  for _, unitID in ipairs(Spring.GetTeamUnits(team) or {}) do
    strip(unitID, Spring.GetUnitDefID(unitID))
  end
end
