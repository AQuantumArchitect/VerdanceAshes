-- campaign/crew.lua: the company on the field: the roster, who drops (crew confirm, the hot drop), anchor keeps, what was dropped
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: VA_CREW_SELECT, VA_CREW_confirm, VA_CREW_isAnchorKeep, VA_CREW_isCommerceKitSpec,
-- VA_CREW_loadRoster, VA_CREW_publish, VA_HOT, VA_HOT_drop, vaNoteDropped
-- Uses: crew_packs, crew_storage, spawn, start, state

-- Muster the Band: packed table (Lua 5.1 local budget). Fresh chapter only.
VA_CREW_SELECT = {
  pending = false,
  confirmed = false,
  selected = {},
  wallet = 5,
  spent = 0,
  anchorX = nil,
  anchorZ = nil,
  roster = nil,
}
-- Hot drop (tools/verdance_kernel/hot_drop.py): the kernel launched before the player chose who
-- goes. The company waits off the field; the drop names the packs and the reserve that board.
VA_HOT = {
  token = nil,     -- mission.hotDrop.token; a drop must carry it
  pending = false, -- loaded and waiting for the drop
  reserve = {},    -- reserve specs held back: { spec, teamID, baseX, baseZ, groupX, groupZ, force }
}

-- Muster the Band helpers (globals — keep main-chunk locals free).
function VA_CREW_loadRoster()
  if VA_CREW_SELECT.roster then return VA_CREW_SELECT.roster end
  local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_crew_roster.lua")
  if not ok or type(mod) ~= "table" then
    ok, mod = pcall(VFS.Include, "LuaRules/gadgets/include/va_crew_roster.lua")
  end
  if ok and type(mod) == "table" then
    VA_CREW_SELECT.roster = mod
    VA_CREW_SELECT.wallet = tonumber(mod.START_WALLET_TNB) or 5
  else
    Spring.Echo("VA_CREW_ROSTER_MISSING")
    VA_CREW_SELECT.roster = { CORE = { "vane", "ketha" }, HEROES = {}, BAND_ORDER = {}, SEAT_CAP = 3,
      START_WALLET_TNB = 5, defaultAutoPick = function() return {} end, get = function() return nil end,
      isCore = function() return false end, hireCost = function() return 1 end, hireKmCost = function() return 0 end,
      isMentor = function() return false end, MENTOR_PRODUCTS = {} }
  end
  GG = GG or {}
  GG.VA_CrewIsMentor = function(heroId)
    local r = VA_CREW_SELECT.roster
    return r and r.isMentor and r.isMentor(heroId) or false
  end
  -- Cortex packs spend km$ (1km$ = 1000 metal). Prefer mission commerce bag.
  local com = mission and mission.commerce
  local km = com and tonumber(com.metalK)
  VA_CREW_SELECT.walletKm = (km ~= nil) and math.max(0, math.floor(km)) or 7
  return VA_CREW_SELECT.roster
end

-- Eco / support defs that still drop with the hub crew kit (not replaced by heroes).
-- Mex + storage + nano matter for Consul / Twitcher dig-in sorties.
local VA_CREW_ANCHOR_KEEP = {
  legmex = true, armmex = true, cormex = true,
  legwin = true, legsolar = true, armsolar = true, corsolar = true,
  legrad = true, armrad = true, corrad = true,
  legestor = true, legmstor = true, armestor = true, armmstor = true, corestor = true, cormstor = true,
  legck = true, legcv = true, legca = true, corck = true, armck = true,
  legnanotc = true, armnanotc = true, cornanotc = true,
}

function VA_CREW_isAnchorKeep(spec)
  if not spec then return false end
  if spec.heroId or spec.hero then return false end -- heroes wait for muster
  local defName = tostring(spec.unitDefName or spec.def or spec[1] or "")
  if VA_CREW_ANCHOR_KEEP[defName] then return true end
  if spec.atMetalSpots or spec.nearestMetalSpots then return true end
  -- Generic rez still allowed as a spare until Ketha drops (no hero tag).
  if defName == "legrezbot" then return true end
  return false
end

-- Bought broker kit (punch / fabs / constructors / nanos from mission.commerce.deploy).
-- RULE (one owner): VA_LOGISTICS.spawnCommerceDeployKit spawns the commerce deploy
-- bag at GameStart, straight from mission.commerce.deploy. The layout force in
-- playableSetup may still carry copies of those items (scripts/build_next_mission_v1.ps1
-- Add-CommerceDeployToKit composes them into the player kit for previews); the setup
-- spawn must skip every one of them or the kit lands twice. The PS1 stamps each such
-- spec with commerceDeploy=true and a packageTag; the tag heuristics below cover
-- seeds built before the stamp existed.
function VA_CREW_isCommerceKitSpec(spec)
  if not spec then return false end
  if spec.commerceDeploy == true or spec.commerceDeploy == 1 then return true end
  if spec.unitPrinter == true or spec.unitPrinter == 1 then return true end
  local tag = tostring(spec.packageTag or "")
  if tag == "" then return false end
  if tag:match("^pad_") or tag:match("^crew_") then return false end
  return true
end

function VA_CREW_publish()
  local cs = VA_CREW_SELECT
  Spring.SetGameRulesParam("va_crew_pending", cs.pending and 1 or 0, { public = true })
  Spring.SetGameRulesParam("va_crew_ready", cs.confirmed and 1 or 0, { public = true })
  Spring.SetGameRulesParam("va_crew_wallet", tonumber(cs.wallet) or 0, { public = true })
  Spring.SetGameRulesParam("va_crew_wallet_km", tonumber(cs.walletKm) or 0, { public = true })
  Spring.SetGameRulesParam("va_crew_spent", tonumber(cs.spent) or 0, { public = true })
  local parts = {}
  for i = 1, #(cs.selected or {}) do
    parts[#parts + 1] = tostring(cs.selected[i])
  end
  Spring.SetGameRulesParam("va_crew_selected", table.concat(parts, ","), { public = true })
end

-- Who of the company is on this field (va_dropped_heroes, a rules param so it outlives a LuaRules
-- reload): the exfil manifest carries it, and a hero who dropped but is neither going nor staying
-- at extraction did not survive (verdance.campaign.roster).
VA_DROPPED = VA_DROPPED or {}
function vaNoteDropped(heroId)
  heroId = tostring(heroId or "")
  if heroId == "" then return end
  for _, h in ipairs(VA_DROPPED) do if h == heroId then return end end
  local prior = tostring(Spring.GetGameRulesParam("va_dropped_heroes") or "")
  if #VA_DROPPED == 0 and prior ~= "" then
    for h in prior:gmatch("[^,]+") do VA_DROPPED[#VA_DROPPED + 1] = h end
    for _, h in ipairs(VA_DROPPED) do if h == heroId then return end end
  end
  VA_DROPPED[#VA_DROPPED + 1] = heroId
  Spring.SetGameRulesParam("va_dropped_heroes", table.concat(VA_DROPPED, ","), { public = true })
end

function VA_CREW_confirm(selectedIds)
  local cs = VA_CREW_SELECT
  if cs.confirmed then
    Spring.Echo("VA_CREW_ALREADY_CONFIRMED")
    return false
  end
  local roster = VA_CREW_loadRoster()
  local seatCap = tonumber(roster.SEAT_CAP) or 3
  -- The hub sheet already chose who ships. Seat cap is the first-run
  -- formation pick, not a second clip that drops the fourth pack.
  local fromSheet = (mission and type(mission.crewBand) == "table")
    or (mission and type(mission.deployAces) == "table")
  local cap = fromSheet and 64 or seatCap
  local picks = {}
  local spent = 0
  local spentKm = 0
  for _, id in ipairs(selectedIds or {}) do
    id = tostring(id or "")
    if id ~= "" and not (roster.isCore and roster.isCore(id)) then
      local cost = (roster.hireCost and roster.hireCost(id)) or 0
      local costKm = (roster.hireKmCost and roster.hireKmCost(id)) or 0
      if #picks < cap then
        picks[#picks + 1] = id
        spent = spent + cost
        spentKm = spentKm + costKm
      end
    end
  end
  local wallet = tonumber(cs.wallet) or (roster.START_WALLET_TNB or 5)
  local walletKm = tonumber(cs.walletKm) or 7
  -- Formation Tnb was paid on the hub. Do not refuse the sheet over the
  -- sortie fab wallet.
  if not fromSheet and spent > wallet then
    Spring.Echo("VA_CREW_OVERBUDGET spent=" .. tostring(spent) .. " wallet=" .. tostring(wallet))
    return false
  end
  if not fromSheet and spentKm > walletKm then
    Spring.Echo("VA_CREW_OVERBUDGET_KM spent=" .. tostring(spentKm) .. " walletKm=" .. tostring(walletKm))
    return false
  end
  local baseX = cs.anchorX or ((Game.mapSizeX or 0) * 0.23)
  local baseZ = cs.anchorZ or ((Game.mapSizeZ or 0) * 0.24)
  local total = 0
  -- Core always, while they live: mission.heroes names the living (dead heroes are not on it)
  local living = nil
  if mission and type(mission.heroes) == "table" and #mission.heroes > 0 then
    living = {}
    for _, mh in ipairs(mission.heroes) do living[tostring(mh.id or mh.heroId or "")] = true end
  end
  local core = {}
  for _, id in ipairs(roster.CORE or { "vane", "ketha" }) do
    if not living or living[tostring(id)] then core[#core + 1] = id
    else Spring.Echo("VA_CREW_CORE_FALLEN " .. tostring(id)) end
  end
  for ci, id in ipairs(core) do
    total = total + VA_CREW_spawnHeroPack(id, baseX, baseZ, (ci - 1) * 200)
  end
  for i, id in ipairs(picks) do
    total = total + VA_CREW_spawnHeroPack(id, baseX, baseZ, 400 + (i - 1) * 220)
  end
  do
    local present = {}
    for _, id in ipairs(core) do present[#present + 1] = id end
    for _, id in ipairs(picks) do present[#present + 1] = id end
    total = total + VA_BOND_apply(present, baseX, baseZ, 400 + #picks * 220)
  end
  -- No free pad M/E storage — Solarium (and bought eco) own that seat.
  cs.selected = picks
  cs.spent = spent
  cs.wallet = wallet - spent
  cs.walletKm = walletKm - spentKm
  cs.confirmed = true
  cs.pending = false
  -- Formation hireTnb / hireKm is paid at the hub (commerce bag). The sortie
  -- Tnb bank is the fab stake for this Drop — never debit it again here.
  Spring.Echo("VA_CREW_HIRE_HUB_PAID spentTnb=" .. tostring(spent)
    .. " spentKm=" .. tostring(spentKm)
    .. " sortieBank=" .. tostring(tenebLoot and tenebLoot.bank or "?"))
  VA_CREW_publish()
  if SendToUnsynced then
    SendToUnsynced("VERDANCE_BEAT", "bark", "Ketha", "Band sealed. Drop them.", 6)
    SendToUnsynced("VERDANCE_BEAT", "crew_ready", table.concat(picks, ","), tostring(spent), tostring(cs.wallet), "")
  end
  Spring.Echo("VA_CREW_CONFIRMED picks=" .. table.concat(picks, ",")
    .. " spentTnb=" .. tostring(spent) .. " spentKm=" .. tostring(spentKm)
    .. " units=" .. tostring(total))
  -- Solarium (and any storage escorts) just landed — restore caps now and
  -- again on frames 1–3 in case BAR Team Resourcing still races us.
  cs.storageRefreshUntil = math.max(tonumber(cs.storageRefreshUntil) or 0, 3)
  VA_refreshPlayerStorageCaps("crew_confirm")
  return true
end

-- The drop: the packs and reserve the player chose on the hub, into the field that is
-- already loaded. Message: "vahotdrop token|pack,pack|unitdef:n,unitdef:n".
function VA_HOT_drop(line)
  if not VA_HOT.pending then
    Spring.Echo("VA_HOTDROP_IGNORED not_pending")
    return false
  end
  local token, packs, units = tostring(line or ""):match("^([^|]*)|([^|]*)|?(.*)$")
  if token ~= VA_HOT.token then
    Spring.Echo("VA_HOTDROP_IGNORED stale_token " .. tostring(token))
    return false
  end
  local picks = {}
  for id in string.gmatch(packs or "", "[%w_]+") do picks[#picks + 1] = id end
  local want = {}
  for def, n in string.gmatch(units or "", "([%w_]+):(%d+)") do want[def] = (want[def] or 0) + tonumber(n) end
  local landed = 0
  for _, held in ipairs(VA_HOT.reserve) do
    local def = tostring(held.spec.unitDefName or "")
    local n = math.min(want[def] or 0, tonumber(held.spec.count) or 1)
    if n > 0 then
      local spec = {}
      for k, v in pairs(held.spec) do spec[k] = v end
      spec.count = n
      want[def] = want[def] - n
      landed = landed + spawnUnitSpec(spec, held.teamID, held.baseX, held.baseZ, held.groupX, held.groupZ, {}, held.force)
    end
  end
  VA_HOT.pending = false
  VA_CREW_confirm(picks)
  sweepPlayerCommanders("hotdrop")
  Spring.SetGameRulesParam("va_hotdrop_pending", 0, { public = true })
  Spring.Echo("VA_HOTDROP_DONE packs=" .. table.concat(picks, ",") .. " reserve=" .. tostring(landed))
  return true
end
