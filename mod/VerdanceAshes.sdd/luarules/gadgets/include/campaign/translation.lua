-- campaign/translation.lua: the translation matrix packet
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: logAndBroadcastTranslation
-- Uses: result, state, telemetry, waterline

-- Sum metrics across all teams in a zone bucket (total military presence)
local function sumZoneMetrics(zoneEntry)
  local av, bp, dp = 0, 0, 0
  if not zoneEntry or not zoneEntry.teams then return av, bp, dp end
  for _, bucket in pairs(zoneEntry.teams) do
    av = av + (bucket.metrics.armyValue or 0)
    bp = bp + (bucket.metrics.buildPower or 0)
    dp = dp + (bucket.metrics.defensiveValue or 0)
  end
  return av, bp, dp
end

local function generateTranslationPacket(zoneBuckets)
  if not zoneMap or type(zoneMap.zones) ~= "table" or #zoneMap.zones == 0 then
    Spring.Echo("VA_TRANSLATION_SKIP no zone map loaded")
    return nil
  end

  local N = #zoneMap.zones
  -- Spring.GetMapWaterLevel does NOT exist on this engine; the old guarded call
  -- silently returned 0, which pinned the hydrology anchor at zero forever and
  -- made the whole last row and column of the matrix carry no information.
  -- The waterline is campaign state now, and it is measured per zone.
  local rho_H = math.max(0, math.min(1, tonumber(vaWaterLevel) or 0))
  local waterLevel = vaWaterElevation(rho_H) or 0

  -- Build flat zone list from real data
  local zones = {}
  for i, zone in ipairs(zoneMap.zones) do
    local entry = zoneBuckets[zone.zoneId] or { zone = zone, teams = {} }
    local av, bp, dp = sumZoneMetrics(entry)
    zones[i] = {
      id      = i,
      zoneId  = zone.zoneId,
      name    = zone.label or zone.zoneId,
      type    = getZoneHydroType(zone),
      av      = av,
      bp      = bp,
      dp      = dp,
    }
  end

  -- Instantiate (N+1) x (N+1) Hermitian matrix
  local matrix = {}
  for i = 1, N + 1 do
    matrix[i] = {}
    for j = 1, N + 1 do matrix[i][j] = 0 end
  end

  -- Step 1: Diagonals (zone density)
  for k = 1, N do
    local z = zones[k]
    matrix[k][k] = math.tanh((z.av + z.bp + z.dp) / 5735.0)
  end
  matrix[N+1][N+1] = rho_H  -- Environmental hydrology anchor

  -- Step 2: Off-diagonals -- entanglement between zones that actually TOUCH.
  --
  -- This used to couple every pair by how similar their army values were, which
  -- made two empty zones in opposite corners read as maximally entangled, and
  -- grew as N^2 with the zone count. A coupling is now a real front: shared
  -- border, forces on BOTH sides, plus the units measured crossing it.
  local geo = vaZoneAdjacency and vaZoneAdjacency()
  local shared = geo and geo.shared or {}
  local perimeter = geo and geo.perimeter or {}
  local flow = vaZoneFlow or {}
  local flowPeak = 1
  for _, count in pairs(flow) do
    if count > flowPeak then flowPeak = count end
  end
  for i = 1, N do
    for j = i + 1, N do
      local a, b = zones[i].zoneId, zones[j].zoneId
      local key = (a < b) and (a .. "|" .. b) or (b .. "|" .. a)
      local border = shared[key]
      if border and border > 0 then
        local edge = math.min(perimeter[a] or border, perimeter[b] or border)
        local borderShare = math.min(1.0, border / math.max(1, edge))
        -- A front needs two sides: the weaker presence sets the coupling.
        local weaker = math.min(zones[i].av, zones[j].av)
        local stronger = math.max(zones[i].av, zones[j].av, 1.0)
        local pressure = math.tanh(weaker / 2000.0) * (weaker / stronger)
        local crossing = (flow[key] or 0) / flowPeak
        local c = VA_TRANSLATION.BASE_COUPLING * borderShare * (0.65 * pressure + 0.35 * crossing)
        matrix[i][j] = c
        matrix[j][i] = c
      end
    end
    -- Step 3: Hydrological coupling -- how much of this zone the current
    -- waterline actually takes, measured from its own flood curve.
    local wet = vaZoneSubmerged(zoneMap.zones[i], rho_H)
    local hc = VA_TRANSLATION.BASE_HYDRO_COUPLING * wet
    matrix[i][N+1] = hc
    matrix[N+1][i] = hc
  end

  -- Build canonical packet
  local packet = {
    protocol = "VERDANCE_TRANSLATION_V1",
    frame    = Spring.GetGameFrame(),
    global   = { hydrology = { level = waterLevel, saturation = tonumber(string.format("%.3f", rho_H)) } },
    nodes    = {},
    entanglements = {},
    factoids = {},
  }

  for i = 1, N do
    local z = zones[i]
    table.insert(packet.nodes, {
      id           = z.id,
      zoneId       = z.zoneId,
      name         = z.name,
      type         = z.type,
      raw          = { av = z.av, bp = z.bp, dp = z.dp },
      density      = tonumber(string.format("%.3f", matrix[i][i])),
      hydroCoupling= tonumber(string.format("%.3f", matrix[i][N+1])),
    })
  end

  for i = 1, N do
    for j = i + 1, N do
      local coupling = matrix[i][j]
      if coupling > VA_TRANSLATION.ENTANGLEMENT_THRESHOLD then
        table.insert(packet.entanglements, {
          zoneIds  = { zones[i].zoneId, zones[j].zoneId },
          names    = { zones[i].name, zones[j].name },
          coupling = tonumber(string.format("%.3f", coupling)),
        })
      end
    end
  end

  for _, node in ipairs(packet.nodes) do
    if node.type == "low-flood" and node.hydroCoupling > VA_TRANSLATION.HYDRO_HAZARD_THRESHOLD then
      table.insert(packet.factoids, {
        type    = "HAZARD",
        zoneId  = node.zoneId,
        message = node.name .. " is critically exposed to current hydrology levels.",
      })
    end
    if node.density > VA_TRANSLATION.DENSITY_HOTSPOT then
      table.insert(packet.factoids, {
        type    = "HOTSPOT",
        zoneId  = node.zoneId,
        message = node.name .. " has reached critical military density.",
      })
    end
  end

  return packet
end

-- Minimal table -> JSON serializer for the canonical packet
local function serializeTranslationPacket(p)
  if not p then return nil end

  local nodeParts = {}
  for _, n in ipairs(p.nodes) do
    table.insert(nodeParts, string.format(
      '{"id":%d,"zoneId":%s,"name":%s,"type":%s,"raw":{"av":%.0f,"bp":%.0f,"dp":%.0f},"density":%.3f,"hydroCoupling":%.3f}',
      n.id, jstr(n.zoneId), jstr(n.name), jstr(n.type), n.raw.av, n.raw.bp, n.raw.dp, n.density, n.hydroCoupling
    ))
  end

  local entParts = {}
  for _, e in ipairs(p.entanglements) do
    table.insert(entParts, string.format(
      '{"zoneIds":[%s,%s],"names":[%s,%s],"coupling":%.3f}',
      jstr(e.zoneIds[1]), jstr(e.zoneIds[2]), jstr(e.names[1]), jstr(e.names[2]), e.coupling
    ))
  end

  local factParts = {}
  for _, f in ipairs(p.factoids) do
    table.insert(factParts, string.format(
      '{"type":%s,"zoneId":%s,"message":%s}',
      jstr(f.type), jstr(f.zoneId), jstr(f.message)
    ))
  end

  return string.format(
    '{"protocol":%s,"frame":%d,"global":{"hydrology":{"level":%.1f,"saturation":%.3f}},"nodes":[%s],"entanglements":[%s],"factoids":[%s]}',
    jstr(p.protocol), p.frame,
    p.global.hydrology.level, p.global.hydrology.saturation,
    table.concat(nodeParts, ","),
    table.concat(entParts, ","),
    table.concat(factParts, ",")
  )
end

function logAndBroadcastTranslation()
  -- We need fresh zoneBuckets - rebuild them inline
  local zoneBucketsLive = {}
  if zoneMap and type(zoneMap.zones) == "table" then
    -- Build fresh per-zone buckets from current unit positions
    for _, teamID in ipairs(Spring.GetTeamList()) do
      local units = Spring.GetTeamUnits(teamID) or {}
      for _, unitID in ipairs(units) do
        if Spring.ValidUnitID(unitID) and not Spring.GetUnitIsDead(unitID) then
          local defID = Spring.GetUnitDefID(unitID)
          local x, _, z = Spring.GetUnitPosition(unitID)
          if x and z then
            local zone = zoneForPosition(x, z)
            if zone and zone.zoneId then
              zoneBucketsLive[zone.zoneId] = zoneBucketsLive[zone.zoneId] or { zone = zone, teams = {} }
              if not zoneBucketsLive[zone.zoneId].teams[teamID] then
                local zb = makeTeamBucket(teamID)
                zb.metrics = emptyMetrics()
                zb.unitCountsByDef = {}
                zoneBucketsLive[zone.zoneId].teams[teamID] = zb
              end
              addUnitToBucket(zoneBucketsLive[zone.zoneId].teams[teamID], defID, unitID)
            end
          end
        end
      end
    end
  end

  local packet = generateTranslationPacket(zoneBucketsLive)
  local json   = serializeTranslationPacket(packet)
  if not json then
    Spring.Echo("VA_TRANSLATION_ERROR failed to serialize packet")
    return
  end

  -- Log to infolog (chunked, readable in headless output)
  Spring.Echo("VA_TRANSLATION_PACKET_COMPACT " .. json)
  logJsonChunked("VA_TRANSLATION_PACKET", json)

  Spring.Echo(string.format(
    "VA_TRANSLATION_OK frame=%d zones=%d entanglements=%d factoids=%d water=%.3f",
    packet.frame, #packet.nodes, #packet.entanglements, #packet.factoids,
    tonumber(vaWaterLevel) or 0
  ))
  -- Crossings are counted BETWEEN packets, so the next matrix measures the next
  -- interval rather than the whole match.
  vaZoneFlow = {}
end
