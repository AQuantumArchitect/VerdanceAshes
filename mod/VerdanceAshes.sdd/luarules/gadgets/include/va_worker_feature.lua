-- Resolve featureID from a builder's current worker task (rez / reclaim).
-- Engines without noOffsetForFeatureID offset feature IDs by Game.maxUnits.

local M = {}

function M.needsFeatureOffset()
  return not (Engine and Engine.FeatureSupport and Engine.FeatureSupport.noOffsetForFeatureID)
end

function M.normalizeFeatureID(featureID)
  featureID = tonumber(featureID)
  if not featureID then return nil end
  if M.needsFeatureOffset() then
    featureID = featureID - (Game.maxUnits or 0)
  end
  return featureID
end

--- Returns featureID, cmdID for the builder's current RESURRECT or RECLAIM task.
function M.fromWorkerTask(builderID, opts)
  opts = opts or {}
  if not builderID or not Spring.GetUnitWorkerTask then return nil, nil end
  local cmdID, targetID = Spring.GetUnitWorkerTask(builderID)
  if not cmdID or not targetID then return nil, cmdID end
  local wantRez = opts.resurrect ~= false
  local wantReclaim = opts.reclaim == true
  local isRez = CMD and CMD.RESURRECT and cmdID == CMD.RESURRECT
  local isRec = CMD and CMD.RECLAIM and cmdID == CMD.RECLAIM
  if isRez and wantRez then
    return M.normalizeFeatureID(targetID), cmdID
  end
  if isRec and wantReclaim then
    return M.normalizeFeatureID(targetID), cmdID
  end
  if opts.anyWork and (isRez or isRec) then
    return M.normalizeFeatureID(targetID), cmdID
  end
  return nil, cmdID
end

--- RESURRECT-only (hero rez / field factory join).
function M.featureIDFromResurrect(builderID)
  local fid = M.fromWorkerTask(builderID, { resurrect = true, reclaim = false })
  return fid
end

return M
