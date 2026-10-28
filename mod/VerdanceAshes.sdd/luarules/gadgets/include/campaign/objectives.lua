-- campaign/objectives.lua: the objective: its kinds and modes, its state (targets, completion, capture), the target zone
-- Part of game_verdance_campaign.lua, loaded into that gadget's environment
-- (VFS.Include with the gadget table), so its globals are the gadget's globals.
-- Provides: CHECK_PERIOD, CLEAR_FRACTION, PRESENCE_HOLD_DEFAULT, VA_GADGET_KINDS, VA_KINDS,
-- WIPE_GRACE_FRAMES, capture, extraObj, extractLoop, nodeClaimedFrame, objectiveComplete,
-- objectiveCompleteFrame, objectiveKind, objectiveTargetCount, objectiveTargets,
-- objectiveTargetsDestroyed, targetZoneRect, vaObjectiveMode, zoneHoldFrames, zoneRectFor
-- Uses: mission_data, state

-- Objective automation (gadget-env globals — Lua 5.1 main-chunk local budget).
CHECK_PERIOD = 30                 -- frames between objective checks
PRESENCE_HOLD_DEFAULT = 900       -- 30s hold for seize/gate objectives
WIPE_GRACE_FRAMES = 900           -- no wipe-defeat before 30s

-- Objective kinds → how the gadget resolves them (one table, gadget-env).
-- Every kind Python emits (verdance_story_engine_v1 / quest_generator_v1
-- ROLE_ARCHETYPE) must land in exactly one mode; vaObjectiveMode() below echoes
-- the choice at setup as VA_OBJECTIVE_KIND so the infolog shows it.
--   capture  clear the living-shell pocket (CLEAR_FRACTION of eco+teeth), then
--            hold the node under regrow pressure → node claimed. Without a
--            living shell the same kinds fall back to a plain presence hold.
--            siege = take the citadel; multipressure = hold the swamp under
--            pressure from all sides (the regrow waves are the pressure).
--   survive  stand in the target zone for requiredHoldFrames. No targets are
--            booked for it even when a shell is loaded (survive ≠ raze).
--   fortify  raise defensive value in the target zone (fortifyDefensiveValue).
--   targets  anything else (hive_clear_or_bypass, kings_showdown, jump_gate): every booked
--            target must die, unless a dedicated gadget decides the kind (VA_GADGET_KINDS).
-- Every job is territory (2026-10-27): Python turns raids, strikes and the Eye's contracts into
-- seize_lane and keeps the old kind as contractKind, the reason the zone is worth taking.
VA_KINDS = {
  capture = { seize_lane = true, gate_control = true, hold_plateau = true, siege = true, multipressure = true },
  survive = { survive_wilds = true },
  fortify = { fortify_zone = true, home_founding = true },
}
-- kind -> the one completion word its own gadget sends (onObjectiveComplete ignores any other)
VA_GADGET_KINDS = { jump_gate = "jumped" }

objectiveTargets = {}             -- unitID -> forceId (objective_target structures)
objectiveTargetCount = 0
objectiveTargetsDestroyed = 0
objectiveComplete = false

zoneHoldFrames = 0
-- Frames at which the objective facts latched (0 = never). Exported in the result.
objectiveCompleteFrame = 0
nodeClaimedFrame = 0
-- The pad geometry only (pass five: there is no extract loop, timer or hold —
-- the sortie ends when the player confirms the manifest in game_verdance_exfil.lua).
extractLoop = { padRadius = 560 }

extraObj = {
  purge = false,
  purgeDone = false,
  purgeTeams = {},     -- teamID -> true
  announced = false,   -- all-objectives-done broadcast latch
}
CLEAR_FRACTION = 0.6              -- pocket clear threshold for capture claims
-- Capture claim state (one table — Lua 5.1 local budget).
-- Fantasy: clear living-shell pocket, then hold it while regrow pressure tries to retake.
capture = {
  mode = false,             -- armed when living shell + CAPTURE_KIND (or captureMode stamp)
  phase = "idle",           -- idle | clear | hold | claimed
  pocketCleared = false,
  nodeClaimed = false,
  regrowNextFrame = 0,
  regrowInterval = 450,     -- ~15s between pressure pulses during hold
  regrowWaves = 0,
  regrowMax = 6,
  regrowBaseSize = 3,
}

targetZoneRect = nil              -- {x1, z1, x2, z2} in elmos

-- ============================================================
-- OBJECTIVE AUTOMATION
-- Real win/loss detection: target destruction, zone holds,
-- extraction, commander loss, player wipe.
-- ============================================================

function objectiveKind()
  return mission and mission.objective and mission.objective.kind or ""
end

-- How a kind resolves (see VA_KINDS). Gadget-env global: resultJson / setup echo call it.
function vaObjectiveMode(kind)
  kind = tostring(kind or "")
  if VA_KINDS.capture[kind] then return "capture" end
  if VA_KINDS.survive[kind] then return "presence" end
  if VA_KINDS.fortify[kind] then return "fortify" end
  return "targets_all"
end

function zoneRectFor(zoneId)
  if not zoneId or not zoneMap or type(zoneMap.zones) ~= "table" then return nil end
  local sx = Game.mapSizeX or 0
  local sz = Game.mapSizeZ or 0
  for _, z in ipairs(zoneMap.zones) do
    if z.zoneId == zoneId then
      local b = z.bounds or {}
      return {
        normalizedToElmos(b.xMin, sx),
        normalizedToElmos(b.zMin, sz),
        normalizedToElmos(b.xMax, sx),
        normalizedToElmos(b.zMax, sz),
      }, z.label
    end
  end
  return nil
end
