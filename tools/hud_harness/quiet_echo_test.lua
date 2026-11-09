-- va_active.lua's quiet echo, run under plain Lua with a stub engine (tests/test_quiet_echo.py).
-- VA_ lines go to Spring.Log at L_DEPRECATED (BAR's chat drops that priority; the infolog keeps it);
-- everything else still echoes; va_echo=1 and a plain BAR game leave Spring.Echo alone.
local PATH = "mod/VerdanceAshes.sdd/LuaRules/Configs/va_active.lua"

local function fresh(opts)
  local echoed, logged = {}, {}
  Spring = {
    GetModOptions = function() return opts end,
    Echo = function(...) echoed[#echoed + 1] = table.concat({ ... }, " ") end,
    Log = function(section, level, msg) logged[#logged + 1] = { section, level, msg } end,
  }
  LOG = { DEBUG = 20, INFO = 30, NOTICE = 35, DEPRECATED = 37, WARNING = 40 }
  local active = dofile(PATH)
  return active, echoed, logged
end

local function check(cond, what) if not cond then error("FAIL " .. what, 2) end end

-- a campaign match: VA_ quiet, others loud
local active, echoed, logged = fresh({ va_campaign = "1" })
check(active == true, "active in a campaign match")
Spring.Echo("VA_TERMINAL kind=extracted")
Spring.Echo("Commander, the bridge is down")
Spring.Echo("VA_TWO", "args")                         -- more than one argument: left alone
check(#logged == 1 and logged[1][2] == 37 and logged[1][3] == "VA_TERMINAL kind=extracted", "VA_ line logged at L_DEPRECATED")
check(#echoed == 2 and echoed[1] == "Commander, the bridge is down", "other lines still echo")
-- a second include (every gadget includes the file) does not wrap twice
dofile(PATH)
Spring.Echo("VA_AGAIN")
check(#logged == 2 and #echoed == 2, "wrapped once")

-- va_echo=1: the old echo
active, echoed, logged = fresh({ va_campaign = "1", va_echo = "1" })
Spring.Echo("VA_TERMINAL kind=extracted")
check(#echoed == 1 and #logged == 0, "va_echo=1 keeps the echo")

-- plain BAR: nothing touched
active, echoed, logged = fresh({})
check(active == false, "inactive outside the hub")
Spring.Echo("VA_X")
check(#echoed == 1 and #logged == 0, "plain BAR untouched")

print("ok: VA_ lines quiet at L_DEPRECATED, others echo, wrapped once, va_echo=1 and plain BAR untouched")
