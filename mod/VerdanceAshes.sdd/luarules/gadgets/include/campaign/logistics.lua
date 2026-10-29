-- campaign/logistics.lua: mercenary logistics: the deploy kit, pending deliveries, the brute crash
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: VA_LOGISTICS, armPendingDeliveries, spawnBruteCrashFromEdge, tickPendingDeliveries
-- Uses: objective_pad, reinforcements, spawn, state

-- Living logistics: deferred combat packs arrive mid-sortie from map-web / launcher.
-- Packed into one gadget-env table so this file stays under Lua 5.1's 200-local limit
-- (Exceeded → gadget fails to load → BAR Initial Spawn drops a naked Legion com only).
VA_LOGISTICS = { pending = {} }

function VA_LOGISTICS.infilAnchor()
  local dx, dz = VA_padPoint()
  if dx and dz then return dx, dz end
  local px, pz = teamUnitCentroid(playerTeamID)
  if px then return px, pz end
  return (Game.mapSizeX or 0) * 0.5, (Game.mapSizeZ or 0) * 0.5
end

function VA_LOGISTICS.publishInboundHud()
  local n = 0
  for _, d in ipairs(VA_LOGISTICS.pending) do
    if d and not d.arrived then
      n = n + 1
      local left = math.max(0, (d.dueFrame or 0) - (Spring.GetGameFrame() or 0))
      Spring.SetGameRulesParam("va_inbound_" .. n .. "_label", tostring(d.label or d.listingId or "shipment"), { public = true })
      Spring.SetGameRulesParam("va_inbound_" .. n .. "_source", tostring(d.sourceLabel or d.mode or ""), { public = true })
      Spring.SetGameRulesParam("va_inbound_" .. n .. "_eta", math.floor(left / 30), { public = true })
      Spring.SetGameRulesParam("va_inbound_" .. n .. "_count", tonumber(d.count) or 0, { public = true })
      Spring.SetGameRulesParam("va_inbound_" .. n .. "_mode", tostring(d.mode or ""), { public = true })
    end
  end
  Spring.SetGameRulesParam("va_inbound_total", n, { public = true })
end

function VA_LOGISTICS.spawnPackageDelivery(spec)
  if not playerTeamID or type(spec) ~= "table" then return 0 end
  local defName = tostring(spec.unitDef or "")
  local count = math.max(1, math.min(24, math.floor(tonumber(spec.count) or 1)))
  if defName == "" or not UnitDefNames or not UnitDefNames[defName] then
    Spring.Echo("VA_DELIVERY_FAIL missing_def=" .. defName)
    return 0
  end
  local mode = tostring(spec.mode or "map_web")
  local tx, tz = VA_LOGISTICS.infilAnchor()
  local x, z
  if mode == "pawn_launcher" then
    -- Land near infil with tight scatter.
    x = tx + ((math.random() * 2) - 1) * 160
    z = tz + ((math.random() * 2) - 1) * 160
  else
    -- Deliveries come in over the map edge nearest the company's pad.
    local sx, sz = Game.mapSizeX or 1, Game.mapSizeZ or 1
    local edges = {
      { x = 220, z = tz }, { x = sx - 220, z = tz },
      { x = tx, z = 220 }, { x = tx, z = sz - 220 },
    }
    local best, bestD = edges[1], math.huge
    for _, e in ipairs(edges) do
      local d = (e.x - tx) ^ 2 + (e.z - tz) ^ 2
      if d < bestD then best, bestD = e, d end
    end
    x, z = best.x, best.z
  end
  local spawned = 0
  local hmin = tonumber(spec.healthFracMin) or 1
  local hmax = tonumber(spec.healthFracMax) or 1
  local hfrac = (hmin + hmax) * 0.5
  for i = 1, count do
    local ux, uz
    if mode == "pawn_launcher" then
      ux = x + ((i % 3) - 1) * 55
      uz = z + math.floor((i - 1) / 3) * 55
    else
      ux = x + ((i % 3) - 1) * 70
      uz = z + math.floor((i - 1) / 3) * 70
    end
    ux = math.max(48, math.min((Game.mapSizeX or 96) - 48, ux))
    uz = math.max(48, math.min((Game.mapSizeZ or 96) - 48, uz))
    local uid = Spring.CreateUnit(defName, ux, Spring.GetGroundHeight(ux, uz), uz, 0, playerTeamID)
    if uid then
      spawned = spawned + 1
      Spring.SetUnitRulesParam(uid, "va_package_tag", tostring(spec.packageTag or spec.listingId or defName), { public = true })
      Spring.SetUnitRulesParam(uid, "va_playable_proxy", 1, { public = true })
      Spring.SetUnitRulesParam(uid, "va_delivery_mode", mode, { public = true })
      if hfrac < 0.99 and Spring.SetUnitHealth and Spring.GetUnitHealth then
        local _, maxH = Spring.GetUnitHealth(uid)
        if maxH and maxH > 0 then pcall(Spring.SetUnitHealth, uid, maxH * hfrac) end
      end
      -- Delivered units wait where they land: only named heroes act on their own.
    end
  end
  Spring.Echo("VA_DELIVERY_ARRIVE listing=" .. tostring(spec.listingId or "")
    .. " mode=" .. mode
    .. " source=" .. tostring(spec.sourceLabel or spec.sourceMapId or "")
    .. " count=" .. tostring(spawned)
    .. " from=" .. tostring(math.floor(x)) .. "," .. tostring(math.floor(z)))
  if spawned > 0 and SendToUnsynced then
    local bark = tostring(spec.label or spec.listingId or "shipment")
    if mode == "pawn_launcher" then
      bark = "Pawn launcher impact — " .. tostring(spawned) .. " near infil"
    elseif tostring(spec.sourceMapId or "") == "all_that_simmers" then
      bark = "Geo-vent stream clearing the gaps — " .. bark
    else
      bark = "Column clearing the rim from " .. tostring(spec.sourceLabel or "the web") .. " — " .. bark
    end
    SendToUnsynced("VERDANCE_BEAT", "wave_warning", x, Spring.GetGroundHeight(x, z) or 0, z, bark)
  end
  return spawned
end

-- list: what is in transit (default: the seed's; a hot drop brings its own, see VA_HOT_drop).
function VA_LOGISTICS.armPendingDeliveries(list)
  VA_LOGISTICS.pending = {}
  local bag = mission and mission.commerce or {}
  list = list or bag.pendingDeliveries or mission.pendingDeliveries or {}
  local frame = Spring.GetGameFrame() or 0
  for _, raw in ipairs(list) do
    if type(raw) == "table" and tostring(raw.status or "in_transit") == "in_transit" then
      local eta = math.max(15, math.floor(tonumber(raw.etaSeconds) or 90))
      local rec = {
        id = tostring(raw.id or (#VA_LOGISTICS.pending + 1)),
        listingId = raw.listingId,
        label = raw.label or raw.listingId,
        unitDef = raw.unitDef,
        count = tonumber(raw.count) or 1,
        mode = raw.mode or "map_web",
        sourceMapId = raw.sourceMapId,
        sourceLabel = raw.sourceLabel,
        packageTag = raw.packageTag or raw.listingId,
        healthFracMin = raw.healthFracMin,
        healthFracMax = raw.healthFracMax,
        dueFrame = frame + eta * 30,
        arrived = false,
        warned = false,
      }
      VA_LOGISTICS.pending[#VA_LOGISTICS.pending + 1] = rec
      Spring.Echo("VA_DELIVERY_ARMED listing=" .. tostring(rec.listingId)
        .. " mode=" .. tostring(rec.mode)
        .. " etaSec=" .. tostring(eta)
        .. " source=" .. tostring(rec.sourceLabel or ""))
    end
  end
  VA_LOGISTICS.publishInboundHud()
end

-- t=0 commerce bag (pawn-launcher packs, constructors, fabs, nanos) — mission.commerce.deploy.
-- Deferred map-web packs stay on pendingDeliveries; this only loads what already paid at the hub.
-- RULE (one owner): this is the ONLY spawner of the commerce deploy bag. The layout force
-- in playableSetup carries preview copies of the same items (stamped commerceDeploy=true by
-- scripts/build_next_mission_v1.ps1 Add-CommerceDeployToKit) and spawnPlayableSetup skips
-- them via VA_CREW_isCommerceKitSpec. Spawning here AND there is the double-spawn bug.
-- list: the kit (default: the seed's; a hot drop brings what was bought up to the drop).
function VA_LOGISTICS.spawnCommerceDeployKit(list)
  if VA_LOGISTICS.deployKitSpawned then
    Spring.Echo("VA_COMMERCE_DEPLOY already_spawned")
    return 0
  end
  VA_LOGISTICS.deployKitSpawned = true
  local bag = mission and mission.commerce or {}
  list = list or bag.deploy or {}
  if type(list) ~= "table" or #list == 0 then
    Spring.Echo("VA_COMMERCE_DEPLOY empty")
    return 0
  end
  if not playerTeamID then
    Spring.Echo("VA_COMMERCE_DEPLOY skip no_player_team")
    return 0
  end
  local baseX, baseZ = VA_LOGISTICS.infilAnchor()
  local total = 0
  for i, raw in ipairs(list) do
    if type(raw) == "table" then
      local kind = tostring(raw.kind or "package")
      local lid = tostring(raw.listingId or raw.packageTag or ("kit_" .. tostring(i)))
      if kind == "package" or kind == "loan_package" or kind == "purchase_package" then
        local n = VA_LOGISTICS.spawnPackageDelivery({
          listingId = lid,
          label = raw.label or lid,
          unitDef = raw.unitDef,
          count = tonumber(raw.count) or 1,
          mode = "pawn_launcher",
          packageTag = raw.packageTag or lid,
          healthFracMin = raw.healthFracMin or raw.healthFrac,
          healthFracMax = raw.healthFracMax or raw.healthFrac,
        })
        total = total + n
      elseif kind == "constructor" then
        local defName = tostring(raw.unitDef or "")
        local count = math.max(1, math.floor(tonumber(raw.count) or 1))
        if defName ~= "" and UnitDefNames and UnitDefNames[defName] then
          local n = spawnUnitSpec({
            unitDefName = defName,
            count = count,
            dx = 90 + (i % 3) * 70,
            dz = -160 - math.floor((i - 1) / 3) * 70,
            spacing = 85,
            packageTag = lid,
          }, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
          total = total + n
          -- hired for this drop: the manifest keeps them out of the reserve
          for _, uid in ipairs(Spring.GetTeamUnits(playerTeamID) or {}) do
            if tostring(Spring.GetUnitRulesParam(uid, "va_package_tag") or "") == lid then
              Spring.SetUnitRulesParam(uid, "va_delivery_mode", "kit", { public = true })
            end
          end
          Spring.Echo("VA_COMMERCE_DEPLOY constructor=" .. defName .. " n=" .. tostring(n) .. " listing=" .. lid)
        else
          Spring.Echo("VA_COMMERCE_DEPLOY_FAIL constructor_def=" .. defName)
        end
      elseif kind == "unit_printer" then
        local factoryDef = tostring(raw.factoryDef or raw.unitDef or "")
        local product = tostring(raw.product or "corak")
        local seed = math.max(0, math.floor(tonumber(raw.seedCount) or 0))
        if factoryDef ~= "" and UnitDefNames and UnitDefNames[factoryDef] then
          local n = spawnUnitSpec({
            unitDefName = factoryDef,
            count = 1,
            dx = 140 + (i % 2) * 110,
            dz = -220 - math.floor((i - 1) / 2) * 100,
            spacing = 120,
            packageTag = lid,
            unitPrinter = true,
            printerProduct = product,
            printerMetalIncome = tonumber(raw.metalIncome) or 8,
            printerEnergyIncome = tonumber(raw.energyIncome) or 40,
          }, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
          total = total + n
          if seed > 0 and product ~= "" and UnitDefNames[product] then
            total = total + spawnUnitSpec({
              unitDefName = product,
              count = seed,
              dx = 200 + (i % 2) * 90,
              dz = -280,
              spacing = 70,
              packageTag = lid .. "_seed",
            }, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
          end
          Spring.Echo("VA_COMMERCE_DEPLOY fab=" .. factoryDef .. " product=" .. product
            .. " seed=" .. tostring(seed) .. " listing=" .. lid)
        else
          Spring.Echo("VA_COMMERCE_DEPLOY_FAIL fab_def=" .. factoryDef)
        end
      elseif kind == "nano" then
        local defName = tostring(raw.unitDef or "cornanotc")
        local count = math.max(1, math.floor(tonumber(raw.count) or 1))
        if UnitDefNames and UnitDefNames[defName] then
          local n = spawnUnitSpec({
            unitDefName = defName,
            count = count,
            dx = 60 + i * 55,
            dz = -240,
            spacing = 70,
            packageTag = lid,
          }, playerTeamID, baseX, baseZ, 0, 0, {}, { role = "player_crew" })
          total = total + n
          -- hired for this drop: the manifest keeps them out of the reserve
          for _, uid in ipairs(Spring.GetTeamUnits(playerTeamID) or {}) do
            if tostring(Spring.GetUnitRulesParam(uid, "va_package_tag") or "") == lid then
              Spring.SetUnitRulesParam(uid, "va_delivery_mode", "kit", { public = true })
            end
          end
        end
      else
        Spring.Echo("VA_COMMERCE_DEPLOY_SKIP kind=" .. kind .. " listing=" .. lid)
      end
    end
  end
  Spring.Echo("VA_COMMERCE_DEPLOY spawned=" .. tostring(total) .. " listings=" .. tostring(#list))
  return total
end

function VA_LOGISTICS.tickPendingDeliveries(frame)
  if #VA_LOGISTICS.pending == 0 then return end
  local dirty = false
  for _, d in ipairs(VA_LOGISTICS.pending) do
    if d and not d.arrived then
      local left = (d.dueFrame or 0) - frame
      if not d.warned and left <= 30 * 30 and left > 0 then
        d.warned = true
        if SendToUnsynced then
          SendToUnsynced("VERDANCE_BEAT", "wave_warning", 0, 0, 0,
            "Inbound " .. tostring(d.label or "shipment") .. " · " .. tostring(math.floor(left / 30)) .. "s")
        end
      end
      if frame >= (d.dueFrame or 0) then
        d.arrived = true
        VA_LOGISTICS.spawnPackageDelivery(d)
        dirty = true
      end
    end
  end
  if dirty or (frame % 30 == 0) then
    VA_LOGISTICS.publishInboundHud()
  end
end

function VA_LOGISTICS.spawnBruteCrashFromEdge(count)
  return VA_LOGISTICS.spawnPackageDelivery({
    listingId = "crash_of_brutes",
    label = "Crash of Brutes",
    unitDef = "corraid",
    count = count or 4,
    mode = "map_web",
    sourceMapId = "eye_of_horus",
    sourceLabel = "Eye of Horus",
    packageTag = "crash_of_brutes",
    healthFracMin = 0.9,
    healthFracMax = 1.0,
  })
end

-- Compat aliases for existing call sites (gadget-env globals, not main-chunk locals).
armPendingDeliveries = function(...) return VA_LOGISTICS.armPendingDeliveries(...) end
tickPendingDeliveries = function(...) return VA_LOGISTICS.tickPendingDeliveries(...) end
spawnBruteCrashFromEdge = function(...) return VA_LOGISTICS.spawnBruteCrashFromEdge(...) end
spawnCommerceDeployKit = function(...) return VA_LOGISTICS.spawnCommerceDeployKit(...) end
