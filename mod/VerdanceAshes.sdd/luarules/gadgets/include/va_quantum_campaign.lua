-- Verdance quantum campaign kernel v1.
-- Synced, deterministic, and independent of Spring except through callbacks.

local M = {}

local function clamp(v, lo, hi)
  v = tonumber(v) or 0
  lo, hi = lo or 0, hi or 1
  if v < lo then return lo end
  if v > hi then return hi end
  return v
end

local function copy(value, seen)
  if type(value) ~= "table" then return value end
  seen = seen or {}
  if seen[value] then return seen[value] end
  local out = {}
  seen[value] = out
  for k, v in pairs(value) do out[copy(k, seen)] = copy(v, seen) end
  return out
end

local function sortedKeys(t)
  local keys = {}
  for key in pairs(t or {}) do keys[#keys + 1] = key end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  return keys
end

local function escape(value)
  return tostring(value or ""):gsub("\\", "\\\\"):gsub('"', '\\"')
    :gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t")
end

local function encode(value)
  local kind = type(value)
  if kind == "nil" then return "null" end
  if kind == "boolean" then return value and "true" or "false" end
  if kind == "number" then
    if value ~= value or value == math.huge or value == -math.huge then return "0" end
    return string.format("%.7g", value)
  end
  if kind == "string" then return '"' .. escape(value) .. '"' end
  if kind ~= "table" then return '"' .. escape(value) .. '"' end
  local max, count, array = 0, 0, true
  for key in pairs(value) do
    count = count + 1
    if type(key) ~= "number" or key < 1 or key % 1 ~= 0 then array = false; break end
    if key > max then max = key end
  end
  if array and max == count then
    local parts = {}
    for i = 1, max do parts[i] = encode(value[i]) end
    return "[" .. table.concat(parts, ",") .. "]"
  end
  local parts = {}
  for _, key in ipairs(sortedKeys(value)) do
    parts[#parts + 1] = '"' .. escape(key) .. '":' .. encode(value[key])
  end
  return "{" .. table.concat(parts, ",") .. "}"
end

-- Small deterministic rolling hash. Lua 5.1 numbers are doubles, so both the
-- modulus and every pre-modulo multiplication stay below 2^53.
local function hashText(text)
  -- Some Recoil builds use reduced-precision Lua numbers. Two independent
  -- prime-modulus accumulators keep every multiplication below 2^24 while
  -- retaining roughly 32 bits in the combined opaque identity.
  local a, b = 5381, 52711
  for i = 1, #text do
    local byte = text:byte(i)
    a = (a * 131 + byte) % 65521
    b = (b * 137 + byte + (i % 251)) % 65519
  end
  return "q" .. string.format("%05d%05d", a, b)
end

local GROWTH = {
  SimpleAI = { mobile = 0.0050, economy = 0.0045, fortification = 0.0025 },
  SimpleDefenderAI = { mobile = 0.0035, economy = 0.0030, fortification = 0.0060 },
  NullMercsAI = { mobile = 0.0060, economy = 0.0030, fortification = 0.0015 },
  Ashwalkers = { mobile = 0.0018, economy = 0.0020, fortification = 0.0015 },
  RaptorsAI = { mobile = 0.0040, economy = 0.0000, fortification = 0.0000, hazard = 0.0080 },
}

local function normalizePaths(narrative)
  local total = (tonumber(narrative.pathA) or 0) + (tonumber(narrative.pathB) or 0)
    + (tonumber(narrative.pathC) or 0)
  if total <= 0 then
    narrative.pathA, narrative.pathB, narrative.pathC = 0, 1, 0
  else
    narrative.pathA = (tonumber(narrative.pathA) or 0) / total
    narrative.pathB = (tonumber(narrative.pathB) or 0) / total
    narrative.pathC = (tonumber(narrative.pathC) or 0) / total
  end
end

local function rebuildDensity(state)
  local order = state.zoneOrder or {}
  local byFaction, masses = {}, {}
  for index, zoneId in ipairs(order) do
    local zone = state.zones[zoneId]
    if zone and zone.control and zone.control ~= "neutral" then
      local faction = tostring(zone.control)
      byFaction[faction] = byFaction[faction] or {}
      local mass = math.max(0, tonumber(zone.mobile) or 0)
        + 0.55 * math.max(0, tonumber(zone.economy) or 0)
        + 0.75 * math.max(0, tonumber(zone.fortification) or 0)
        + math.max(0, tonumber(zone.hazard) or 0)
      byFaction[faction][index] = math.sqrt(mass)
      masses[faction] = (masses[faction] or 0) + mass
    end
  end
  local total = 0
  for _, mass in pairs(masses) do total = total + mass end
  if total <= 0 then total = 1 end
  local names, vectors, weights, diagonal = {}, {}, {}, {}
  for i = 1, #order do diagonal[i] = 0 end
  for _, faction in ipairs(sortedKeys(byFaction)) do
    local raw, norm = byFaction[faction], 0
    for i = 1, #order do norm = norm + (raw[i] or 0) ^ 2 end
    norm = math.sqrt(norm)
    if norm <= 0 then norm = 1 end
    local vector, weight = {}, (masses[faction] or 0) / total
    for i = 1, #order do
      vector[i] = (raw[i] or 0) / norm
      diagonal[i] = diagonal[i] + weight * vector[i] * vector[i]
    end
    names[#names + 1], vectors[#vectors + 1], weights[#weights + 1] = faction, vector, weight
  end
  local eigenvalues = copy(weights)
  table.sort(eigenvalues, function(a, b) return a > b end)
  local purity = 0
  for _, weight in ipairs(weights) do purity = purity + weight * weight end
  state.density = {
    names = names, vectors = vectors, weights = weights, diagonal = diagonal,
    eigenvalues = eigenvalues, purity = purity,
  }
end

local Kernel = {}
Kernel.__index = Kernel

function M.new(seed, options)
  local self = setmetatable({}, Kernel)
  self.state = copy(seed or {})
  self.options = options or {}
  self.state.schemaVersion = self.state.schemaVersion or "verdance-quantum-campaign/1.0"
  self.state.clockMinutes = tonumber(self.state.clockMinutes) or 0
  self.state.transitionIndex = tonumber(self.state.transitionIndex) or 0
  self.state.zoneOrder = self.state.zoneOrder or {}
  self.state.zones = self.state.zones or {}
  self.state.edges = self.state.edges or {}
  self.state.narrative = self.state.narrative or { pathA = 0, pathB = 1, pathC = 0, axes = {} }
  self.state.transitQueue = self.state.transitQueue or {}
  self.state.transitionJournal = self.state.transitionJournal or {}
  self.processed = {}
  for _, row in ipairs(self.state.transitionJournal) do
    if row.requestId then self.processed[tostring(row.requestId)] = true end
  end
  normalizePaths(self.state.narrative)
  rebuildDensity(self.state)
  self:_rehash()
  return self
end

function Kernel:_rehash()
  local old = self.state.stateHash
  local afterHashes = {}
  for index, row in ipairs(self.state.transitionJournal or {}) do
    afterHashes[index] = row.afterHash
    row.afterHash = nil
  end
  self.state.stateHash = nil
  self.state.stateHash = hashText(encode(self.state))
  for index, row in ipairs(self.state.transitionJournal or {}) do
    row.afterHash = afterHashes[index]
  end
  return old, self.state.stateHash
end

function Kernel:snapshot() return copy(self.state) end
function Kernel:json() return encode(self.state) end
function Kernel:journalJson() return encode(self.state.transitionJournal or {}) end

function Kernel:_adjacency()
  local out = {}
  for _, edge in ipairs(self.state.edges) do
    if not edge.blocked then
      local a, b = tostring(edge.from), tostring(edge.to)
      local minutes = math.max(0.1, tonumber(edge.travelMinutes) or 3)
      out[a], out[b] = out[a] or {}, out[b] or {}
      out[a][#out[a] + 1] = { to = b, edge = edge, minutes = minutes }
      out[b][#out[b] + 1] = { to = a, edge = edge, minutes = minutes }
    end
  end
  return out
end

function Kernel:_route(source, destination)
  if source == destination then return { source }, {}, 0 end
  local adj, dist, prev, edgePrev, open = self:_adjacency(), {}, {}, {}, {}
  for _, zoneId in ipairs(self.state.zoneOrder) do dist[zoneId] = math.huge end
  dist[source], open[source] = 0, true
  while next(open) do
    local current, best
    for zoneId in pairs(open) do
      if not best or dist[zoneId] < best then current, best = zoneId, dist[zoneId] end
    end
    open[current] = nil
    if current == destination then break end
    for _, step in ipairs(adj[current] or {}) do
      local candidate = dist[current] + step.minutes
      if candidate < (dist[step.to] or math.huge) then
        dist[step.to], prev[step.to], edgePrev[step.to], open[step.to] = candidate, current, step.edge, true
      end
    end
  end
  if not prev[destination] then return nil end
  local route, edges, cursor = { destination }, {}, destination
  while cursor ~= source do
    table.insert(edges, 1, edgePrev[cursor])
    cursor = prev[cursor]
    table.insert(route, 1, cursor)
  end
  return route, edges, dist[destination]
end

function Kernel:_assimilate(samples)
  for _, sample in ipairs(samples or {}) do
    local zone = self.state.zones[tostring(sample.zoneId or "")]
    if zone then
      if sample.control then zone.control = tostring(sample.control) end
      -- BAR values are blended with prior memory so one scout does not erase a
      -- whole offscreen army. Divisors are the measured sortie-scale anchors.
      if sample.av then zone.mobile = clamp(0.35 * zone.mobile + 0.65 * clamp(sample.av / 30000)) end
      if sample.bp then zone.economy = clamp(0.35 * zone.economy + 0.65 * clamp(sample.bp / 6000)) end
      if sample.dp then zone.fortification = clamp(0.35 * zone.fortification + 0.65 * clamp(sample.dp / 30000)) end
    end
  end
end

function Kernel:_grow(dt, activeMapId, measured)
  measured = measured or {}
  for zoneId, zone in pairs(self.state.zones) do
    if not measured[zoneId] then
      local rate = zone.mapId == activeMapId and 0.5 or 0.25
      local growth = GROWTH[zone.actor] or GROWTH.SimpleAI
      local minutes = dt * rate
      zone.mobile = clamp((zone.mobile or 0) + (growth.mobile or 0) * minutes)
      zone.economy = clamp((zone.economy or 0) + (growth.economy or 0) * minutes)
      zone.fortification = clamp((zone.fortification or 0) + (growth.fortification or 0) * minutes)
      zone.hazard = clamp((zone.hazard or 0) + (growth.hazard or 0) * minutes)
    end
  end
end

function Kernel:_arriveOffscreen(now, activeMapId)
  for _, transit in ipairs(self.state.transitQueue) do
    if transit.status == "transit" and tonumber(transit.etaMinute) <= now then
      local destination = self.state.zones[transit.destinationZoneId]
      if destination and destination.mapId ~= activeMapId then
        local force = math.max(0, tonumber(transit.mass) or 0)
        local defenders = math.max(0, tonumber(destination.mobile) or 0)
        if destination.control == "neutral" or destination.control == transit.faction then
          destination.control = transit.faction
          destination.mobile = defenders + force
          transit.casualtyMass = 0
          transit.outcome = "joined"
        else
          local defenderLoss = math.min(defenders, force * 0.75)
          local attackerLoss = math.min(force, defenders * 0.60)
          local defenderSurvivors = defenders - defenderLoss
          local attackerSurvivors = force - attackerLoss
          transit.casualtyMass = defenderLoss + attackerLoss
          if attackerSurvivors > defenderSurvivors then
            destination.control = transit.faction
            destination.mobile = attackerSurvivors - defenderSurvivors
            destination.instability = clamp((destination.instability or 0) + 0.20)
            transit.outcome = "control_changed"
          else
            destination.mobile = defenderSurvivors - attackerSurvivors
            destination.instability = clamp((destination.instability or 0) + 0.12)
            transit.outcome = "repelled"
          end
        end
        transit.status, transit.arrivedMinute = "arrived_offscreen", now
      end
    end
  end
end

function Kernel:_dispatch(measurement)
  local targetId = tostring(measurement.targetZoneId or "")
  local target = self.state.zones[targetId]
  if not target then return nil end
  local against = tostring(measurement.against or target.control or "armada")
  local best
  for sourceId, source in pairs(self.state.zones) do
    if sourceId ~= targetId and source.control == against and (source.mobile or 0) >= 0.055 then
      local route, edges, minutes = self:_route(sourceId, targetId)
      if route then
        local current = (source.mobile or 0) / math.max(0.75, minutes)
        current = current * (0.8 + 0.4 * (self.state.density.purity or 0))
        if not best or current > best.current or (current == best.current and sourceId < best.sourceId) then
          best = { sourceId = sourceId, source = source, route = route, edges = edges,
            minutes = minutes, current = current }
        end
      end
    end
  end
  if not best or best.current < 0.004 then return nil end
  local mass = math.min(best.source.mobile * 0.22, 0.045 + best.current * 0.6)
  if mass < 0.015 then return nil end
  best.source.mobile = clamp(best.source.mobile - mass)
  local id = string.format("tr_%04d_%s_%s", self.state.transitionIndex + 1, best.sourceId, targetId)
  local transit = {
    id = id, faction = against, sourceZoneId = best.sourceId, destinationZoneId = targetId,
    route = best.route, edgeIds = {}, mass = mass, dispatchMinute = self.state.clockMinutes,
    etaMinute = self.state.clockMinutes + best.minutes, status = "transit",
    causeContractId = measurement.contractId, recipe = measurement.reinforcementRecipe or {},
  }
  for _, edge in ipairs(best.edges) do transit.edgeIds[#transit.edgeIds + 1] = edge.id end
  self.state.transitQueue[#self.state.transitQueue + 1] = transit
  return transit
end

function Kernel:transition(measurement)
  measurement = measurement or {}
  local requestId = tostring(measurement.requestId or ("transition_" .. (self.state.transitionIndex + 1)))
  if self.processed[requestId] then return false, "duplicate", nil end
  local beforeHash = self.state.stateHash
  local dt = math.max(0.05, tonumber(measurement.elapsedMinutes) or 0.05)
  self.state.clockMinutes = self.state.clockMinutes + dt
  self:_assimilate(measurement.zoneSamples)
  local measured = {}
  for _, sample in ipairs(measurement.zoneSamples or {}) do measured[tostring(sample.zoneId)] = true end
  self:_grow(dt, tostring(measurement.mapId or ""), measured)

  local target = self.state.zones[tostring(measurement.targetZoneId or "")]
  if target then
    local damage = clamp(measurement.objectiveDamage)
    target.economy = clamp((target.economy or 0) - 0.55 * damage)
    target.fortification = clamp((target.fortification or 0) - 0.45 * damage)
    target.mobile = clamp((target.mobile or 0) - 0.25 * damage)
    target.instability = clamp((target.instability or 0) + 0.2 * damage)
    if measurement.zoneFlipped and measurement.patron then target.control = tostring(measurement.patron) end
  end

  local narrative = self.state.narrative
  local path = tostring(measurement.pathSignal or "B"):upper()
  if path == "A" then narrative.pathA = (narrative.pathA or 0) + 0.08
  elseif path == "C" then narrative.pathC = (narrative.pathC or 0) + 0.08
  else narrative.pathB = (narrative.pathB or 0) + 0.08 end
  normalizePaths(narrative)
  self:_arriveOffscreen(self.state.clockMinutes, tostring(measurement.mapId or ""))
  rebuildDensity(self.state)
  self.state.transitionIndex = self.state.transitionIndex + 1
  local dispatch = self:_dispatch(measurement)
  rebuildDensity(self.state)
  local journal = {
    transitionIndex = self.state.transitionIndex, requestId = requestId,
    contractId = measurement.contractId, mapId = measurement.mapId,
    targetZoneId = measurement.targetZoneId, elapsedMinutes = dt,
    beforeHash = beforeHash, dispatchId = dispatch and dispatch.id or nil,
  }
  self.state.transitionJournal[#self.state.transitionJournal + 1] = journal
  self.processed[requestId] = true
  self:_rehash()
  journal.afterHash = self.state.stateHash
  return true, "accepted", copy(journal)
end

function Kernel:dueArrivals(nowMinute, activeMapId)
  local due = {}
  for _, transit in ipairs(self.state.transitQueue) do
    if transit.status == "transit" and transit.destinationZoneId
        and tonumber(transit.etaMinute) <= tonumber(nowMinute)
        and (not transit.retryMinute or tonumber(transit.retryMinute) <= tonumber(nowMinute))
        and self.state.zones[transit.destinationZoneId]
        and self.state.zones[transit.destinationZoneId].mapId == activeMapId then
      due[#due + 1] = copy(transit)
    end
  end
  table.sort(due, function(a, b) return tostring(a.id) < tostring(b.id) end)
  return due
end

function Kernel:deferArrival(id, retryMinute, reason)
  for _, transit in ipairs(self.state.transitQueue) do
    if transit.id == id and transit.status == "transit" then
      transit.retryMinute = tonumber(retryMinute) or (self.state.clockMinutes + 0.17)
      transit.deferCount = (tonumber(transit.deferCount) or 0) + 1
      transit.deferReason = tostring(reason or "no_hidden_ingress")
      self:_rehash()
      return true
    end
  end
  return false
end

function Kernel:ackArrival(id, physicalMass, minute)
  for _, transit in ipairs(self.state.transitQueue) do
    if transit.id == id and transit.status == "transit" then
      transit.status = "arrived_live"
      transit.arrivedMinute = tonumber(minute) or self.state.clockMinutes
      transit.physicalMass = tonumber(physicalMass) or transit.mass
      local destination = self.state.zones[transit.destinationZoneId]
      if destination then
        destination.mobile = math.max(0, tonumber(destination.mobile) or 0)
          + math.max(0, tonumber(transit.physicalMass) or 0)
      end
      self:_rehash()
      return true
    end
  end
  return false
end

M.encode = encode
M.copy = copy
M.hashText = hashText
return M
