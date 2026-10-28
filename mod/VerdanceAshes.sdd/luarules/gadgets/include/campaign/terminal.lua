-- campaign/terminal.lua: ending the sortie: the terminal crunch and the GG entry points
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: lastResultJson, publishTenebriumRules, setTerminal, terminal, terminalReason
-- Uses: heroes, mission_data, objective_checks, objectives, result, start, state, telemetry

terminal = false
terminalReason = ""
lastResultJson = nil     -- the one result this sortie wrote (dev telemetry re-sends it)

-- Heavy terminal work (result JSON, telemetry, GameOver).
-- Extracted from setTerminal so the exfil path can paint a loading screen first.
-- Pass five: the sortie ends once, with facts. No verdict here (Python reads the manifest),
-- no deferred crunch, no soft-continue, no engine GameOver. The exfil gadget owns the manifest
-- and the quit; this is the one place the result is written.
function runTerminalCrunch(opts)
  opts = opts or {}
  local kind = opts.reason or terminalReason
  Spring.Echo("VA_TERMINAL_CRUNCH kind=" .. tostring(kind) .. " frame=" .. tostring(Spring.GetGameFrame() or 0))
  logResult()
  if devTel.enabled and SendToUnsynced then
    SendToUnsynced("VERDANCE_TRACK", "result", lastResultJson or "")
  end
  if SendToUnsynced then SendToUnsynced("VERDANCE_MISSION_EVENT", "sortie_over", kind) end
  local profilingRun = headless.autoStart or balance.exportFrame or (#fib.milestones > 0)
  if profilingRun and headless.quit then
    headless.quitFrame = Spring.GetGameFrame() + 60
  end
end

-- kind: "extracted" (manifest confirmed) | "wiped" (nobody left) | "closed" (engine ended it).
function setTerminal(kind, reason)
  if terminal then return end
  terminal = true
  terminalReason = tostring(reason or kind or "")
  status = tostring(kind or "closed")
  debugAutoProgress = 0
  finalizeHeroStates()
  publishHeroRules()
  Spring.SetGameRulesParam("va_terminal", 1, { public = true })
  Spring.SetGameRulesParam("va_status", status, { public = true })
  Spring.SetGameRulesParam("va_terminal_reason", terminalReason, { public = true })
  Spring.Echo("VA_TERMINAL kind=" .. status .. " reason=" .. terminalReason)
  runTerminalCrunch({ reason = status })
end

-- Where the company leaves from (2026-10-24): taking ground extracts ON the ground it took, once
-- secured; a rescue (raise a named hero) goes back to the deployment pad. The exfil gadget asks.
-- A hero raised in the wound of a territory mission (taking a lane, a door, a plateau) is a rescue
-- inside a territory mission, not a rescue contract: the company still leaves from the ground it
-- took (owner, 2026-10-26, after the Greenest Fields door). Only a mission that is the rescue goes
-- home by the way it came.
function GG.VA_ExtractRule()
  local obj = mission and mission.objective or {}
  local mode = vaObjectiveMode(objectiveKind())
  if mode == "capture" or (capture and capture.mode) or VA_KINDS.fortify[objectiveKind()] then
    return "territory", tostring(obj.targetZoneId or mission.targetZoneId or "")
  end
  return "deployment"
end

-- The exfil gadget calls this when the player confirms the manifest.
function GG.VA_EndSortie(kind)
  -- Clean vs contested extraction is Python's reading of manifest.enemyOnPad.
  setTerminal(kind, kind)
end

-- The Spire Gate calls this as a named hero goes through: survived, going home, no wreck.
function GG.VA_HeroPorted(heroId)
  local rec = heroes[tostring(heroId or "")]
  if not rec then return false end
  if rec.unitID and Spring.ValidUnitID(rec.unitID) and Spring.GetUnitExperience then
    local cur = Spring.GetUnitExperience(rec.unitID) or 0
    rec.lastXp = cur
    rec.peakXp = math.max(tonumber(rec.peakXp) or 0, cur)
  end
  rec.ported = true
  rec.result = "survived"
  rec.state = "ported"
  return true
end

-- The kings gadget calls this when every rival king has fallen and ours stands.
function GG.VA_ObjectiveComplete(how)
  onObjectiveComplete(how)
end

function GG.VA_TenebriumBank()
  return tonumber(tenebLoot and tenebLoot.bank) or 0
end

-- Tnb top bar feed (gui_verdance_tnb_bar.lua). GLOBAL on purpose: the main chunk is
-- at Lua 5.1's 200-local ceiling. Every field is guarded; tenebLoot may be bare early
-- (handlers pack attaches after the chunk) so each read is pcall-safe.
function publishTenebriumRules()
  local function readField(name)
    local ok, v = pcall(function() return tenebLoot and tenebLoot[name] end)
    if not ok then return nil end
    return v
  end
  local function asCount(v)
    if type(v) == "function" then
      local ok, r = pcall(v)
      v = ok and r or 0
    end
    if type(v) == "table" then
      local n = 0
      for _ in pairs(v) do n = n + 1 end
      return n
    end
    return tonumber(v) or 0
  end
  local bank = tonumber(readField("bank")) or 0
  local looted = tonumber(readField("looted")) or tonumber(readField("total")) or 0
  local spent = tonumber(readField("spent")) or 0
  local lost = tonumber(readField("lost")) or 0
  local field = asCount(readField("unclaimedWrecks"))
  pcall(Spring.SetGameRulesParam, "va_tenebrium_bank", bank, { public = true })
  pcall(Spring.SetGameRulesParam, "va_tenebrium_looted", looted, { public = true })
  pcall(Spring.SetGameRulesParam, "va_tenebrium_spent", spent, { public = true })
  pcall(Spring.SetGameRulesParam, "va_tenebrium_lost", lost, { public = true })   -- a reload restores all four
  pcall(Spring.SetGameRulesParam, "va_tenebrium_wrecks_unclaimed", field, { public = true })
end
