-- va_tenebrium_handlers.lua
-- Tenebrium loot handlers for Verdance campaign (WO-043c / Phase 6 split).
-- Loaded via VFS.Include from game_verdance_campaign.lua; returns an attach
-- function so parent locals stay live through api getters:
--   api.jnum / api.jstr / api.teamFaction / api.SendToUnsynced
--   api.playerTeamID() / api.playerAllyTeamID() / api.mission() / api.publishRules()
-- Do not require() this file standalone.

return function(tenebLoot, api)
  local jnum = api.jnum
  local jstr = api.jstr
  local teamFaction = api.teamFaction
  local SendToUnsynced = api.SendToUnsynced

  -- WO-043c handlers on tenebLoot table only (Lua 5.1 200-local ceiling).
  -- One writer for the Tnb rules params: publishTenebriumRules in the campaign
  -- gadget (va_tenebrium_bank / looted / spent / wrecks_unclaimed — the four the
  -- HUD reads). Handlers call it on every bank change; the gadget also calls it
  -- every 30 frames. Nothing else writes va_tenebrium_* params.
  tenebLoot.publish = function()
    if api.publishRules then api.publishRules() end
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

  tenebLoot.claimEventsJson = function()
    local parts = {}
    for i = 1, #(tenebLoot.claimEvents or {}) do
      local e = tenebLoot.claimEvents[i]
      if e then
        parts[#parts + 1] = '{'
          .. '"featureID":' .. jnum(e.featureID or -1)
          .. ',"teamID":' .. jnum(e.teamID or -1)
          .. ',"faction":' .. jstr(e.faction or "unknown")
          .. ',"builderID":' .. jnum(e.builderID or -1)
          .. ',"frame":' .. jnum(e.frame or 0)
          .. ',"amount":' .. jnum(e.amount or 0)
          .. '}'
      end
    end
    return '[' .. table.concat(parts, ',') .. ']'
  end

  tenebLoot.teamBanksJson = function()
    local parts = {}
    local ids = {}
    for teamID in pairs(tenebLoot.teamBanks or {}) do ids[#ids + 1] = teamID end
    table.sort(ids)
    for i = 1, #ids do
      local teamID = ids[i]
      parts[#parts + 1] = jstr(teamID) .. ':' .. jnum(tenebLoot.teamBanks[teamID] or 0)
    end
    return '{' .. table.concat(parts, ',') .. '}'
  end

  tenebLoot.factionBanksJson = function()
    local parts = {}
    local factions = {}
    for faction in pairs(tenebLoot.factionBank or {}) do factions[#factions + 1] = faction end
    table.sort(factions)
    for i = 1, #factions do
      local faction = factions[i]
      parts[#parts + 1] = jstr(faction) .. ':' .. jnum(tenebLoot.factionBank[faction] or 0)
    end
    return '{' .. table.concat(parts, ',') .. '}'
  end

  tenebLoot.unclaimedWrecks = function()
    local n = 0
    for _, rec in pairs(tenebLoot.byFeature or {}) do
      if rec and not rec.claimedByTeam and (rec.amountRemaining or 0) > 0 then n = n + 1 end
    end
    return n
  end

  -- Shared formula (UI build cards Include the same file).
  local TnbCost = nil
  do
    local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_tnb_cost.lua")
    if ok and type(mod) == "table" then TnbCost = mod end
  end

  tenebLoot.bpPerTnb = tenebLoot.bpPerTnb or ((TnbCost and TnbCost.BP_PER_TNB) or 150)

  local function costOpts()
    return {
      amountPerDecoy = tenebLoot.amountPerDecoy or 1,
      bpPerTnb = tenebLoot.bpPerTnb or 150,
    }
  end

  tenebLoot.costOf = function(unitDefID)
    if TnbCost and TnbCost.costOf then
      return TnbCost.costOf(unitDefID, costOpts())
    end
    return 0
  end

  tenebLoot.dropOf = function(unitDefID)
    if TnbCost and TnbCost.dropOf then
      return TnbCost.dropOf(unitDefID, costOpts())
    end
    return tenebLoot.costOf(unitDefID)
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
    -- Always heal tables that tryLoot / publish require (older runs left them nil).
    tenebLoot.claimEvents = tenebLoot.claimEvents or {}
    tenebLoot.teamBanks = tenebLoot.teamBanks or {}
    tenebLoot.events = tenebLoot.events or {}
    tenebLoot.pending = tenebLoot.pending or {}
    tenebLoot.byFeature = tenebLoot.byFeature or {}
    tenebLoot.byUnit = tenebLoot.byUnit or {}
    tenebLoot.heapTransfer = tenebLoot.heapTransfer or {}
    tenebLoot.pendingLoss = tenebLoot.pendingLoss or {}
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
    tenebLoot.teamBanks = {}
    tenebLoot.claimEvents = {}
    tenebLoot.wrecksCreated = 0
    tenebLoot.wrecksClaimed = 0
    tenebLoot.wrecksLost = 0
    tenebLoot.heapTransfer = {}
    tenebLoot.pendingLoss = {}
    tenebLoot.events = {}
    local mission = api.mission()
    local tn = (mission and mission.tenebrium) or {}
    local com = (mission and mission.commerce) or {}
    local startBank = tonumber(tn.playerBank or tn.bank or com.tenebrium or 0) or 0
    -- Mid-reload restore: prefer live published bank over reseeding to 0.
    local frame = (Spring.GetGameFrame and Spring.GetGameFrame()) or 0
    local published = tonumber((Spring.GetGameRulesParam and Spring.GetGameRulesParam("va_tenebrium_bank")))
    if frame > 0 and published ~= nil then
      tenebLoot.bank = math.max(0, math.floor(published))
      tenebLoot.spent = math.max(0, math.floor(tonumber((Spring.GetGameRulesParam("va_tenebrium_spent"))) or 0))
      tenebLoot.looted = math.max(0, math.floor(tonumber((Spring.GetGameRulesParam("va_tenebrium_looted"))) or 0))
      tenebLoot.lost = math.max(0, math.floor(tonumber((Spring.GetGameRulesParam("va_tenebrium_lost"))) or 0))
      Spring.Echo("VA_TENEBRIUM_RESTORE bank=" .. tostring(tenebLoot.bank)
        .. " spent=" .. tostring(tenebLoot.spent)
        .. " frame=" .. tostring(frame))
    else
      tenebLoot.bank = math.max(0, math.floor(startBank))
    end
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

  tenebLoot.addTeamBank = function(teamID, amount, source)
    teamID = tonumber(teamID)
    amount = math.floor(tonumber(amount) or 0)
    if not teamID or amount <= 0 then return end
    tenebLoot.teamBanks[teamID] = math.max(0, (tenebLoot.teamBanks[teamID] or 0) + amount)
    local faction = tostring(teamFaction[teamID] or "unknown")
    tenebLoot.factionBank[faction] = math.max(0, (tenebLoot.factionBank[faction] or 0) + amount)
    if teamID == api.playerTeamID() then
      tenebLoot.addBank(amount, source)
    else
      tenebLoot.events[#tenebLoot.events + 1] = {
        amount = amount,
        frame = Spring.GetGameFrame() or 0,
        source = source or "team_reclaim",
        teamID = teamID,
      }
      tenebLoot.publish()
    end
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

  tenebLoot.tagFeature = function(featureID, amount, fromUnit, sourceTeam, sourceDef)
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
      sourceTeam = sourceTeam,
      sourceDef = sourceDef,
      claimedByTeam = nil,
      claimedByFaction = nil,
      claimFrame = nil,
      claimBuilderID = nil,
    }
    tenebLoot.wrecksCreated = (tenebLoot.wrecksCreated or 0) + 1
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
      -- the size-2 crystals: big enough to spot (the size-1 ones vanished into the grass)
      "pilha_crystal2", "pilha_crystal_violet2", "pilha_crystal_blue2",
      "pilha_crystal_teal2", "armmex_dead", "cormex_dead", "legmex_dead",
    }
    if not FeatureDefNames then return nil end
    for i = 1, #candidates do
      local name = candidates[i]
      if FeatureDefNames[name] then
        local fid = Spring.CreateFeature(name, x, y, z, 0, Spring.GetGaiaTeamID and Spring.GetGaiaTeamID() or 0)
        if fid then
          tenebLoot.tagFeature(fid, amount, fromUnit)
          if Spring.SetFeatureResources then
            pcall(Spring.SetFeatureResources, fid, 30, 100)   -- the reclaim a small crystal gave
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
    -- Drop can be 0 even when cost was > 0 (T2 fabs explode too hard to salvage).
    local drop = tenebLoot.dropOf and tenebLoot.dropOf(unitDefID) or tenebLoot.costOf(unitDefID)
    local amount = invested
    if drop <= 0 then
      amount = 0
    elseif not amount or amount <= 0 then
      if isDecoy then
        amount = tenebLoot.amountPerDecoy or 1
      else
        amount = drop
      end
    else
      -- Stamped invest may exceed dropOf (e.g. fab that costs but never drops).
      amount = math.min(amount, drop)
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
      sourceTeam = unitTeam,
      sourceDef = UnitDefs[unitDefID] and UnitDefs[unitDefID].name or tostring(unitDefID),
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
      tenebLoot.tagFeature(featureID, pend.amount, sourceID, pend.sourceTeam, pend.sourceDef)
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
            tenebLoot.wrecksLost = (tenebLoot.wrecksLost or 0) + 1
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

  -- Claim a Tnb shard into the bank (reclaim / active rez soak — not a free vacuum).
  tenebLoot.claimFeature = function(featureID, builderID, builderTeam, source)
    local rec = tenebLoot.byFeature[featureID]
    if not rec or rec.claimedByTeam then return 0 end
    local rem = math.floor(tonumber(rec.amountRemaining or 0) or 0)
    if rem <= 0 then return 0 end
    local allyOk = (builderTeam == api.playerTeamID())
    local playerAllyTeamID = api.playerAllyTeamID()
    if not allyOk and builderID and Spring.GetUnitAllyTeam and playerAllyTeamID then
      allyOk = Spring.GetUnitAllyTeam(builderID) == playerAllyTeamID
    end
    if not allyOk then return 0 end
    local claimant = tonumber(builderTeam)
    if not claimant then return 0 end
    rec.amountRemaining = 0
    rec.claimedByTeam = claimant
    rec.claimedByFaction = tostring(teamFaction[claimant] or "unknown")
    rec.claimFrame = Spring.GetGameFrame() or 0
    rec.claimBuilderID = builderID
    tenebLoot.wrecksClaimed = (tenebLoot.wrecksClaimed or 0) + 1
    tenebLoot.claimEvents = tenebLoot.claimEvents or {}
    tenebLoot.claimEvents[#tenebLoot.claimEvents + 1] = {
      featureID = featureID,
      teamID = claimant,
      faction = rec.claimedByFaction,
      builderID = builderID,
      frame = rec.claimFrame,
      amount = rem,
      source = source or "reclaim",
    }
    if Spring.SetFeatureRulesParam then
      Spring.SetFeatureRulesParam(featureID, "va_tenebrium_amount", 0, { public = true })
    end
    tenebLoot.addTeamBank(claimant, rem, source or (rec.fromUnit and "builder_reclaim" or "decoy_reclaim"))
    if rem > 0 and (tenebLoot.metalBonus or 0) > 0 and Spring.AddTeamResource then
      pcall(Spring.AddTeamResource, builderTeam, "metal", math.min(tenebLoot.metalBonus, 15 * rem))
    end
    Spring.Echo("VA_TENEBRIUM_LOOT amount=" .. tostring(rem)
      .. " source=" .. tostring(source or "reclaim")
      .. " bank=" .. tostring(tenebLoot.bank)
      .. " feature=" .. tostring(featureID))
    if SendToUnsynced then
      SendToUnsynced("VERDANCE_BEAT", "tenebrium_loot", rem, tenebLoot.bank, featureID, claimant)
    end
    rec.looted = true
    return rem
  end

  tenebLoot.tryLoot = function(builderID, builderTeam, featureID, step)
    -- Reclaim steps are negative. First reclaim tick claims the whole stake.
    if not step or step >= 0 then return end
    tenebLoot.claimFeature(featureID, builderID, builderTeam, "reclaim")
  end

  -- Pull Tnb off the feature a rez bot is actively working (rez or reclaim).
  local WorkerFeature = nil
  do
    local ok, mod = pcall(VFS.Include, "luarules/gadgets/include/va_worker_feature.lua")
    if ok and type(mod) == "table" then WorkerFeature = mod end
  end

  tenebLoot.soakWorkerFeature = function(builderID, builderTeam)
    if not builderID or not Spring.GetUnitWorkerTask or not CMD then return 0 end
    local cmdID, targetID = Spring.GetUnitWorkerTask(builderID)
    if not targetID then return 0 end
    if cmdID ~= CMD.RESURRECT and cmdID ~= CMD.RECLAIM then return 0 end
    local featureID = targetID
    if cmdID == CMD.RESURRECT and WorkerFeature and WorkerFeature.normalizeFeatureID then
      featureID = WorkerFeature.normalizeFeatureID(targetID) or targetID
    elseif cmdID == CMD.RESURRECT
        and not (Engine and Engine.FeatureSupport and Engine.FeatureSupport.noOffsetForFeatureID) then
      featureID = featureID - Game.maxUnits
    end
    local got = tenebLoot.claimFeature(featureID, builderID, builderTeam,
      cmdID == CMD.RESURRECT and "rez_soak" or "reclaim_soak")
    if got <= 0 and cmdID == CMD.RECLAIM and WorkerFeature and WorkerFeature.needsFeatureOffset
        and WorkerFeature.needsFeatureOffset() then
      got = tenebLoot.claimFeature(featureID - Game.maxUnits, builderID, builderTeam, "reclaim_soak")
    elseif got <= 0 and cmdID == CMD.RECLAIM
        and not (Engine and Engine.FeatureSupport and Engine.FeatureSupport.noOffsetForFeatureID) then
      got = tenebLoot.claimFeature(featureID - Game.maxUnits, builderID, builderTeam, "reclaim_soak")
    end
    return got
  end

  tenebLoot.teamIsArmada = function(teamID)
    local fac = teamFaction[teamID]
    if fac and tostring(fac) == "armada" then return true end
    return false
  end

  -- Bank check only. Rez of a Tnb builder soaks the wreck first, then spends.
  tenebLoot.allowCreate = function(unitDefID, builderTeam, builderID)
    if not tenebLoot.enabled then return true end
    local resurrecting = false
    if builderID and Spring.GetUnitWorkerTask and CMD and CMD.RESURRECT then
      local cmdID = Spring.GetUnitWorkerTask(builderID)
      if cmdID == CMD.RESURRECT then
        resurrecting = true
        tenebLoot.soakWorkerFeature(builderID, builderTeam)
      end
    end
    local cost = tenebLoot.costOf(unitDefID)
    if cost <= 0 then return true end
    if builderTeam == api.playerTeamID() and (tenebLoot.bank or 0) < cost then
      Spring.Echo("VA_TENEBRIUM_BLOCKED need=" .. tostring(cost)
        .. " have=" .. tostring(tenebLoot.bank or 0)
        .. (resurrecting and " rez=1" or ""))
      return false
    end
    return true
  end

  tenebLoot.onUnitCreated = function(unitID, unitDefID, unitTeam, builderID)
    local cost = tenebLoot.costOf(unitDefID)
    if cost <= 0 then return end
    -- Pre-spawned mission kit: stamp reclaim shard, do not charge bank again.
    local proxy = Spring.GetUnitRulesParam and Spring.GetUnitRulesParam(unitID, "va_playable_proxy")
    if proxy == 1 or proxy == true or not builderID then
      tenebLoot.stampUnit(unitID, cost)
      return
    end
    if unitTeam == api.playerTeamID() then
      -- Rez may finish a frame after soak; soak again just in case.
      if builderID then
        tenebLoot.soakWorkerFeature(builderID, unitTeam)
      end
      if (tenebLoot.bank or 0) < cost then
        if Spring.DestroyUnit then pcall(Spring.DestroyUnit, unitID, false, true) end
        return
      end
      tenebLoot.bank = (tenebLoot.bank or 0) - cost
      tenebLoot.spent = (tenebLoot.spent or 0) + cost
      tenebLoot.stampUnit(unitID, cost)
      tenebLoot.publish()
      Spring.Echo("VA_TENEBRIUM_SPEND amount=" .. tostring(cost)
        .. " bank=" .. tostring(tenebLoot.bank)
        .. " unit=" .. tostring(UnitDefs[unitDefID] and UnitDefs[unitDefID].name or unitDefID))
    else
      tenebLoot.stampUnit(unitID, cost)
    end
  end

  -- Sum Tnb still stamped on living player units/structures (build stakes).
  tenebLoot.livingStakes = function(teamID)
    teamID = tonumber(teamID)
    local total = 0
    local n = 0
    if not teamID or not Spring.GetTeamUnits then
      return 0, 0
    end
    local units = Spring.GetTeamUnits(teamID) or {}
    for i = 1, #units do
      local uid = units[i]
      local amt = tonumber(tenebLoot.byUnit[uid]) or 0
      if amt <= 0 and Spring.GetUnitRulesParam then
        -- GetUnitRulesParam returns nothing when missing — wrap before tonumber().
        amt = tonumber((Spring.GetUnitRulesParam(uid, "va_tenebrium_invested"))) or 0
      end
      if amt > 0 then
        total = total + math.floor(amt)
        n = n + 1
      end
    end
    return total, n
  end

  -- Exfil: pull living build-stakes back into liquid bank so campaign bag
  -- recovers Tnb spent on structures/units you leave behind when you extract.
  -- Does not touch unclaimed wreck shards (those stay lost unless reclaimed).
  tenebLoot.refundLivingStakesOnExfil = function(teamID)
    teamID = tonumber(teamID) or api.playerTeamID()
    local total, n = tenebLoot.livingStakes(teamID)
    if total <= 0 then
      return 0, 0
    end
    local units = Spring.GetTeamUnits(teamID) or {}
    for i = 1, #units do
      local uid = units[i]
      if tenebLoot.byUnit[uid] then
        tenebLoot.byUnit[uid] = nil
      end
      if Spring.SetUnitRulesParam then
        pcall(Spring.SetUnitRulesParam, uid, "va_tenebrium_invested", 0, { public = true })
      end
    end
    tenebLoot.bank = (tenebLoot.bank or 0) + total
    tenebLoot.spent = math.max(0, (tenebLoot.spent or 0) - total)
    tenebLoot.events[#tenebLoot.events + 1] = {
      amount = total,
      frame = Spring.GetGameFrame() or 0,
      source = "exfil_stake_refund",
    }
    tenebLoot.publish()
    Spring.Echo("VA_TENEBRIUM_EXFIL_REFUND amount=" .. tostring(total)
      .. " units=" .. tostring(n)
      .. " bank=" .. tostring(tenebLoot.bank))
    return total, n
  end
end
