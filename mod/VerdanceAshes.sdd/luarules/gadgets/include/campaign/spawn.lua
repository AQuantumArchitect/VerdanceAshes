-- campaign/spawn.lua: placing units: dry landing, standable ground, spawnOneUnit / spawnUnitSpec
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: spawnUnitSpec, vaDryClaims, vaStandable
-- Uses: hero_spawn, heroes, mentors, mission_data, objectives, state, units, waterline

local DECOY_FOR_REAL_COM = {
  armcom = "armdecom",
  corcom = "cordecom",
  legcom = "legdecom",
}

-- Sea level is 0. A front-band slide can plant the company in the lake;
-- land units there drown. Global on purpose (main chunk is at the local cap).
vaDryClaims = nil
function vaDryLanding(x, z)
  local mapX = Game.mapSizeX or 0
  local mapZ = Game.mapSizeZ or 0
  local function ground(px, pz)
    if px < 64 or pz < 64 or (mapX > 0 and px > mapX - 64) or (mapZ > 0 and pz > mapZ - 64) then
      return -9999
    end
    return (Spring.GetGroundHeight and Spring.GetGroundHeight(px, pz)) or -9999
  end
  local sinkPending = 0
  if (tonumber(vaWaterApplied) or 0) < 0.05 and vaWaterElevation then
    local hydro = mission and mission.hydrology
    local level = hydro and tonumber(hydro.level) or 0
    if level > 0 then
      sinkPending = math.max(0, (vaWaterElevation(level) or 0) - (vaWaterElevation(0) or 0))
    end
  end
  local need = 10 + sinkPending
  local function cell(px, pz)
    return tostring(math.floor(px / 80)) .. ":" .. tostring(math.floor(pz / 80))
  end
  vaDryClaims = vaDryClaims or {}
  if ground(x, z) >= need and not vaDryClaims[cell(x, z)] then
    vaDryClaims[cell(x, z)] = true
    return x, z
  end
  for radius = 90, 3600, 90 do
    for i = 0, 19 do
      local ang = (i / 20) * math.pi * 2
      local px = x + math.cos(ang) * radius
      local pz = z + math.sin(ang) * radius
      local y = ground(px, pz)
      if y >= need and not vaDryClaims[cell(px, pz)] then
        vaDryClaims[cell(px, pz)] = true
        return px, pz
      end
    end
  end
  vaDryClaims[cell(x, z)] = true
  return x, z
end

-- The nearest ground a unit can really stand on: a building where it can be built (the hero bays
-- and turrets failed CreateUnit on rough ground), anything that moves where it can drive, with
-- room to drive out (the Consul's wreck landed on a hillside nobody could reach). With reachX/Z,
-- a mobile unit's spot must also have a path to that point (the pad), so it is not a ledge cut off
-- by cliffs. Global on purpose (the main chunk is at the local cap). nil when nothing fits.
function vaPathReaches(ud, x, z, tx, tz)
  if not (Spring.RequestPath and ud.moveDef and ud.moveDef.name) then return true end
  -- Before the first sim frame the path system is not up: RequestPath at GameStart (f=-1) is an
  -- engine access violation (autopilot run 2026-10-24, field-recruit wreck seeding). Standing
  -- ground is enough then.
  if (Spring.GetGameFrame and Spring.GetGameFrame() or 0) < 1 then return true end
  local path = Spring.RequestPath(ud.moveDef.name, x, Spring.GetGroundHeight(x, z), z, tx, Spring.GetGroundHeight(tx, tz), tz, 64)
  if not path then return false end
  local pts = path.GetPathWayPoints and path:GetPathWayPoints() or nil
  local last = pts and pts[#pts]
  if not last then return true end
  local dx, dz = (last[1] or x) - tx, (last[3] or z) - tz
  return dx * dx + dz * dz <= 400 * 400
end

function vaStandable(defName, x, z, facing, reachX, reachZ)
  local ud = UnitDefNames and UnitDefNames[defName]
  if not ud or not x or not z then return nil end
  if ud.canFly then return x, z end
  local mapX, mapZ = Game.mapSizeX or 0, Game.mapSizeZ or 0
  local building = ud.isBuilding or ud.isFactory or (ud.speed or 0) == 0
  local pathChecks = 0
  local function fits(px, pz)
    if px < 96 or pz < 96 or px > mapX - 96 or pz > mapZ - 96 then return nil end
    local py = Spring.GetGroundHeight(px, pz)
    if building then
      local bx, by, bz = px, py, pz
      if Spring.Pos2BuildPos then bx, by, bz = Spring.Pos2BuildPos(ud.id, px, py, pz, facing or 0) end
      if Spring.TestBuildOrder and (Spring.TestBuildOrder(ud.id, bx, by, bz, facing or 0) or 0) > 0 then return bx, bz end
      return nil
    end
    if not Spring.TestMoveOrder then return px, pz end
    -- the spot and a ring around it: a passable pixel on a cliff face is not ground
    for _, o in ipairs({ { 0, 0 }, { 56, 0 }, { -56, 0 }, { 0, 56 }, { 0, -56 } }) do
      local qx, qz = px + o[1], pz + o[2]
      if not Spring.TestMoveOrder(ud.id, qx, Spring.GetGroundHeight(qx, qz), qz, 0, 0, 0, true, true, true) then return nil end
    end
    if reachX and reachZ then
      pathChecks = pathChecks + 1
      -- a budget of path queries; past it, standing ground is enough
      if pathChecks <= 24 and not vaPathReaches(ud, px, pz, reachX, reachZ) then return nil end
    end
    return px, pz
  end
  local fx, fz = fits(x, z)
  if fx then return fx, fz end
  for radius = 48, 960, 48 do
    local n = math.max(12, math.floor(radius / 24))
    for i = 0, n - 1 do
      local ang = (i / n) * math.pi * 2
      fx, fz = fits(x + math.cos(ang) * radius, z + math.sin(ang) * radius)
      if fx then return fx, fz end
    end
  end
  return nil
end

local function spawnOneUnit(defName, x, z, facing, teamID, spec, force, hpPct)
  -- Occupation shells plant decoy farmers, not real commanders. Remap any
  -- enemy real-com spawn (all maps) so a stale recipe / AI start unit cannot
  -- introduce a 700-AoE commanderExplosion + 1250-metal wreck into a raid.
  if teamID ~= playerTeamID then
    local decoy = DECOY_FOR_REAL_COM[tostring(defName)]
    if decoy and UnitDefNames and UnitDefNames[decoy] then
      defName = decoy
    end
  end
  do
    local ud = UnitDefNames and UnitDefNames[defName]
    -- A baked field (Koom's war) already stands on ground the sim used: placed exactly.
    local skipDry = (ud and (ud.canFly or ud.floatOnWater)) or (spec and spec.exact)
    if not skipDry then
      local nx, nz = vaDryLanding(x, z)
      if math.abs((nx or x) - x) > 40 or math.abs((nz or z) - z) > 40 then
        vaDryMoves = (vaDryMoves or 0) + 1
        if vaDryMoves <= 8 then
          Spring.Echo(string.format(
            "VA_DRY_LANDING def=%s from=%.0f,%.0f to=%.0f,%.0f y=%.0f",
            tostring(defName), x, z, nx or x, nz or z,
            (Spring.GetGroundHeight and Spring.GetGroundHeight(nx or x, nz or z)) or 0))
        end
      end
      x, z = nx or x, nz or z
    end
  end
  if teamID == playerTeamID then
    local sx, sz = vaStandable(defName, x, z, facing)
    if sx then x, z = sx, sz end
  end
  local y = Spring.GetGroundHeight(x, z)
  local unitID = Spring.CreateUnit(defName, x, y, z, facing, teamID)
  if unitID then
    Spring.SetUnitRulesParam(unitID, "va_playable_proxy", 1, { public = true })
    if hpPct and hpPct < 100 and Spring.GetUnitHealth and Spring.SetUnitHealth then
      local _, maxH = Spring.GetUnitHealth(unitID)
      if maxH then pcall(Spring.SetUnitHealth, unitID, math.max(1, maxH * hpPct / 100)) end
    end
    if defName == "va_queen_nest" and Spring.SetUnitPieceMatrix then
      -- the queen's nest is bigger than a roost: scale its root piece (the unit def widens the box)
      local s = 1.6
      pcall(Spring.SetUnitPieceMatrix, unitID, 1, { s, 0, 0, 0, 0, s, 0, 0, 0, 0, s, 0, 0, 0, 0, 1 })
    end
    -- Pack mates: stamp leader; mentors also mint XP floor + field aura.
    if teamID == playerTeamID and not (spec and (spec.heroId or spec.hero)) then
      local pkg = spec and tostring(spec.packageTag or "") or ""
      local lead = nil
      if pkg ~= "" then
        lead = pkg:match("^crew_pack_(.+)$")
          or pkg:match("^crew_escort_([^_]+)")
          or pkg:match("^crew_mint_(.+)$")
          or pkg:match("^crew_([^_]+)$")
      end
      if lead and packMentors[lead] then
        stampMentorSubordinate(unitID, lead)
      elseif lead and heroes[lead] then
        Spring.SetUnitRulesParam(unitID, "va_pack_leader", lead, { public = true })
        Spring.SetUnitRulesParam(unitID, "va_pack_id", lead, { public = true })
        Spring.SetUnitRulesParam(unitID, "va_pack_role", "mate", { public = true })
        local rec = heroes[lead]
        if rec and rec.field and HeroTags and HeroTags.applyFieldToUnit then
          local okMate, errMate = pcall(HeroTags.applyFieldToUnit, unitID, rec.field, rec)
          if not okMate then
            Spring.Echo("VA_PACK_FIELD_FAIL lead=" .. tostring(lead)
              .. " unit=" .. tostring(unitID) .. " err=" .. tostring(errMate))
          end
        end
        if GG and GG.VA_PackOverlayStamp then
          pcall(GG.VA_PackOverlayStamp, unitID, lead, "mate")
        end
      elseif isWheelieDef(defName) and packMentors["spoke"] then
        stampMentorSubordinate(unitID, "spoke")
      end
    end
    if force and force.role then
      Spring.SetUnitRulesParam(unitID, "va_force_role", tostring(force.role), { public = true })
      if force.role == "objective_target" then
        local defID = Spring.GetUnitDefID(unitID)
        if isStructure(defID) then
          local forceId = tostring(force.id or "objective")
          objectiveTargets[unitID] = forceId
          objectiveTargetCount = objectiveTargetCount + 1
        end
      elseif force.role == "objective_secondary" then
        -- Drop 4: secondary marks keep their own ledger, never the primary
        -- pool (a capture mission's clear fraction must not count them).
        local defID = Spring.GetUnitDefID(unitID)
        if isStructure(defID) then
          local sid = tostring(force.secondaryId or force.id or "secondary")
          MarksLib.bindTarget(marks, unitID, sid, {
            required = (force.required == true),
            kind = MarksLib.KIND.structure,
            label = sid,
          })
        end
      end
    end
    -- Patrols actually patrol: a waypoint list (or the legacy single point)
    -- becomes a CMD.PATROL loop from the spawn position, so garrisons sweep
    -- their ground instead of fight-moving once and clumping.
    if spec and type(spec.patrol) == "table" and CMD and CMD.PATROL then
      local opts = {}
      for _, wp in ipairs(spec.patrol) do
        local px = normalizedToElmos(wp.x, Game.mapSizeX or 0)
        local pz = normalizedToElmos(wp.z, Game.mapSizeZ or 0)
        Spring.GiveOrderToUnit(unitID, CMD.PATROL, { px, Spring.GetGroundHeight(px, pz), pz }, opts)
        opts = { "shift" }
      end
    elseif spec and spec.patrolX and spec.patrolZ and CMD and CMD.PATROL then
      local px = normalizedToElmos(spec.patrolX, Game.mapSizeX or 0)
      local pz = normalizedToElmos(spec.patrolZ, Game.mapSizeZ or 0)
      Spring.GiveOrderToUnit(unitID, CMD.PATROL, { px, Spring.GetGroundHeight(px, pz), pz }, {})
    end
    -- Named heroes (and the legacy single-hero flag): the persistent warband
    -- leaders, not commander suits - tougher and blooded on the field.
    if spec and (spec.heroId or spec.hero) then
      registerHeroSpawn(unitID, spec)
      -- A builder hero's experience is craft: Ketha at full XP rezzes and builds faster and from
      -- farther (game_verdance_craft_xp.lua caps it). Combat veterancy does nothing for a rezbot.
      local hud = UnitDefNames[defName]
      local heroXp = tonumber(spec.heroXp) or 0
      if hud and heroXp > 0 and ((tonumber(hud.buildSpeed) or 0) > 0 or hud.canResurrect) then
        Spring.SetUnitRulesParam(unitID, "va_craft_xp", heroXp, { public = true })
        if GG and GG.VA_CraftRefresh then pcall(GG.VA_CraftRefresh, unitID) end
      end
    elseif teamID == playerTeamID and spec then
      -- Non-hero player units: restore banked combat / craft XP between rounds.
      -- Majority retain: campaign bakes keepFrac into spec.xp already; still
      -- floor against mission.cadreXp so green packs do not wipe veterans.
      local seedXp = tonumber(spec.xp or spec.heroXp or 0) or 0
      if seedXp <= 0 and mission and type(mission.cadreXp) == "table" then
        local bag = mission.cadreXp[defName]
        if type(bag) == "table" then
          seedXp = tonumber(bag.xp or bag.avgXp or bag.peakXp) or 0
        elseif type(bag) == "number" then
          seedXp = bag
        end
      end
      if seedXp > 0 and Spring.SetUnitExperience then
        pcall(Spring.SetUnitExperience, unitID, seedXp)
        Spring.SetUnitRulesParam(unitID, "va_carry_xp", seedXp, { public = true })
        if GG and GG.VA_VetRefresh then pcall(GG.VA_VetRefresh, unitID) end
      end
      local craftSeed = tonumber(spec.craftXp or 0) or 0
      if craftSeed <= 0 and mission and type(mission.cadreXp) == "table" then
        local bag = mission.cadreXp[defName]
        if type(bag) == "table" then
          craftSeed = tonumber(bag.craftXp or bag.avgCraftXp or bag.peakCraftXp) or 0
        end
      end
      if craftSeed > 0 then
        Spring.SetUnitRulesParam(unitID, "va_craft_xp", craftSeed, { public = true })
        if GG and GG.VA_CraftRefresh then
          pcall(GG.VA_CraftRefresh, unitID)
        end
      end
    end
    -- WO-043: loan packs / smoking thugs spawn damaged so repair bots eat early downtime.
    if spec and (spec.healthFrac or spec.healthFracMin or spec.healthFracMax or spec.loanPackage) then
      local hmin = tonumber(spec.healthFracMin)
      local hmax = tonumber(spec.healthFracMax)
      local hfrac = tonumber(spec.healthFrac)
      if not hfrac then
        if hmin and hmax then
          hfrac = (hmin + hmax) * 0.5
        elseif hmin then
          hfrac = hmin
        else
          hfrac = 0.45
        end
      end
      if hfrac > 1 then hfrac = 1 end
      if hfrac < 0.05 then hfrac = 0.05 end
      if Spring.GetUnitHealth and Spring.SetUnitHealth then
        local cur, maxH = Spring.GetUnitHealth(unitID)
        if maxH and maxH > 0 then
          pcall(Spring.SetUnitHealth, unitID, maxH * hfrac)
        end
      end
      Spring.SetUnitRulesParam(unitID, "va_health_frac", hfrac, { public = true })
      if spec.loanPackage == true or spec.loanPackage == 1 then
        Spring.SetUnitRulesParam(unitID, "va_loan_package", 1, { public = true })
      end
      if spec.packageTag then
        Spring.SetUnitRulesParam(unitID, "va_package_tag", tostring(spec.packageTag), { public = true })
        stampPadToothIfNeeded(unitID, spec.packageTag)
        if GG and GG.VA_PackOverlayStamp then
          local pid = tostring(spec.packageTag):match("crew_pack_(.+)")
            or tostring(spec.packageTag):match("crew_escort_([^_]+)")
            or tostring(spec.packageTag):match("crew_([^_]+)")
          if pid then GG.VA_PackOverlayStamp(unitID, pid, "mate") end
        end
      end
      Spring.Echo("VA_DAMAGED_SPAWN unit=" .. tostring(unitID) .. " frac=" .. tostring(hfrac)
        .. " package=" .. tostring(spec.packageTag or ""))
    elseif spec and spec.packageTag then
      Spring.SetUnitRulesParam(unitID, "va_package_tag", tostring(spec.packageTag), { public = true })
      stampPadToothIfNeeded(unitID, spec.packageTag)
      if GG and GG.VA_PackOverlayStamp then
        local pid = tostring(spec.packageTag):match("crew_pack_(.+)")
          or tostring(spec.packageTag):match("crew_escort_([^_]+)")
          or tostring(spec.packageTag):match("crew_([^_]+)")
        if pid then GG.VA_PackOverlayStamp(unitID, pid, "mate") end
      end
    end
    -- WO-033 unit printer: lock factory to a single product and trickle resources.
    if spec and (spec.unitPrinter == true or spec.unitPrinter == 1) then
      local product = tostring(spec.printerProduct or "leggob")
      Spring.SetUnitRulesParam(unitID, "va_unit_printer", 1, { public = true })
      Spring.SetUnitRulesParam(unitID, "va_printer_product", product, { public = true })
      if Spring.EditUnitCmdDesc and Spring.GetUnitCmdDescs and Spring.RemoveUnitCmdDesc then
        local descs = Spring.GetUnitCmdDescs(unitID) or {}
        for i = #descs, 1, -1 do
          local c = descs[i]
          if c and c.id and c.id < 0 then
            local buildDefID = -c.id
            local bud = UnitDefs[buildDefID]
            if not bud or bud.name ~= product then
              pcall(Spring.RemoveUnitCmdDesc, unitID, i)
            end
          end
        end
      end
      local mInc = tonumber(spec.printerMetalIncome) or 8
      local eInc = tonumber(spec.printerEnergyIncome) or 40
      if mInc > 0 then pcall(Spring.SetTeamResource, teamID, "metal", (Spring.GetTeamResources(teamID, "metal") or 0) + 200) end
      if eInc > 0 then pcall(Spring.SetTeamResource, teamID, "energy", (Spring.GetTeamResources(teamID, "energy") or 0) + 400) end
      -- Ongoing trickle via GameFrame table.
      printerUnits = printerUnits or {}
      printerUnits[unitID] = { metal = mInc / 30, energy = eInc / 30, team = teamID }
      Spring.Echo("VA_UNIT_PRINTER unit=" .. tostring(unitID) .. " product=" .. product)
    end
    return 1
  end
  return 0
end

function spawnUnitSpec(spec, teamID, baseX, baseZ, groupX, groupZ, claimedMetalSpots, force)
  if type(spec) ~= "table" then return 0 end
  local defName = spec.unitDefName or spec.def or spec[1]
  if not defName or not UnitDefNames[defName] then
    Spring.Echo("VA_PLAYABLE_MISSING_UNIT " .. tostring(defName))
    return 0
  end
  local count = tonumber(spec.count or 1) or 1
  local spacing = tonumber(spec.spacing or 90) or 90
  local spawned = 0
  local dx = tonumber(spec.dx or spec.x or 0) or 0
  local dz = tonumber(spec.dz or spec.z or 0) or 0
  local facing = tonumber(spec.facing or 0) or 0
  local anchorX = baseX + groupX + dx
  local anchorZ = baseZ + groupZ + dz

  if type(spec.at) == "table" then
    -- Flat [x, z, facing, hp%] per unit, x and z normalized (the baked Koom war).
    for i = 1, #spec.at - 3, 4 do
      local ux = normalizedToElmos(spec.at[i], Game.mapSizeX or 0)
      local uz = normalizedToElmos(spec.at[i + 1], Game.mapSizeZ or 0)
      spawned = spawned + spawnOneUnit(defName, ux, uz, math.floor(tonumber(spec.at[i + 2]) or 0), teamID, spec, force,
        tonumber(spec.at[i + 3]))
    end
    return spawned
  end

  if spec.atMetalSpots or spec.nearestMetalSpots then
    for i = 1, count do
      local spot = nearestOpenMetalSpot(anchorX, anchorZ, claimedMetalSpots)
      if not spot then
        Spring.Echo("VA_PLAYABLE_NO_METAL_SPOT unitDef=" .. tostring(defName) .. " anchorX=" .. tostring(math.floor(anchorX)) .. " anchorZ=" .. tostring(math.floor(anchorZ)))
        break
      end
      claimedMetalSpots[metalSpotKey(spot)] = true
      spawned = spawned + spawnOneUnit(defName, spot.x, spot.z, facing, teamID, spec, force)
    end
    return spawned
  end

  local formation = tostring(spec.formation or "")
  if formation == "triangle" and count >= 3 then
    -- Equilateral-ish triangle: point toward +Z, base behind.
    local tri = {
      { 0, 0 },
      { -spacing, spacing },
      { spacing, spacing },
    }
    for i = 1, count do
      local off = tri[((i - 1) % 3) + 1]
      local ring = math.floor((i - 1) / 3)
      local x = anchorX + off[1] * (1 + ring * 0.85)
      local z = anchorZ + off[2] * (1 + ring * 0.85)
      spawned = spawned + spawnOneUnit(defName, x, z, facing, teamID, spec, force)
    end
    return spawned
  end
  if formation == "ring" and count > 1 then
    local radius = spacing
    for i = 1, count do
      local ang = ((i - 1) / count) * math.pi * 2
      local x = anchorX + math.cos(ang) * radius
      local z = anchorZ + math.sin(ang) * radius
      spawned = spawned + spawnOneUnit(defName, x, z, facing, teamID, spec, force)
    end
    return spawned
  end
  for i = 1, count do
    local row = math.floor((i - 1) / 4)
    local col = (i - 1) % 4
    local x = anchorX + ((col - 1.5) * spacing)
    local z = anchorZ + (row * spacing)
    spawned = spawned + spawnOneUnit(defName, x, z, facing, teamID, spec, force)
  end
  return spawned
end
