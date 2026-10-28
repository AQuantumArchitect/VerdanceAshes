-- campaign/result.lua: the sortie result: resultJson writes the result_* sections in order (RESULT_SECTIONS); chunked logging, logResult, the headless finish
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: echoStatus, finishHeadlessResult, logJsonChunked, logResult
-- Uses: heroes, mission_data, objectives, result_company, result_heroes, result_objective,
-- result_world, start, state, terminal, translation

-- The result is facts only (law: Lua reports facts, Python interprets).
-- status is the terminal KIND (extracted | wiped | closed), never a verdict;
-- tools/manifest_v1.py and tools/match_credit_v1.py turn these facts into
-- victory / partial / defeat / abandon, zone flips and credits. Nothing here
-- may compute a judgement — if Python needs something, export the fact.
-- What every section of the result reads: computed once, in this order, before any field is
-- written. refundLivingStakesOnExfil moves the living Tenebrium stakes back into the bank (a side
-- effect the tenebrium section then reports), and playerUnitFacts is the one walk over our units.
local function resultContext()
  local c = {}
  c.frame = Spring.GetGameFrame() or 0
  c.obj = mission.objective or {}
  c.chapter = sortieChapter or 1
  c.cid = mission.campaignId or "verdance_ashes"
  c.mid = mission.missionId or "va_unknown"
  local reasonSafe = tostring(terminalReason or "none"):gsub("|", "_")
  -- resultKey: unique per sortie attempt (chapter + terminal kind + reason + frame).
  c.rkey = c.cid .. "|" .. c.mid .. "|" .. tostring(mission.missionNumber or 0)
    .. "|ch" .. tostring(c.chapter)
    .. "|" .. tostring(status)
    .. "|" .. reasonSafe
    .. "|f" .. tostring(c.frame)
  Spring.SetGameRulesParam("va_result_key", c.rkey, { public = true })
  -- Exfil refund: living Tnb stakes on player builds return to liquid bank.
  -- Campaign settle uses tenebriumBank as bag SoT; without this, spent stakes
  -- on left-behind structures vanish from the company wallet.
  local livingStakes, livingStakeUnits = 0, 0
  if tenebLoot.refundLivingStakesOnExfil then
    livingStakes, livingStakeUnits = tenebLoot.refundLivingStakesOnExfil(playerTeamID)
  elseif tenebLoot.livingStakes then
    livingStakes, livingStakeUnits = tenebLoot.livingStakes(playerTeamID)
  end
  c.livingStakes = math.floor(tonumber(livingStakes) or 0)
  c.livingStakeUnits = math.floor(tonumber(livingStakeUnits) or 0)
  -- End-of-sortie metal stock → campaign 1km$ export (floor(metal/1000)).
  -- Campaign bag stays home; settle ADDS this export (does not replace bag).
  c.metalStored, c.metalStorage = 0, 0
  if Spring.GetTeamResources then
    local okM, mc, ms = pcall(Spring.GetTeamResources, playerTeamID, "metal")
    if okM then
      c.metalStored = tonumber(mc) or 0
      c.metalStorage = tonumber(ms) or 0
    end
  end
  -- One walk over the player's units: footprint, survivors, XP, loan HP, army metal.
  c.facts = playerUnitFacts()
  return c
end

-- The sortie itself: who, where, when, and how it ended (the terminal KIND and the manifest).
local function resultSortieFields(c)
  local sortieId = mission.hubChoiceId or mission.choiceId or mission.sortieId or ""
  return {
    '"schemaVersion":' .. jstr("verdance-match-result/2.0"),
    '"campaignId":' .. jstr(c.cid),
    '"missionId":' .. jstr(c.mid),
    '"missionNumber":' .. jnum(mission.missionNumber or 0),
    '"playerTeamId":' .. jnum(playerTeamID),
    '"chapterIndex":' .. jnum(c.chapter),
    '"pathSignal":' .. jstr(mission.pathSignal or "B"),
    '"resultKey":' .. jstr(c.rkey),
    '"sortieId":' .. jstr(tostring(sortieId)),
    -- terminal kind only: extracted | wiped | closed (Python reads the verdict off the manifest)
    '"status":' .. jstr(status),
    '"terminalReason":' .. jstr(terminalReason),
    '"manifest":' .. ((GG and GG.VA_ManifestJson) and GG.VA_ManifestJson() or 'null'),
    '"frame":' .. jnum(c.frame),
    '"elapsedMinutes":' .. jnum(c.frame / 1800.0, 2),
    '"holdFrames":' .. jnum(holdFrames),
    '"requiredFrames":' .. jnum(c.obj.requiredFrames or 600),
    '"debugAutoProgress":' .. jnum(debugAutoProgress),
    '"sessionMode":' .. jstr(mission.sessionMode or "same_map"),
    '"occupationModel":' .. jstr(mission.occupationModel or "living_shell"),
    '"deploymentMapId":' .. jstr(mission.deploymentMapId or ""),
    '"mapId":' .. jstr(mission.deploymentMapId or ""),
    '"deploymentZoneId":' .. jstr(mission.deploymentZoneId or ""),
    '"targetZoneId":' .. jstr(mission.targetZoneId or c.obj.targetZoneId or ""),
    '"extractionZoneId":' .. jstr(mission.extractionZoneId or c.obj.extractionZoneId or ""),
    '"patron":' .. jstr(mission.patron or (mission.worldConflict and mission.worldConflict.patron) or ""),
    '"map":{"name":' .. jstr(Game.mapName or "") .. ',"sizeX":' .. jnum(Game.mapSizeX or 0) .. ',"sizeZ":' .. jnum(Game.mapSizeZ or 0) .. '}',
    '"zoneMap":{' .. zoneMapJson() .. '}',
  }
end

-- The result, as one JSON object: the sections in order, each in the part that knows its facts.
local RESULT_SECTIONS = {
  function(c) return resultSortieFields(c) end,   -- here
  function(c) return resultObjectiveFields(c) end, -- result_objective.lua
  function(c) return resultCaptureFields(c) end,   -- result_objective.lua
  function(c) return resultCompanyFields(c) end,   -- result_company.lua
  function(c) return resultHeroFields(c) end,      -- result_heroes.lua
  function(c) return resultMetalFields(c) end,     -- result_company.lua
  function(c) return resultTenebriumFields(c) end, -- result_company.lua
  function(c) return resultWorldFields(c) end,     -- result_world.lua
}

local function resultJson()
  local c = resultContext()
  local fields = {}
  for _, section in ipairs(RESULT_SECTIONS) do
    for _, f in ipairs(section(c)) do fields[#fields + 1] = f end
  end
  return '{' .. table.concat(fields, ',') .. '}'
end

function echoStatus()
  local req = mission.objective and mission.objective.requiredFrames or 600
  Spring.Echo("VA_STATUS mission=" .. tostring(mission.missionId) .. " status=" .. status .. " hold=" .. holdFrames .. "/" .. req .. " auto=" .. debugAutoProgress)
end

function logJsonChunked(prefix, json)
  local chunkSize = 180
  local total = math.ceil(#json / chunkSize)
  if total < 1 then total = 1 end
  Spring.Echo(prefix .. "_BEGIN")
  for i = 1, total do
    local a = ((i - 1) * chunkSize) + 1
    local b = i * chunkSize
    Spring.Echo(prefix .. "_CHUNK " .. tostring(i) .. "/" .. tostring(total) .. " " .. json:sub(a, b))
  end
  Spring.Echo(prefix .. "_END")
end

-- Forward declaration: the Hermitian-observable emitter is defined later (it
-- depends on the zone-scan helpers), but the terminal paths above need to call
-- it. Assigning to this file-scope local at its definition site wires them up.
logAndBroadcastTranslation = nil

function logResult()
  -- resultJson can throw on bad Spring returns; never skip the harvest marker.
  local ok, json = pcall(resultJson)
  if not ok then
    Spring.Echo("VA_RESULT_JSON_ERROR " .. tostring(json))
    json = "{"
      .. '"schemaVersion":"verdance-match-result/2.0-fallback",'
      .. '"status":' .. jstr(tostring(status or "unknown")) .. ","
      .. '"terminalReason":' .. jstr(tostring(terminalReason or "result_json_error")) .. ","
      .. '"objectiveComplete":' .. tostring(objectiveComplete == true) .. ","
      .. '"objectiveFailed":' .. tostring(rescueContractFailed == true) .. ","
      .. '"objectiveFailHero":' .. jstr(tostring(rescueContractFailHero or "")) .. ","
      .. '"tenebriumBank":' .. jnum((tenebLoot and tenebLoot.bank) or 0) .. ","
      .. '"tenebriumLooted":' .. jnum((tenebLoot and (tenebLoot.looted or tenebLoot.total)) or 0)
      .. "}"
  end
  lastResultJson = json
  logJsonChunked("VA_RESULT_JSON", json)
  echoStatus()
end

function finishHeadlessResult(outcome)
  local req = mission.objective and mission.objective.requiredFrames or 600
  status = outcome or "victory"
  holdFrames = req
  debugAutoProgress = 0
  terminal = true
  terminalReason = "headless_fastwin"
  Spring.SetGameRulesParam("va_hold_frames", holdFrames, { public = true })
  Spring.Echo("VA_HEADLESS_RESULT_READY mission=" .. tostring(mission.missionId) .. " status=" .. status)
  logResult()
  if logAndBroadcastTranslation then logAndBroadcastTranslation() end
  if headless.quit then
    headless.quitFrame = Spring.GetGameFrame() + 2
  end
end
