-- Verdance BeliefField — Lua port of the Umwelt / GummyDynasty host contract.
-- observe(η) → belief(value, confidence). Not umweltd. Not pathfinding.
-- Dissipative roles forget toward 0.5; unitary command roles stick until overwritten.

local M = {}

M.MODE_DISSIPATIVE = "dissipative"
M.MODE_UNITARY = "unitary"
M.KIND_WORLD = "world"
M.KIND_ACTOR = "actor"
M.REDUCE_MEAN = "mean"
M.REDUCE_MAX = "max"

local function clamp01(v)
  v = tonumber(v) or 0
  if v < 0 then return 0 end
  if v > 1 then return 1 end
  return v
end

local function expDecay(gamma, dt)
  if gamma <= 0 or dt <= 0 then return 1 end
  return math.exp(-gamma * dt)
end

function M.new()
  return {
    nodes = {},
    order = {},
  }
end

function M.addNode(field, id, parentId, kind)
  if not field or not id or id == "" then return nil end
  id = tostring(id)
  local node = field.nodes[id]
  if not node then
    node = { id = id, parentId = nil, kind = kind or M.KIND_WORLD, roles = {} }
    field.nodes[id] = node
    field.order[#field.order + 1] = id
  end
  if parentId ~= nil then
    node.parentId = (parentId ~= "" and tostring(parentId)) or nil
  end
  if kind then node.kind = kind end
  return node
end

function M.ensureRole(field, nodeId, role, mode, gammaDiss, reduce)
  local node = field and field.nodes[tostring(nodeId or "")]
  if not node or not role then return nil end
  role = tostring(role)
  local leaf = node.roles[role]
  if not leaf then
    leaf = {
      value = 0.5,
      localValue = 0.5,
      inheritedValue = 0.5,
      confidence = 0,
      override = 0,
      mode = mode or M.MODE_DISSIPATIVE,
      gammaDiss = tonumber(gammaDiss) or 0.35,
      reduce = reduce or M.REDUCE_MEAN,
    }
    node.roles[role] = leaf
  else
    if mode then leaf.mode = mode end
    if gammaDiss ~= nil then leaf.gammaDiss = tonumber(gammaDiss) or leaf.gammaDiss end
    if reduce then leaf.reduce = reduce end
  end
  return leaf
end

function M.observe(field, nodeId, role, value, eta, selfTagged)
  if not field then return end
  eta = tonumber(eta) or 0
  if eta <= 0 then return end
  nodeId = tostring(nodeId or "")
  role = tostring(role or "")
  local node = field.nodes[nodeId]
  if not node then return end
  if selfTagged and node.kind == M.KIND_WORLD then return end

  local leaf = node.roles[role]
  if not leaf then
    leaf = M.ensureRole(field, nodeId, role)
  end
  if not leaf then return end

  value = clamp01(value)
  -- α shrinks as the leaf becomes certain — Umwelt-compatible, not Belavkin.
  local alpha = eta * (1 - 0.5 * leaf.confidence)
  leaf.value = leaf.value + (value - leaf.value) * alpha
  leaf.localValue = leaf.value
  leaf.confidence = leaf.confidence + (1 - leaf.confidence) * eta * 0.25
  leaf.value = clamp01(leaf.value)
  leaf.localValue = leaf.value
  leaf.confidence = clamp01(leaf.confidence)
end

function M.tick(field, dt)
  if not field then return end
  dt = tonumber(dt) or 0
  if dt <= 0 then return end
  for i = 1, #field.order do
    local node = field.nodes[field.order[i]]
    if node then
      for _, leaf in pairs(node.roles) do
        if leaf.mode == M.MODE_DISSIPATIVE and (leaf.gammaDiss or 0) > 0 then
          local k = 1 - expDecay(leaf.gammaDiss, dt)
          leaf.value = leaf.value + (0.5 - leaf.value) * k
          leaf.localValue = leaf.localValue + (0.5 - leaf.localValue) * k
          leaf.confidence = leaf.confidence * expDecay(leaf.gammaDiss, dt)
          leaf.value = clamp01(leaf.value)
          leaf.localValue = clamp01(leaf.localValue)
          leaf.confidence = clamp01(leaf.confidence)
        end
      end
    end
  end
end

-- Drop a node (a unit that died or changed hands). Its children, if any, keep their parentId and
-- simply stop inheriting until the parent comes back.
function M.removeNode(field, id)
  if not field or id == nil then return end
  id = tostring(id)
  if not field.nodes[id] then return end
  field.nodes[id] = nil
  local order, j = field.order, 0
  for i = 1, #order do
    local v = order[i]
    if v ~= id then j = j + 1; order[j] = v end
  end
  for i = #order, j + 1, -1 do order[i] = nil end
end

-- children[parentId] = { child node, ... } in field order: built once per propagate, so the upward
-- pass is linear in the nodes (it used to rescan every node for every parent and role).
local function childIndex(field)
  local children = {}
  for i = 1, #field.order do
    local n = field.nodes[field.order[i]]
    if n and n.parentId then
      local list = children[n.parentId]
      if not list then list = {}; children[n.parentId] = list end
      list[#list + 1] = n
    end
  end
  return children
end

local kids = {}   -- reused by reduceRole
local function reduceRole(children, parent, role, leaf)
  local list = children[parent.id]
  if not list then return end
  local nk = 0
  for i = 1, #list do
    local r = list[i].roles[role]
    if r then nk = nk + 1; kids[nk] = r end
  end
  for i = #kids, nk + 1, -1 do kids[i] = nil end
  if nk == 0 then return end
  if leaf.reduce == M.REDUCE_MAX then
    local best, bestC = 0, 0
    for i = 1, #kids do
      if kids[i].value > best then best = kids[i].value end
      if kids[i].confidence > bestC then bestC = kids[i].confidence end
    end
    leaf.value = best
    leaf.localValue = best
    leaf.confidence = math.max(leaf.confidence, bestC * 0.85)
  else
    local sum, csum = 0, 0
    for i = 1, #kids do
      sum = sum + kids[i].value
      csum = csum + kids[i].confidence
    end
    leaf.value = sum / #kids
    leaf.localValue = leaf.value
    leaf.confidence = math.max(leaf.confidence, (csum / #kids) * 0.85)
  end
end

function M.propagate(field, inherit)
  if not field then return end
  inherit = tonumber(inherit) or 0.15
  -- Children take a weak prior from parents unless local override is high.
  for i = 1, #field.order do
    local node = field.nodes[field.order[i]]
    if node and node.parentId then
      local parent = field.nodes[node.parentId]
      if parent then
        for role, leaf in pairs(node.roles) do
          local parentLeaf = parent.roles[role]
          if parentLeaf then
            leaf.inheritedValue = parentLeaf.value
            local weight = inherit * (1 - clamp01(leaf.override))
            if weight <= 0 then
              leaf.value = leaf.localValue
            else
              leaf.value = leaf.localValue + (leaf.inheritedValue - leaf.localValue) * weight
              leaf.value = clamp01(leaf.value)
            end
          end
        end
      end
    end
  end
  -- Reduce dissipative roles upward (unitary command does not collapse into crowd).
  local children = childIndex(field)
  for i = #field.order, 1, -1 do
    local parent = field.nodes[field.order[i]]
    if parent and children[parent.id] then
      for role, leaf in pairs(parent.roles) do
        if leaf.mode ~= M.MODE_UNITARY then
          reduceRole(children, parent, role, leaf)
        end
      end
    end
  end
end

function M.get(field, nodeId, role)
  local node = field and field.nodes[tostring(nodeId or "")]
  local leaf = node and node.roles[tostring(role or "")]
  if leaf then
    return leaf.value, leaf.confidence
  end
  return 0.5, 0
end

function M.setOverride(field, nodeId, role, weight)
  local node = field and field.nodes[tostring(nodeId or "")]
  local leaf = node and node.roles[tostring(role or "")]
  if leaf then
    leaf.override = clamp01(weight)
  end
end

function M.nodeIdForUnit(unitID)
  return "u" .. tostring(unitID)
end

return M
