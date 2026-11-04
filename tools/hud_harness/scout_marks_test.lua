-- Run with Lua 5.4 from the workspace root. A sortie's scout mark (mission.secondaries kind
-- "scout") is armed optional and is done once the company has looked hard at its zone
-- (va_obs_<zoneId> from game_verdance_belief_observe reaches 0.7).
local rules, echoes, events = {}, {}, {}
Spring = {
  Echo = function(s) echoes[#echoes + 1] = s end,
  SetGameRulesParam = function(k, v) rules[k] = v end,
  GetGameRulesParam = function(k) return rules[k] end,
  GetUnitRulesParam = function() return nil end,
}
Game = { mapSizeX = 8192, mapSizeZ = 8192 }
MarksLib = dofile("mod/VerdanceAshes.sdd/luarules/gadgets/include/va_marks_registry.lua")
marks = MarksLib.new()
function marksCommit(ev, sid) MarksLib.publish(marks); events[#events + 1] = ev .. ":" .. tostring(sid) end
mission = { secondaries = {
  { id = "sec_t_nw_lane", kind = "scout", zoneId = "T_NW_LANE", label = "Northwest Lane", required = true, x = 0.2, z = 0.3 },
  { id = "bonus_fus_x", label = "Vault", required = false, x = 0.5, z = 0.5 },   -- not a scout: left alone
} }
dofile("mod/VerdanceAshes.sdd/luarules/gadgets/include/campaign/objective_targets.lua")
armScoutMarks()
MarksLib.publish(marks)
assert(MarksLib.count(marks) == 1, "one scout mark armed, the vault waits for its structures")
assert(rules.va_sec1_kind == "scout" and rules.va_sec1_req == 0, "scout marks are always optional")
assert(rules.va_sec1_label == "Northwest Lane" and rules.va_sec1_x == math.floor(0.2 * 8192))
rules.va_obs_T_NW_LANE = 0.4
tickScoutMarks(75)
assert(rules.va_sec1_done == 0, "a glance is not a scouting")
rules.va_obs_T_NW_LANE = 0.72
tickScoutMarks(74)
assert(rules.va_sec1_done == 0, "checked every two seconds, not every frame")
tickScoutMarks(135)
assert(rules.va_sec1_done == 1 and rules.va_sec1_label == "Northwest Lane", "looked at hard: done, label kept")
assert(events[#events] == "secondary_complete:sec_t_nw_lane")
rules.va_obs_T_NW_LANE = 0.1
tickScoutMarks(195)
assert(rules.va_sec1_done == 1, "it stays done when the look fades")
print("ok: scout marks arm optional and complete once the zone is looked at")
