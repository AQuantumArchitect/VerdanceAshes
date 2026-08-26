-- va_tenebrium_handlers.lua
-- Tenebrium loot handlers for Verdance campaign (WO-043c / Phase 6 split).
-- Loaded via VFS.Include from game_verdance_campaign.lua; returns an attach
-- function so parent locals stay live through api getters:
--   api.jnum / api.jstr / api.teamFaction / api.SendToUnsynced
--   api.playerTeamID() / api.playerAllyTeamID() / api.mission()
-- Do not require() this file standalone.

return function(tenebLoot, api)
  local jnum = api.jnum
  local jstr = api.jstr
  local teamFaction = api.teamFaction
  local SendToUnsynced = api.SendToUnsynced

  -- WO-043c handlers on tenebLoot table only (Lua 5.1 200-local ceiling).
  tenebLoot.publish = function()
    Spring.SetGameRulesParam("va_tenebrium_bank", tenebLoot.bank or 0, { public = true })
    Spring.SetGameRulesParam("va_tenebrium_looted", tenebLoot.looted or 0, { public = true })
    Spring.SetGameRulesParam("va_tenebrium_spent", tenebLoot.spent or 0, { public = true })
    Spring.SetGameRulesParam("va_tenebrium_lost", tenebLoot.lost or 0, { public = true })
    Spring.SetGameRulesParam("va_tenebrium_storage", -1, { public = true }) -- infinite
    Spring.SetGameRulesParam("va_armada_tenebrium_crisis", tenebLoot.armadaCrisis and 1 or 0, { public = true })
    if tenebLoot.publishBpCap then
      tenebLoot.publishBpCap()
    end
  end

  tenebLoot.eventsJson = function()
    local parts = {}
    for i = 1, #(tenebLoot.events or {}) do
      local e = tenebLoot.events[i]
      if e then
        parts[#parts + 1] = '{'
          .. '"amount":' .. jnum(e.amount or 0)
          .. ',"frame":' .. jnum(e.frame or 0)
          .. ',"source":' .. jstr(e.source or "decoy")
          .. '}'
      end
    end
    return '[' .. table.concat(parts, ',') .. ']'
  end

  tenebLoot.costOf = function(unitDefID)
    local ud = unitDefID and UnitDefs[unitDefID]
    if not ud then return 0 end
    local bp = tonumber(ud.buildSpeed or 0) or 0
    if bp <= 0 then return 0 end
    -- Floor 1 for any build-power unit; scale gently with BP (cons/nano/fac/com).
    return math.max(1, math.floor(bp / 150 + 0.999))
  end

  -- v0.8.4: concurrent BP ceiling = 150 * accessTnb (bank + living invested stakes).
  tenebLoot.bpPerTnb = tenebLoot.bpPerTnb or 150

  tenebLoot.unitBuildPower = function(unitDefID)
    local ud = unitDefID and UnitDefs[unitDefID]
    if not ud then return 0 end
    return tonumber(ud.buildSpeed or 0) or 0
  end

  tenebLoot.investedTotal = function()
    local sum = 0
    for _, amt in pairs(tenebLoot.byUnit or {}) do
      sum = sum + (math.floor(tonumber(amt) or 0))
    end
    return sum
  end

  tenebLoot.accessTnb = function()
    return math.max(0, math.floor(tenebLoot.bank or 0) + tenebLoot.investedTotal())
  end

  tenebLoot.maxPlayerBuildPower = function()
    return (tenebLoot.bpPerTnb or 150) * tenebLoot.accessTnb()
  end

  tenebLoot.playerBpUsed = function()
    local team = api.playerTeamID()
    if team == nil then return 0 end
    local units = Spring.GetTeamUnits and Spring.GetTeamUnits(team) or {}
    local sum = 0
    for i = 1, #units do
      local uid = units[i]
      local udid = Spring.GetUnitDefID and Spring.GetUnitDefID(uid)
      local bp = tenebLoot.unitBuildPower(udid)
      if bp > 0 then
        sum = sum + bp
      end
    end
    return sum
  end

  tenebLoot.publishBpCap = function()
    local maxBp = tenebLoot.maxPlayerBuildPower()
    local used = tenebLoot.playerBpUsed()
    if Spring.SetGameRulesParam then
      Spring.SetGameRulesParam("va_tenebrium_bp_max", maxBp, { public = true })
      Spring.SetGameRulesParam("va_tenebrium_bp_used", used, { public = true })
      Spring.SetGameRulesParam("va_tenebrium_access", tenebLoot.accessTnb(), { public = true })
    end
    return maxBp, used
  end

  tenebLoot.isDecoy = function(unitID, unitDefID)
    if unitID and Spring.GetUnitRulesParam then
      local tag = Spring.GetUnitRulesParam(unitID, "va_decoy_node")
      if tag == 1 or tag == true or tag == "1" then return true end
      local role = Spring.GetUnitRulesParam(unitID, "va_force_role")
      if role == "decoy_farmer" or role == "autonomous_decoy_farmer" then return true end
    end
    local ud = unitDefID and UnitDefs[unitDefID]
    if not ud then return false end
    local cp = ud.customParams or {}
    if cp.isdecoycommander or cp.decoyfor then return true end
    local n = string.lower(tostring(ud.name or ""))
    return n == "armdecom" or n == "cordecom" or n == "legdecom"
  end

  tenebLoot.initFromMission = function()
    -- Idempotent: GameStart + startMission both call this; do not wipe unit stamps.
    if tenebLoot._inited then
      tenebLoot.publish()
      return
    end
    tenebLoot._inited = true
    tenebLoot.looted = 0
    tenebLoot.spent = 0
    tenebLoot.lost = 0
    tenebLoot.total = 0
    tenebLoot.pending = {}
    tenebLoot.byFeature = {}
    tenebLoot.byUnit = {}
    tenebLoot.heapTransfer = {}
    tenebLoot.pendingLoss = {}
    tenebLoot.events = {}
    local mission = api.mission()
    local tn = (mission and mission.tenebrium) or {}
    local com = (mission and mission.commerce) or {}
    local startBank = tonumber(tn.playerBank or tn.bank or com.tenebrium or 0) or 0
    tenebLoot.bank = math.max(0, math.floor(startBank))
    local wc = (mission and mission.worldConflict) or {}
    if tn.armadaCrisis ~= nil then
      tenebLoot.armadaCrisis = tn.armadaCrisis == true
    elseif wc.armadaTenebriumCrisis ~= nil then
      tenebLoot.armadaCrisis = wc.armadaTenebriumCrisis == true
    else
      tenebLoot.armadaCrisis = true
    end
    tenebLoot.factionBank = tenebLoot.factionBank or {}
    tenebLoot.factionBank.armada = tenebLoot.armadaCrisis and 0 or math.floor(tonumber(tn.armadaBank or 0) or 0)
    tenebLoot.factionBank.cortex = math.floor(tonumber(tn.cortexBank or 2) or 2)
    tenebLoot.publish()
    Spring.Echo("VA_TENEBRIUM_INIT bank=" .. tostring(tenebLoot.bank)
      .. " armadaCrisis=" .. tostring(tenebLoot.armadaCrisis)
      .. " armadaBank=" .. tostring(tenebLoot.factionBank.armada))
  end

  tenebLoot.addBank = function(amount, source)
    amount = math.floor(tonumber(amount) or 0)
    if amount == 0 then return end
    tenebLoot.bank = math.max(0, (tenebLoot.bank or 0) + amount)
    if amount > 0 then
      tenebLoot.looted = (tenebLoot.looted or 0) + amount
      tenebLoot.total = tenebLoot.looted
    end
    tenebLoot.events[#tenebLoot.events + 1] = {
      amount = amount,
      frame = Spring.GetGameFrame() or 0,
      source = source or "bank",
    }
    tenebLoot.publish()
  end

  tenebLoot.stampUnit = function(unitID, amount)
    amount = math.floor(tonumber(amount) or 0)
    if amount <= 0 or not unitID then return end
    tenebLoot.byUnit[unitID] = amount
    if Spring.SetUnitRulesParam then
      Spring.SetUnitRulesParam(unitID, "va_tenebrium_cost", amount, { public = true })
      Spring.SetUnitRulesParam(unitID, "va_tenebrium_invested", amount, { public = true })
    end
  end

  tenebLoot.tagFeature = function(featureID, amount, fromUnit)
    if not featureID then return end
    amount = math.floor(tonumber(amount) or 0)
    if amount <= 0 then return end
    local prev = tenebLoot.byFeature[featureID]
    if prev and (prev.amountRemaining or 0) > 0 then
      amount = amount + (prev.amountRemaining or 0)
    end
    tenebLoot.byFeature[featureID] = {
      amount = amount,
      amountRemaining = amount,
      looted = false,
      fromUnit = fromUnit,
    }
    if Spring.SetFeatureRulesParam then
      Spring.SetFeatureRulesParam(featureID, "va_tenebrium_shard", 1, { public = true })
      Spring.SetFeatureRulesParam(featureID, "va_tenebrium_amount", amount, { public = true })
    end
    Spring.Echo("VA_TENEBRIUM_SHARD feature=" .. tostring(featureID) .. " amount=" .. tostring(amount))
  end

  tenebLoot.spawnShard = function(x, y, z, amount, fromUnit)
    if not x or not z or amount <= 0 then return nil end
    y = y or (Spring.GetGroundHeight and Spring.GetGroundHeight(x, z)) or 0
    local candidates = {
      "pilha_crystal1", "pilha_crystal_violet1", "pilha_crystal_blue1",
      "pilha_crystal_teal1", "armmex_dead", "cormex_dead", "legmex_dead",
    }
    if not FeatureDefNames then return nil end
    for i = 1, #candidates do
      local name = candidates[i]
      if FeatureDefNames[name] then
        local fid = Spring.CreateFeature(name, x, y, z, 0, Spring.GetGaiaTeamID and Spring.GetGaiaTeamID() or 0)
        if fid then
          tenebLoot.tagFeature(fid, amount, fromUnit)
          if Spring.SetFeatureResources then
            local m = select(1, Spring.GetFeatureResources(fid)) or 10
            local e = select(2, Spring.GetFeatureResources(fid)) or 0
            pcall(Spring.SetFeatureResources, fid, math.max(m, 30), e)
          end
          return fid
        end
      end
    end
    return nil
  end

  tenebLoot.posKey = function(x, z)
    return tostring(math.floor((x or 0) / 8 + 0.5)) .. "|" .. tostring(math.floor((z or 0) / 8 + 0.5))
  end

  tenebLoot.onDead = function(unitID, unitDefID, unitTeam)
    local invested = tenebLoot.byUnit[unitID]
    tenebLoot.byUnit[unitID] = nil
    local isDecoy = tenebLoot.isDecoy(unitID, unitDefID)
    local amount = invested
    if not amount or amount <= 0 then
      if isDecoy then
        amount = tenebLoot.amountPerDecoy or 1
      else
        amount = tenebLoot.costOf(unitDefID)
      end
    end
    if not amount or amount <= 0 then return end
    -- Incomplete nanoframe refund to player bank.
    local hp, maxHp, _, _, bp = Spring.GetUnitHealth(unitID)
    local incomplete = bp and bp < 1.0
    if incomplete and unitTeam == api.playerTeamID() and invested and invested > 0 then
      tenebLoot.bank = (tenebLoot.bank or 0) + invested
      tenebLoot.spent = math.max(0, (tenebLoot.spent or 0) - invested)
      tenebLoot.publish()
      Spring.Echo("VA_TENEBRIUM_REFUND amount=" .. tostring(invested) .. " unit=" .. tostring(unitID))
      return
    end
    local x, y, z = Spring.GetUnitPosition(unitID)
    if not x then
      tenebLoot.lost = (tenebLoot.lost or 0) + amount
      tenebLoot.publish()
      return
    end
    tenebLoot.pending[unitID] = {
      x = x, y = y, z = z,
      frame = Spring.GetGameFrame() or 0,
      amount = amount,
      decoy = isDecoy,
    }
    Spring.Echo("VA_TENEBRIUM_PENDING unit=" .. tostring(unitID)
      .. " amount=" .. tostring(amount)
      .. " decoy=" .. tostring(isDecoy))
  end

  tenebLoot.onFeatureCreated = function(featureID, allyTeamID, sourceID)
    local frame = Spring.GetGameFrame() or 0
    -- Wreck from tracked unit death.
    if sourceID and tenebLoot.pending[sourceID] then
      local pend = tenebLoot.pending[sourceID]
      tenebLoot.pending[sourceID] = nil
      tenebLoot.tagFeature(featureID, pend.amount, sourceID)
      return
    end
    -- Heap / debris successor: pick up transfer from wreck destroyed this frame.
    if tenebLoot.heapTransferFrame == frame or tenebLoot.heapTransferFrame == frame - 1 then
      local x, _, z = Spring.GetFeaturePosition(featureID)
      if x then
        local key = tenebLoot.posKey(x, z)
        local amt = tenebLoot.heapTransfer[key]
        if amt and amt > 0 then
          tenebLoot.heapTransfer[key] = nil
          tenebLoot.tagFeature(featureID, amt, nil)
          Spring.Echo("VA_TENEBRIUM_HEAP_TRANSFER feature=" .. tostring(featureID) .. " amount=" .. tostring(amt))
        end
      end
    end
  end

  tenebLoot.onFeatureDestroyed = function(featureID)
    local rec = tenebLoot.byFeature[featureID]
    if not rec then return end
    tenebLoot.byFeature[featureID] = nil
    local rem = math.floor(tonumber(rec.amountRemaining or rec.amount or 0) or 0)
    if rem <= 0 then return end
    -- Stage for heap/debris transfer (same / next frame at this position).
    local x, _, z = Spring.GetFeaturePosition(featureID)
    if x then
      local frame = Spring.GetGameFrame() or 0
      tenebLoot.heapTransferFrame = frame
      local key = tenebLoot.posKey(x, z)
      tenebLoot.heapTransfer[key] = (tenebLoot.heapTransfer[key] or 0) + rem
      -- Resolve after 2 frames: if heap never claimed the key, Tnb is gone-gone.
      tenebLoot.pendingLoss = tenebLoot.pendingLoss or {}
      tenebLoot.pendingLoss[#tenebLoot.pendingLoss + 1] = {
        key = key, amount = rem, frame = frame,
      }
    else
      tenebLoot.lost = (tenebLoot.lost or 0) + rem
      tenebLoot.events[#tenebLoot.events + 1] = {
        amount = -rem, frame = Spring.GetGameFrame() or 0, source = "wreck_lost",
      }
      tenebLoot.publish()
      Spring.Echo("VA_TENEBRIUM_LOST amount=" .. tostring(rem) .. " (no pos)")
    end
  end

  tenebLoot.tickPending = function(frame)
    -- Decoys / vaporized builders: no corpse → spawn reclaimable flake.
    local spawnAfter = 12
    for unitID, pend in pairs(tenebLoot.pending) do
      if pend and (frame - (pend.frame or 0)) >= spawnAfter then
        tenebLoot.pending[unitID] = nil
        local fid = tenebLoot.spawnShard(pend.x, pend.y, pend.z, pend.amount, unitID)
        if not fid then
          tenebLoot.lost = (tenebLoot.lost or 0) + (pend.amount or 0)
          tenebLoot.publish()
        end
      end
    end
    -- Heap transfer timeout: truly gone → lost.
    if tenebLoot.pendingLoss then
      local keep = {}
      for i = 1, #tenebLoot.pendingLoss do
        local pl = tenebLoot.pendingLoss[i]
        if pl and (frame - (pl.frame or 0)) >= 2 then
          local left = tenebLoot.heapTransfer[pl.key]
          if left and left > 0 then
            tenebLoot.heapTransfer[pl.key] = nil
            tenebLoot.lost = (tenebLoot.lost or 0) + left
            tenebLoot.events[#tenebLoot.events + 1] = {
              amount = -left, frame = frame, source = "wreck_gone",
            }
            Spring.Echo("VA_TENEBRIUM_LOST amount=" .. tostring(left) .. " (wreck gone)")
            tenebLoot.publish()
          end
        elseif pl then
          keep[#keep + 1] = pl
        end
      end
      tenebLoot.pendingLoss = keep
    end
  end

  tenebLoot.tryLoot = function(builderID, builderTeam, featureID, step)
    -- Reclaim steps are negative. Pull Tnb proportional to reclaim progress; durable
    -- until the feature is gone. First tick always moves at least 1 if any remains.
    if not step or step >= 0 then return end
    local rec = tenebLoot.byFeature[featureID]
    if not rec then return end
    local rem = math.floor(tonumber(rec.amountRemaining or 0) or 0)
    if rem <= 0 then return end
    local allyOk = (builderTeam == api.playerTeamID())
    local playerAllyTeamID = api.playerAllyTeamID()
    if not allyOk and Spring.GetUnitAllyTeam and playerAllyTeamID then
      allyOk = Spring.GetUnitAllyTeam(builderID) == playerAllyTeamID
    end
    if not allyOk then return end
    -- Fraction of this reclaim step: BAR step is ~negative reclaim-progress delta.
    local frac = math.min(1, math.max(0.05, math.abs(step)))
    local take = math.max(1, math.floor(rem * frac + 0.5))
    if take > rem then take = rem end
    rec.amountRemaining = rem - take
    if Spring.SetFeatureRulesParam then
      Spring.SetFeatureRulesParam(featureID, "va_tenebrium_amount", rec.amountRemaining, { public = true })
    end
    tenebLoot.addBank(take, rec.fromUnit and "builder_reclaim" or "decoy_reclaim")
    if take > 0 and (tenebLoot.metalBonus or 0) > 0 and Spring.AddTeamResource then
      pcall(Spring.AddTeamResource, builderTeam, "metal", math.min(tenebLoot.metalBonus, 15 * take))
    end
    Spring.Echo("VA_TENEBRIUM_LOOT amount=" .. tostring(take)
      .. " bank=" .. tostring(tenebLoot.bank)
      .. " remainOnWreck=" .. tostring(rec.amountRemaining)
      .. " feature=" .. tostring(featureID))
    if SendToUnsynced then
      SendToUnsynced("VERDANCE_BEAT", "tenebrium_loot", take, tenebLoot.bank, featureID, 0)
    end
    if rec.amountRemaining <= 0 then
      rec.looted = true
    end
  end

  tenebLoot.teamIsArmada = function(teamID)
    local fac = teamFaction[teamID]
    if fac and tostring(fac) == "armada" then return true end
    return false
  end

  tenebLoot.allowCreate = function(unitDefID, builderTeam)
    if not tenebLoot.enabled then return true end
    local cost = tenebLoot.costOf(unitDefID)
    if cost <= 0 then return true end
    -- Armada crisis: no Tnb left — cannot complete new build-power units.
    if tenebLoot.armadaCrisis and tenebLoot.teamIsArmada(builderTeam) then
      Spring.Echo("VA_TENEBRIUM_BLOCKED armada_crisis cost=" .. tostring(cost))
      return false
    end
    if builderTeam == api.playerTeamID() then
      if (tenebLoot.bank or 0) < cost then
        Spring.Echo("VA_TENEBRIUM_BLOCKED need=" .. tostring(cost) .. " have=" .. tostring(tenebLoot.bank or 0))
        return false
      end
      -- Concurrent BP cap: maxBP = 150 * accessTnb (bank + living invested).
      local bp = tenebLoot.unitBuildPower(unitDefID)
      local maxBp = tenebLoot.maxPlayerBuildPower()
      local used = tenebLoot.playerBpUsed()
      -- After spend, access still includes this unit's cost once stamped; gate on
      -- current access (pre-create). Bank 0 + no invested => maxBp 0 => block.
      if maxBp <= 0 or (used + bp) > (maxBp + 0.01) then
        Spring.Echo("VA_TENEBRIUM_BPCAP used=" .. tostring(used)
          .. " need=" .. tostring(bp)
          .. " max=" .. tostring(maxBp)
          .. " access=" .. tostring(tenebLoot.accessTnb())
          .. " bank=" .. tostring(tenebLoot.bank or 0))
        return false
      end
    end
    return true
  end

  tenebLoot.onUnitCreated = function(unitID, unitDefID, unitTeam, builderID)
    local cost = tenebLoot.costOf(unitDefID)
    if cost <= 0 then return end
    -- Pre-spawned mission kit: stamp reclaim stake, do not charge bank again.
    local proxy = Spring.GetUnitRulesParam and Spring.GetUnitRulesParam(unitID, "va_playable_proxy")
    if proxy == 1 or proxy == true or not builderID then
      tenebLoot.stampUnit(unitID, cost)
      if tenebLoot.publishBpCap then tenebLoot.publishBpCap() end
      return
    end
    if unitTeam == api.playerTeamID() then
      if (tenebLoot.bank or 0) < cost then
        -- Should have been blocked; hard fail.
        if Spring.DestroyUnit then pcall(Spring.DestroyUnit, unitID, false, true) end
        return
      end
      local bp = tenebLoot.unitBuildPower(unitDefID)
      local maxBp = tenebLoot.maxPlayerBuildPower()
      local used = tenebLoot.playerBpUsed()
      -- Pre-create used does not include this unit yet.
      if maxBp <= 0 or (used + bp) > (maxBp + 0.01) then
        Spring.Echo("VA_TENEBRIUM_BPCAP destroy unit=" .. tostring(unitID)
          .. " used=" .. tostring(used) .. " bp=" .. tostring(bp) .. " max=" .. tostring(maxBp))
        if Spring.DestroyUnit then pcall(Spring.DestroyUnit, unitID, false, true) end
        return
      end
      tenebLoot.bank = (tenebLoot.bank or 0) - cost
      tenebLoot.spent = (tenebLoot.spent or 0) + cost
      tenebLoot.stampUnit(unitID, cost)
      tenebLoot.publish()
      Spring.Echo("VA_TENEBRIUM_SPEND amount=" .. tostring(cost)
        .. " bank=" .. tostring(tenebLoot.bank)
        .. " unit=" .. tostring(UnitDefs[unitDefID] and UnitDefs[unitDefID].name or unitDefID)
        .. " bpCap=" .. tostring(tenebLoot.maxPlayerBuildPower()))
    else
      -- Enemy / ally AI: stamp for reclaim value; Armada cannot afford new (blocked above).
      tenebLoot.stampUnit(unitID, cost)
    end
  end
end
