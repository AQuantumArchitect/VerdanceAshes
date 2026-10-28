-- campaign/result_world.lua: the result's world parts: the zone graph, reputation, the economy, beliefs and kings
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: resultWorldFields
-- Uses: start, state, telemetry

local function graphJson()
  local g = mission.graph or {}
  -- q7 = Tenebrium scarcity axis (1=dry, 0=abundant). Live bank softens readout.
  local q7 = tonumber(g.q7_resource_scarcity or g.q7_scarcity or 0) or 0
  local bank = tonumber(tenebLoot.bank) or 0
  local liveQ7 = q7
  if bank > 0 then
    liveQ7 = math.max(0, math.min(1, q7 - math.min(0.35, bank * 0.04)))
  end
  return table.concat({
    '"q0_armada_cortex":' .. jnum(g.q0_armada_cortex or 0, 4),
    '"q2_void_structure":' .. jnum(g.q2_void_structure or 0, 4),
    '"q3_biogenesis_memory":' .. jnum(g.q3_biogenesis_memory or 0, 4),
    '"q4_ai_human":' .. jnum(g.q4_ai_human or 0, 4),
    '"q6_contested":' .. jnum(g.q6_contested or 0, 4),
    '"q6_independent":' .. jnum(g.q6_independent or 0, 4),
    '"q7_scarcity":' .. jnum(liveQ7, 4),
    '"q7_resource_scarcity":' .. jnum(liveQ7, 4),
    '"tenebriumBank":' .. jnum(bank, 0),
    '"armadaTenebriumCrisis":' .. tostring(tenebLoot.armadaCrisis == true)
  }, ',')
end

local function reputationJson()
  -- WO-002: clans collapsed into nullmercs. Prefer nullmercs; if only clans is
  -- present on an old seed, emit it under nullmercs (never emit both as distinct).
  local r = mission.reputation or {}
  local merc = r.nullmercs
  if merc == nil then merc = r.clans end
  merc = merc or 0
  return table.concat({
    '"armada":' .. jnum(r.armada or 0, 2),
    '"cortex":' .. jnum(r.cortex or 0, 2),
    '"nullmercs":' .. jnum(merc, 2),
    '"sev":' .. jnum(r.sev or 0, 2)
  }, ',')
end

local function economyJson()
  local e = mission.economy or {}
  return table.concat({
    '"metalIncome":' .. jnum(e.metalIncome or 0, 2),
    '"energyIncome":' .. jnum(e.energyIncome or 0, 2),
    '"buildPower":' .. jnum(e.buildPower or 0, 2)
  }, ',')
end

-- The world around the sortie: the economy, the zone graph, reputation, defensive value by zone,
-- what the company saw (the belief contract) and the kings' showdown.
function resultWorldFields(c)
  return {
    '"economy":{' .. economyJson() .. '}',
    '"graph":{' .. graphJson() .. '}',
    '"reputation":{' .. reputationJson() .. '}',
    '"zoneDv":' .. zoneDvJson(),
    -- pass three belief contract, produced by game_verdance_belief_observe.lua (GG, no new locals here)
    '"observedZones":' .. ((GG and GG.VA_ObservedZonesJson) and GG.VA_ObservedZonesJson() or 'null'),
    '"beliefExport":' .. ((GG and GG.VA_BeliefExportJson) and GG.VA_BeliefExportJson() or 'null'),
    -- the kings' showdown, from game_verdance_kings.lua: who fell, when, to whom
    '"kings":' .. ((GG and GG.VA_KingsJson) and GG.VA_KingsJson() or 'null'),
  }
end

