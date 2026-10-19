-- Verdance marks registry.
-- Single source of truth for secondary / recover / vault marks on the sortie.
-- Campaign hero FSM and shell spawn call in; HUD reads va_sec* only.
-- Not a presentation layer — kind drives HUD tags, not label sniffing.

local M = {}

M.KIND = {
  vault = "vault",
  structure = "structure",
  hero_recover = "hero_recover",
}

function M.new()
  return {
    -- group: total, destroyed, required, done, failed, outcome, label, kind, x, z, heroId, meta
    groups = {},
    order = {},    -- stable id list for HUD indices
    targets = {},  -- unitID -> mark id (structure/vault progress)
    requiredLeft = 0,
  }
end

local function ensure(reg, id, defaults)
  id = tostring(id or "")
  if id == "" then return nil end
  local g = reg.groups[id]
  if g then return g end
  g = {
    total = 0,
    destroyed = 0,
    required = false,
    done = false,
    failed = false,
    outcome = "",
    label = id,
    kind = "",
    x = nil,
    z = nil,
    heroId = nil,
    meta = nil,
  }
  if type(defaults) == "table" then
    for k, v in pairs(defaults) do g[k] = v end
  end
  reg.groups[id] = g
  reg.order[#reg.order + 1] = id
  if g.required then
    reg.requiredLeft = reg.requiredLeft + 1
  end
  return g
end

--- Create or reopen a mark. Reopen clears done (re-down after prior resolve).
function M.upsert(reg, id, fields)
  fields = fields or {}
  local g = reg.groups[tostring(id)]
  local wasRequired = g and g.required
  if not g then
    g = ensure(reg, id, {
      total = tonumber(fields.total) or 1,
      destroyed = 0,
      required = fields.required == true,
      done = false,
      failed = false,
      outcome = "",
      label = fields.label or tostring(id),
      kind = tostring(fields.kind or ""),
      x = fields.x,
      z = fields.z,
      heroId = fields.heroId,
      meta = fields.meta,
    })
  else
    g.done = false
    g.failed = false
    g.outcome = ""
    g.destroyed = 0
    if fields.total ~= nil then g.total = tonumber(fields.total) or g.total end
    if fields.label ~= nil then g.label = fields.label end
    if fields.kind ~= nil then g.kind = tostring(fields.kind) end
    if fields.x ~= nil then g.x = fields.x end
    if fields.z ~= nil then g.z = fields.z end
    if fields.heroId ~= nil then g.heroId = fields.heroId end
    if fields.meta ~= nil then g.meta = fields.meta end
    if fields.required == true and not wasRequired then
      g.required = true
      reg.requiredLeft = reg.requiredLeft + 1
    end
  end
  Spring.Echo("VA_MARK_UPSERT id=" .. tostring(id)
    .. " kind=" .. tostring(g.kind)
    .. " req=" .. tostring(g.required == true)
    .. " @ " .. tostring(g.x) .. "," .. tostring(g.z))
  return g
end

--- Successful completion. Clears requiredLeft when required.
function M.complete(reg, id, outcomeLabel)
  id = tostring(id or "")
  local g = reg.groups[id]
  if not g then return nil end
  local newly = not g.done
  if newly then
    g.done = true
    g.failed = false
    g.outcome = "success"
    g.destroyed = math.max(g.destroyed or 0, g.total or 1)
    if g.required then
      reg.requiredLeft = math.max(0, reg.requiredLeft - 1)
    end
  end
  if outcomeLabel ~= nil and tostring(outcomeLabel) ~= "" then
    g.label = tostring(outcomeLabel)
  end
  Spring.Echo("VA_MARK_COMPLETE id=" .. id
    .. " newly=" .. tostring(newly)
    .. " left=" .. tostring(reg.requiredLeft))
  return g, newly
end

--- Failed completion (e.g. rescue wreck destroyed).
-- Closes the mark for HUD but NEVER counts as success for victory gating:
-- requiredLeft is unchanged (required marks stay blocking until success).
function M.fail(reg, id, outcomeLabel)
  id = tostring(id or "")
  local g = reg.groups[id]
  if not g then return nil end
  local newly = not g.done
  if newly then
    g.done = true
    g.failed = true
    g.outcome = "failed"
    g.destroyed = math.max(g.destroyed or 0, g.total or 1)
    -- Do NOT decrement requiredLeft — fail must never unlock victory extract.
  elseif not g.failed then
    -- Already done as success somehow; still stamp failed for HUD honesty.
    g.failed = true
    g.outcome = "failed"
    newly = false
  end
  if outcomeLabel ~= nil and tostring(outcomeLabel) ~= "" then
    g.label = tostring(outcomeLabel)
  end
  Spring.Echo("VA_MARK_FAIL id=" .. id
    .. " newly=" .. tostring(newly)
    .. " left=" .. tostring(reg.requiredLeft))
  return g, newly
end

function M.markRequired(reg, id)
  local g = reg.groups[tostring(id)]
  if not g or g.required then return end
  g.required = true
  if not g.done then
    reg.requiredLeft = reg.requiredLeft + 1
  end
end

--- Bind a live structure unit into a mark group (vault / structure).
function M.bindTarget(reg, unitID, sid, opts)
  if not unitID or reg.targets[unitID] then return nil end
  opts = opts or {}
  sid = tostring(sid or "secondary")
  local g = ensure(reg, sid, {
    total = 0,
    destroyed = 0,
    required = opts.required == true,
    done = false,
    label = opts.label or sid,
    kind = tostring(opts.kind or M.KIND.structure),
    x = opts.x,
    z = opts.z,
  })
  if opts.label then g.label = opts.label end
  if opts.kind then g.kind = tostring(opts.kind) end
  if opts.x ~= nil then g.x = opts.x end
  if opts.z ~= nil then g.z = opts.z end
  if opts.required == true and not g.required then
    M.markRequired(reg, sid)
  end
  g.total = (g.total or 0) + 1
  reg.targets[unitID] = sid
  return g
end

function M.hasTarget(reg, unitID)
  return unitID ~= nil and reg.targets[unitID] ~= nil
end

function M.targetOf(reg, unitID)
  return unitID and reg.targets[unitID] or nil
end

--- Progress a structure mark. Returns markId, group, newlyCompleted.
function M.onTargetDestroyed(reg, unitID)
  local sid = reg.targets[unitID]
  if not sid then return nil, nil, false end
  reg.targets[unitID] = nil
  local g = reg.groups[sid]
  if not g or g.done then return sid, g, false end
  g.destroyed = (g.destroyed or 0) + 1
  if g.destroyed >= (g.total or 0) then
    local _, newly = M.complete(reg, sid, nil)
    return sid, g, newly == true
  end
  return sid, g, false
end

function M.eachTarget(reg, fn)
  for unitID, sid in pairs(reg.targets) do
    fn(unitID, sid)
  end
end

--- Apply mission.secondaries meta (label / coords / required / kind).
function M.enrichFromMission(reg, secondaries, mapSizeX, mapSizeZ)
  if type(secondaries) ~= "table" then return end
  local byId = {}
  for _, m in ipairs(secondaries) do
    if m and m.id then byId[tostring(m.id)] = m end
  end
  mapSizeX = mapSizeX or (Game and Game.mapSizeX) or 0
  mapSizeZ = mapSizeZ or (Game and Game.mapSizeZ) or 0
  for _, sid in ipairs(reg.order) do
    local g = reg.groups[sid]
    local m = byId[sid]
    if g and m then
      if m.label then g.label = m.label end
      if m.required == true then M.markRequired(reg, sid) end
      g.x = math.floor((tonumber(m.x) or 0.5) * mapSizeX)
      g.z = math.floor((tonumber(m.z) or 0.5) * mapSizeZ)
      if not g.kind or g.kind == "" then
        g.kind = tostring(m.kind or (m.highValue and M.KIND.vault or M.KIND.structure))
      end
    end
  end
end

--- Hero wreck → recover mark (seeded field or company). Same kind always.
-- Sortie-linked field recruits stay non-required for the victory gate (pad
-- salvage is not a hard win condition), but destroying them fires the campaign
-- fail→EXTRACT latch. fail() must never credit requiredLeft as success.
function M.upsertHeroRecover(reg, rec)
  if not rec or not rec.id then return nil end
  local sid = "hero_down_" .. tostring(rec.id)
  local isRecruit = (rec.wasFieldRecruit == true) and (rec.recruited ~= true)
  local sortieLinked = rec.sortieLinked == true
  local name = tostring(rec.name or rec.id)
  local label = isRecruit and ("Recruit: " .. name) or ("Recover: " .. name)
  local meta = { recruit = isRecruit, sortieLinked = sortieLinked }
  M.upsert(reg, sid, {
    kind = M.KIND.hero_recover,
    label = label,
    required = false,
    total = 1,
    x = rec.deathX,
    z = rec.deathZ,
    heroId = tostring(rec.id),
    meta = meta,
  })
  rec.secondaryId = sid
  return sid
end

function M.completeHeroRecover(reg, rec, outcome)
  if not rec then return nil end
  local sid = rec.secondaryId or ("hero_down_" .. tostring(rec.id))
  local name = tostring(rec.name or rec.id)
  local label
  if outcome == "lost" then
    label = "Lost: " .. name
    -- Fail path: closed mark, red FAIL in HUD, never victory-gate credit.
    local g, newly = M.fail(reg, sid, label)
    if g then g.outcome = "lost" end
    return g, newly
  elseif outcome == "recruited" then
    label = "Joined: " .. name
  elseif outcome == "recovered" then
    label = "Recovered: " .. name
  end
  local g, newly = M.complete(reg, sid, label)
  if g then g.outcome = tostring(outcome or "success") end
  return g, newly
end

local function subtypeOf(g)
  if not g then return "" end
  if type(g.meta) == "table" and g.meta.recruit then return "recruit" end
  return tostring(g.subtype or "")
end

function M.doneCount(reg)
  local n = 0
  for _, sid in ipairs(reg.order) do
    local g = reg.groups[sid]
    if g and g.done then n = n + 1 end
  end
  return n
end

function M.failedCount(reg)
  local n = 0
  for _, sid in ipairs(reg.order) do
    local g = reg.groups[sid]
    if g and g.failed then n = n + 1 end
  end
  return n
end

function M.successCount(reg)
  local n = 0
  for _, sid in ipairs(reg.order) do
    local g = reg.groups[sid]
    if g and g.done and not g.failed then n = n + 1 end
  end
  return n
end

--- Only writer of va_sec* / va_secondary_* totals (not orphan beat keys).
function M.publish(reg)
  local doneCount = M.doneCount(reg)
  local failedCount = M.failedCount(reg)
  for i, sid in ipairs(reg.order) do
    local g = reg.groups[sid] or {}
    Spring.SetGameRulesParam("va_sec" .. i .. "_id", sid, { public = true })
    Spring.SetGameRulesParam("va_sec" .. i .. "_label", tostring(g.label or sid), { public = true })
    Spring.SetGameRulesParam("va_sec" .. i .. "_req", g.required and 1 or 0, { public = true })
    Spring.SetGameRulesParam("va_sec" .. i .. "_done", g.done and 1 or 0, { public = true })
    Spring.SetGameRulesParam("va_sec" .. i .. "_failed", g.failed and 1 or 0, { public = true })
    Spring.SetGameRulesParam("va_sec" .. i .. "_outcome", tostring(g.outcome or ""), { public = true })
    Spring.SetGameRulesParam("va_sec" .. i .. "_kind", tostring(g.kind or ""), { public = true })
    Spring.SetGameRulesParam("va_sec" .. i .. "_subtype", subtypeOf(g), { public = true })
    if g.x ~= nil then
      Spring.SetGameRulesParam("va_sec" .. i .. "_x", math.floor(tonumber(g.x) or 0), { public = true })
    end
    if g.z ~= nil then
      Spring.SetGameRulesParam("va_sec" .. i .. "_z", math.floor(tonumber(g.z) or 0), { public = true })
    end
  end
  Spring.SetGameRulesParam("va_secondary_total", #reg.order, { public = true })
  Spring.SetGameRulesParam("va_secondary_done", doneCount, { public = true })
  Spring.SetGameRulesParam("va_secondary_failed", failedCount, { public = true })
  Spring.SetGameRulesParam("va_secondary_required_left", reg.requiredLeft, { public = true })
end

function M.requiredLeft(reg)
  return reg.requiredLeft or 0
end

function M.count(reg)
  return #(reg.order or {})
end

function M.resultsJson(reg, jstr, jnum)
  local parts = {}
  for _, sid in ipairs(reg.order) do
    local g = reg.groups[sid] or {}
    parts[#parts + 1] = '{' .. table.concat({
      '"id":' .. jstr(sid),
      '"required":' .. tostring(g.required == true),
      '"completed":' .. tostring(g.done == true and not g.failed),
      '"failed":' .. tostring(g.failed == true),
      '"outcome":' .. jstr(g.outcome or ""),
      '"total":' .. jnum(g.total or 0),
      '"destroyed":' .. jnum(g.destroyed or 0),
      '"kind":' .. jstr(g.kind or ""),
      '"heroId":' .. jstr(g.heroId or ""),
    }, ',') .. '}'
  end
  return '[' .. table.concat(parts, ',') .. ']'
end

return M
