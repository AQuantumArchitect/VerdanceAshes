-- campaign/devcmd.lua: the /luarules va* playtest commands, the headless start and debug auto-progress
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: runVerdanceCommand, tickDebugAutoProgress, tickHeadlessStart
-- Uses: core, logistics, mission_data, objectives, reinforcements, result, setup, start, state,
-- telemetry, terminal, translation

-- Playtest commands change the sortie (grant, spawn, end, reset): cheats only, so a player's
-- typo can never freeze or end a real drop.
local VA_CHEAT_COMMANDS = { vatnb = true, vabrutecrash = true, vaheadless = true, vareset = true,
  vaspawnlayout = true, vastart = true, varesult = true, vaexport = true, vatest_killobjective = true }

function runVerdanceCommand(cmd)
  if type(cmd) ~= "string" then return false end
  local head = cmd:match("^(%a[%w_]*)") or cmd
  if VA_CHEAT_COMMANDS[head] and not Spring.IsCheatingEnabled() then
    Spring.Echo("VA_CMD_DENIED " .. head .. " needs /cheat")
    return true
  end
  -- Exfil (manifest / extract:<dest>) is owned by game_verdance_exfil.lua.
  -- Operator / playtest: grant liquid Tenebrium so BP constructors unlock.
  local tnbAmt = cmd:match("^vatnb[%s:]+(%-?%d+)")
  if cmd == "vatnb" or tnbAmt or cmd:match("^vatnb[%s:]") then
    local n = tonumber(tnbAmt) or 8
    if tenebLoot and tenebLoot.addBank then
      tenebLoot.addBank(n, "operator_grant")
      Spring.Echo("VA_TENEBRIUM_GRANT amount=" .. tostring(n)
        .. " bank=" .. tostring(tenebLoot.bank or 0))
    else
      Spring.Echo("VA_TENEBRIUM_GRANT_FAIL handlers_missing")
    end
    return true
  end
  local bruteN = cmd:match("^vabrutecrash[%s:]+(%d+)")
  if cmd == "vabrutecrash" or bruteN or cmd:match("^vabrutecrash") then
    spawnBruteCrashFromEdge(tonumber(bruteN) or 4)
    return true
  end
  if cmd == "vastart" then startMission()
  elseif cmd == "vastatus" then echoStatus()
  elseif cmd == "vatest_killobjective" then
    if Spring.IsCheatingEnabled() then
      local ids = {}
      for unitID in pairs(objectiveTargets) do ids[#ids + 1] = unitID end
      for _, unitID in ipairs(ids) do Spring.DestroyUnit(unitID, false, false) end
      Spring.Echo("VA_TEST_KILLOBJECTIVE destroyed=" .. tostring(#ids))
    else
      Spring.Echo("VA_TEST_DENIED cheats required for vatest_killobjective")
    end
  elseif cmd == "vaspawnlayout" then spawnPlayableSetup()
  elseif cmd == "vazones" then echoZones()
  elseif cmd == "vatelemetry" or cmd == "vabalance" then logTelemetry()
  elseif cmd == "vatranslation" then logAndBroadcastTranslation()
  elseif cmd == "varesult" or cmd == "vaexport" then
    if Spring.IsCheatingEnabled() then logResult() else Spring.Echo("VA_TEST_DENIED cheats required for varesult") end
  elseif cmd == "vaheadless" then startMission(); finishHeadlessResult("victory")
  elseif cmd == "vacallmercs" then
    -- Pillar B / C payoff: at high standing the Null Mercs answer one call.
    if mercsAllied and mercTeamID and not mercWaveUsed then
      local px, pz = teamUnitCentroid(playerTeamID)
      local ex, ez = teamUnitCentroid(objectiveTeamID)
      local n = spawnWave(mercTeamID, waves.baseSize + 2, ex or px, ez or pz, "merc_call")
      if n > 0 then
        mercWaveUsed = true
        Spring.SetGameRulesParam("va_mercs_available", 0, { public = true })
        Spring.SetGameRulesParam("va_mercs_called", 1, { public = true })
        Spring.Echo("VA_MERCS_CALLED count=" .. tostring(n))
      end
    else
      Spring.Echo("VA_MERCS_UNAVAILABLE allied=" .. tostring(mercsAllied) .. " used=" .. tostring(mercWaveUsed))
    end
  elseif cmd == "vareset" then
    -- Local debug mission latch only — not a campaign wipe (use hub RESET.bat).
    status = "inactive"
    holdFrames = 0
    debugAutoProgress = 0
    Spring.Echo("VA_RESET local_debug_only (hub RESET.bat wipes campaign)")
    echoStatus()
  elseif cmd:match("^vapack") then
    -- Mid-Drop A/B for pack glue / line-spread (handled by pack_overlay GG).
    if GG and GG.VA_PackSet then
      local rest = string.lower((cmd:match("^vapack%s+(.+)$") or ""):match("^%s*(.-)%s*$") or "")
      if rest == "" or rest == "status" or rest == "?" then
        if GG.VA_PackStatus then GG.VA_PackStatus() end
      elseif rest == "help" then
        Spring.Echo("VA_PACK help: /vapack status|on|off|drag on|drag off")
      elseif rest:match("^drag%s+") then
        local tok = rest:match("^drag%s+(%S+)")
        local on = (tok == "on" or tok == "1" or tok == "true")
        local off = (tok == "off" or tok == "0" or tok == "false")
        if on or off then
          GG.VA_PackSet({ drag = on })
        else
          Spring.Echo("VA_PACK_BAD use /vapack drag on|off")
        end
      elseif rest == "on" or rest == "1" or rest == "true" then
        GG.VA_PackSet({ enabled = true, drag = true })
      elseif rest == "off" or rest == "0" or rest == "false" then
        GG.VA_PackSet({ enabled = false, drag = false })
      else
        Spring.Echo("VA_PACK_BAD use /vapack status|on|off|drag on|drag off")
      end
    else
      Spring.Echo("VA_PACK_UNAVAILABLE overlay_gadget_missing")
    end
  else return false end
  return true
end

-- A headless run starts the sortie itself on frame 1 (and a fast-win batch ends it). Called by gadget:GameFrame.
function tickHeadlessStart(frame)
  if headless.autoStart and not headless.started and frame >= 1 then
    headless.started = true
    startMission()
    if VA_LOGISTICS and VA_LOGISTICS.spawnCommerceDeployKit then
      VA_LOGISTICS.spawnCommerceDeployKit()
    end
    armPendingDeliveries()
    if headless.fastWin then
      finishHeadlessResult("victory")
    end
  end
end

-- Called by gadget:GameFrame.
function tickDebugAutoProgress(frame)
  -- Debug/fastwin auto-progress timer (only armed via modoption)
  if status == "active" and debugAutoProgress == 1 and frame % 30 == 0 then
    holdFrames = holdFrames + 30
    Spring.SetGameRulesParam("va_hold_frames", holdFrames, { public = true })
    local req = mission.objective and mission.objective.requiredFrames or 600
    if holdFrames >= req then
      Spring.Echo("VA_OBJECTIVE_COMPLETE mission=" .. tostring(mission.missionId))
      setTerminal("extracted", "debug_autoprogress")
    end
  end
end
