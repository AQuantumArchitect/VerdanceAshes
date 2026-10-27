if not VFS.Include("LuaRules/Configs/va_active.lua") then return false end -- plain BAR unless the hub launched this
-- Commander suits in the field (verdance.campaign.suits). A king in All That Simmers needs a suit;
-- two of the three ways to get one happen here:
--
--   queen_rez    wherever the hive queen falls, a Legion commander's wreck (legcom_dead) lies under
--                her corpse; raise it with a rez bot and the suit is the company's
--   stolen_koom  on Koom Valley, a war commander raised from its wreck (or captured) onto the company
--                is its suit
--
-- (The third, buying Cortex's, is a hub purchase.) The won suit goes home in the result as
-- commanderSuit = { unitDef, how } (GG.VA_SuitJson, read by game_verdance_campaign.lua).
--
-- mission.noCommanders (Tabula): every start commander but the company's is taken away, quietly.
function gadget:GetInfo()
  return {
    name = "Verdance Suits",
    desc = "Commander suits: the queen's Legion suit, stealing on Koom, no commanders on Tabula",
    author = "Verdance",
    layer = 0,
    enabled = true,
  }
end

if not gadgetHandler:IsSyncedCode() then return end

local mapId = ""
local playerTeam = 0
local noCommanders = false
local won                               -- { unitDef, how }
local queenSuits = {}                   -- { x, z, fid } wrecks laid under fallen queens
local pendingWrecks = {}                -- queens fallen this frame: lay the wreck next frame
local SWEEP = { [3] = true, [8] = true, [30] = true, [90] = true, [150] = true }
local QUEEN_REACH = 260                 -- a suit raised this close to a queen's wreck is hers

function gadget:Initialize()
  local ok, data = pcall(VFS.Include, "singleplayer/verdance_ashes/generated/va_current.lua")
  if not ok or type(data) ~= "table" then
    gadgetHandler:RemoveGadget(self)
    return
  end
  mapId = tostring(data.deploymentMapId or data.mapId or "")
  playerTeam = tonumber(data.balance and data.balance.playerTeamID) or 0
  noCommanders = data.noCommanders == true
  GG.VA_SuitJson = function()
    if not won then return "null" end
    return '{"unitDef":"' .. won.unitDef .. '","how":"' .. won.how .. '"}'
  end
end

local function isCommander(defID)
  local ud = defID and UnitDefs[defID]
  if not ud then return false end
  local cp = ud.customParams or {}
  if cp.isdecoycommander or cp.decoyfor then return false end
  return (cp.iscommander or cp.isCommander or cp.commander) and true or false
end

local function suitDef(defID)
  local n = (UnitDefs[defID] and UnitDefs[defID].name) or ""
  for _, base in ipairs({ "armcom", "corcom", "legcom" }) do
    if n:sub(1, #base) == base then return base end
  end
  return nil
end

local function win(defID, how, uid)
  if won then return end
  local base = suitDef(defID)
  if not base then return end
  won = { unitDef = base, how = how }
  Spring.SetGameRulesParam("va_suit_won", base, { public = true })
  Spring.SetGameRulesParam("va_suit_how", how, { public = true })
  if uid then Spring.SetUnitRulesParam(uid, "va_label", "The company's suit", { public = true }) end
  Spring.Echo("VA_SUIT_WON def=" .. base .. " how=" .. how)
  if SendToUnsynced then SendToUnsynced("VERDANCE_MISSION_EVENT", "suit_won", base .. ":" .. how) end
end

local function sweepCommanders()
  local removed = 0
  for _, tid in ipairs(Spring.GetTeamList() or {}) do
    if tid ~= playerTeam then
      for _, uid in ipairs(Spring.GetTeamUnits(tid) or {}) do
        if isCommander(Spring.GetUnitDefID(uid)) then
          Spring.DestroyUnit(uid, false, true)
          removed = removed + 1
        end
      end
    end
  end
  if removed > 0 then Spring.Echo("VA_NO_COMMANDERS removed=" .. removed .. " map=" .. mapId) end
end

local function layQueenSuit(q)
  local fdef = FeatureDefNames and FeatureDefNames["legcom_dead"]
  if not fdef then
    Spring.Echo("VA_SUIT_QUEEN_NO_WRECKDEF")
    return
  end
  local y = Spring.GetGroundHeight(q.x, q.z)
  local fid = Spring.CreateFeature("legcom_dead", q.x, y, q.z, 0)
  if fid then
    -- a placed wreck knows no unit until told: raised, it is a Legion commander
    if Spring.SetFeatureResurrect then pcall(Spring.SetFeatureResurrect, fid, "legcom", 0) end
    if Spring.SetFeatureRulesParam then pcall(Spring.SetFeatureRulesParam, fid, "va_label", "A Legion commander suit", { public = true }) end
    queenSuits[#queenSuits + 1] = { x = q.x, z = q.z, fid = fid }
    Spring.Echo("VA_SUIT_UNDER_QUEEN at=" .. math.floor(q.x) .. "," .. math.floor(q.z) .. " feature=" .. fid)
  end
end

function gadget:GameFrame(frame)
  if noCommanders and SWEEP[frame] then sweepCommanders() end
  if #pendingWrecks > 0 then
    for _, q in ipairs(pendingWrecks) do layQueenSuit(q) end
    pendingWrecks = {}
  end
end

function gadget:UnitDestroyed(unitID, unitDefID)
  local ud = UnitDefs[unitDefID]
  if ud and (ud.name or ""):find("^raptor_queen") then
    local x, _, z = Spring.GetUnitPosition(unitID)
    if x then pendingWrecks[#pendingWrecks + 1] = { x = x, z = z } end
  end
end

local function nearQueenSuit(uid)
  local x, _, z = Spring.GetUnitPosition(uid)
  if not x then return false end
  for _, q in ipairs(queenSuits) do
    if (x - q.x) ^ 2 + (z - q.z) ^ 2 <= QUEEN_REACH * QUEEN_REACH then return true end
  end
  return false
end

function gadget:UnitCreated(unitID, unitDefID, unitTeam, builderID)
  if unitTeam ~= playerTeam or won or not isCommander(unitDefID) then return end
  if (Spring.GetGameFrame() or 0) <= 90 then return end   -- the start commander is not a suit won
  local bud = builderID and UnitDefs[Spring.GetUnitDefID(builderID) or -1]
  if not (bud and bud.canResurrect) then return end
  if suitDef(unitDefID) == "legcom" and nearQueenSuit(unitID) then
    win(unitDefID, "queen_rez", unitID)
  elseif mapId == "koom_valley" then
    win(unitDefID, "stolen_koom", unitID)
  end
end

function gadget:UnitGiven(unitID, unitDefID, newTeam)
  -- a commander captured onto the company on Koom is stolen just the same
  if newTeam == playerTeam and not won and mapId == "koom_valley" and isCommander(unitDefID) then
    win(unitDefID, "stolen_koom", unitID)
  end
end
