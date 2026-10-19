-- Single MoveCtrl speed composer for Verdance.
-- final = stockSpeed * packMult * fieldMult * vetMult
-- Pack overlay, hero field tags, and veterancy all stamp their leg then call apply.
-- customParams.verdance_baked_mobility forces packMult=1 (Saloon Stride, etc.).

local M = {}

-- Hard ceiling so pack × field × vet cannot make light chassis unpleasant.
M.COMBINED_SPEED_CAP = 1.35

local function truthy(v)
  if v == true or v == 1 then return true end
  if type(v) == "string" then
    v = v:lower()
    return v == "1" or v == "true" or v == "yes" or v == "on"
  end
  return false
end

local function clampMult(v)
  -- tonumber() with zero args errors; missing rules params return nothing.
  if v == nil then return 1 end
  v = tonumber(v) or 1
  if v <= 0 then return 1 end
  return v
end

function M.hasBakedMobility(unitDefID)
  local ud = unitDefID and UnitDefs and UnitDefs[unitDefID]
  local cp = ud and ud.customParams
  if not cp then return false end
  if truthy(cp.verdance_baked_mobility) then return true end
  if truthy(cp.verdance_no_pack_speed) then return true end
  return false
end

function M.readMults(unitID)
  -- Parentheses force nil when GetUnitRulesParam returns nothing.
  local pack = clampMult((Spring.GetUnitRulesParam(unitID, "va_pack_speed_mult")))
  local field = clampMult((Spring.GetUnitRulesParam(unitID, "va_field_speed_mult")))
  local vet = clampMult((Spring.GetUnitRulesParam(unitID, "va_vet_speed_mult")))
  local dID = Spring.GetUnitDefID(unitID)
  if M.hasBakedMobility(dID) then
    pack = 1
  end
  return pack, field, vet, pack * field * vet
end

local function stockSpeed(unitID, fallback)
  local dID = Spring.GetUnitDefID(unitID)
  local ud = dID and UnitDefs[dID]
  local stock = tonumber(ud and ud.speed) or 0
  if stock > 0 then return stock, ud, dID end
  return tonumber(fallback) or 0, ud, dID
end

--- Apply composed speed. opts.move = vet baseline {speed, turnRate, reverse, maxAcc, maxDec, movetype}
function M.apply(unitID, opts)
  opts = opts or {}
  if not unitID or not Spring.ValidUnitID(unitID) then return false end
  if Spring.MoveCtrl and Spring.MoveCtrl.GetTag and Spring.MoveCtrl.GetTag(unitID) ~= nil then
    return false
  end

  local pack, field, vet, combined = M.readMults(unitID)
  if opts.packMult ~= nil then
    pack = clampMult(opts.packMult)
    if M.hasBakedMobility(Spring.GetUnitDefID(unitID)) then pack = 1 end
    combined = pack * field * vet
  end
  if opts.fieldMult ~= nil then
    field = clampMult(opts.fieldMult)
    combined = pack * field * vet
  end
  if opts.vetMult ~= nil then
    vet = clampMult(opts.vetMult)
    combined = pack * field * vet
  end
  local cap = tonumber(M.COMBINED_SPEED_CAP) or 1.35
  if combined > cap then combined = cap end

  local move = opts.move
  local baseSpeed, ud = stockSpeed(unitID, move and move.speed)
  if baseSpeed <= 0 then return false end
  if ud and (ud.isImmobile or (ud.speed or 0) <= 0) and not (move and move.speed) then
    return false
  end

  local target = baseSpeed * combined
  local MC = Spring.MoveCtrl
  if not MC then return false end

  local movetype = move and move.movetype
  if movetype == nil and ud then
    if ud.canFly or ud.isAirUnit then
      movetype = (ud.isHoveringAirUnit and 1) or 0
    else
      movetype = 2
    end
  end
  movetype = movetype or 2

  if movetype == 2 and MC.SetGroundMoveTypeData then
    local attr = {
      maxSpeed = target,
      maxWantedSpeed = target,
    }
    if move then
      attr.maxReverseSpeed = (move.reverse or 0) * combined
      attr.accRate = (move.maxAcc and move.maxAcc > 0 and move.maxAcc or (baseSpeed * 0.15)) * combined
      attr.decRate = (move.maxDec and move.maxDec > 0 and move.maxDec or (baseSpeed * 0.15)) * combined
      if move.turnRate and move.turnRate > 0 then
        attr.turnRate = move.turnRate * (1 + (combined - 1) * 0.35)
      end
    end
    pcall(MC.SetGroundMoveTypeData, unitID, attr)
  elseif movetype == 1 and MC.SetGunshipMoveTypeData then
    local attr = { maxSpeed = target }
    if move then
      attr.accRate = (move.maxAcc and move.maxAcc > 0 and move.maxAcc or (baseSpeed * 0.15)) * combined
      attr.decRate = (move.maxDec and move.maxDec > 0 and move.maxDec or (baseSpeed * 0.15)) * combined
      if move.turnRate and move.turnRate > 0 then
        attr.turnRate = move.turnRate * (1 + (combined - 1) * 0.35)
      end
    end
    pcall(MC.SetGunshipMoveTypeData, unitID, attr)
  elseif movetype == 0 and MC.SetAirMoveTypeData then
    local attr = { maxSpeed = target }
    if move then
      attr.maxAcc = (move.maxAcc and move.maxAcc > 0 and move.maxAcc or (baseSpeed * 0.15)) * combined
    end
    pcall(MC.SetAirMoveTypeData, unitID, attr)
  else
    -- Fallback: try ground then air helpers.
    if MC.SetGroundMoveTypeData then
      pcall(MC.SetGroundMoveTypeData, unitID, { maxSpeed = target, maxWantedSpeed = target })
    end
    if ud and (ud.canFly or ud.isAirUnit) then
      if ud.isHoveringAirUnit and MC.SetGunshipMoveTypeData then
        pcall(MC.SetGunshipMoveTypeData, unitID, { maxSpeed = target })
      elseif MC.SetAirMoveTypeData then
        pcall(MC.SetAirMoveTypeData, unitID, { maxSpeed = target })
      end
    end
  end

  pcall(Spring.SetUnitRulesParam, unitID, "selfMoveSpeedChange", combined, { public = true })
  pcall(Spring.SetUnitRulesParam, unitID, "va_speed_combined", combined, { public = true })
  if GG and GG.UpdateUnitAttributes then
    pcall(GG.UpdateUnitAttributes, unitID)
  end
  return true
end

function M.setPackMult(unitID, speedMult)
  if not unitID or not Spring.ValidUnitID(unitID) then return false end
  speedMult = clampMult(speedMult)
  local dID = Spring.GetUnitDefID(unitID)
  if M.hasBakedMobility(dID) then
    pcall(Spring.SetUnitRulesParam, unitID, "va_pack_speed_mult", 1, { public = true })
    pcall(Spring.SetUnitRulesParam, unitID, "va_pack_speed_skip", "baked_mobility", { public = true })
    return M.apply(unitID)
  end
  if math.abs(speedMult - 1) < 0.01 then
    pcall(Spring.SetUnitRulesParam, unitID, "va_pack_speed_mult", 1, { public = true })
    return M.apply(unitID)
  end
  pcall(Spring.SetUnitRulesParam, unitID, "va_pack_speed_mult", speedMult, { public = true })
  return M.apply(unitID)
end

function M.setFieldMult(unitID, speedMult)
  if not unitID or not Spring.ValidUnitID(unitID) then return false end
  speedMult = clampMult(speedMult)
  pcall(Spring.SetUnitRulesParam, unitID, "va_field_speed_mult", speedMult, { public = true })
  if math.abs(speedMult - 1) < 0.01 then
    return M.apply(unitID)
  end
  return M.apply(unitID)
end

function M.setVetMult(unitID, speedMult, move)
  if not unitID or not Spring.ValidUnitID(unitID) then return false end
  speedMult = clampMult(speedMult)
  pcall(Spring.SetUnitRulesParam, unitID, "va_vet_speed_mult", speedMult, { public = true })
  return M.apply(unitID, { move = move })
end

return M
