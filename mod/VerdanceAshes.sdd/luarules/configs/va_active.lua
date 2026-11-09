-- Is Verdance running? Only in a match the hub launched (va_campaign=1) or a shell bake
-- (va_shell_bake=1). Anything else, such as picking this game in BAR's own skirmish menu,
-- is plain Beyond All Reason: every Verdance gadget, widget and unit override stands down.
local opts = (Spring.GetModOptions and Spring.GetModOptions()) or {}
local active = tostring(opts.va_campaign) == "1" or tostring(opts.va_shell_bake) == "1"

-- Quiet debug lines (2026-11-09). The mod's VA_ lines (hundreds a sortie: the result JSON in 48
-- chunks, field ticks, memory stats) are for the kernel and the test tools, which read the infolog;
-- through Spring.Echo each one also landed in the player's chat console. BAR's chat
-- (luaui/widgets/gui_chat.lua, AddConsoleLine) drops lines at priority L_DEPRECATED, and the infolog
-- keeps them all (log probe, 2026-11-09: "[Verdance] Deprecated: VA_PROBE ...", none de-duplicated),
-- so a single-string Spring.Echo starting "VA_" goes out at that level instead. Every parser searches
-- for its VA_ token anywhere in the line. Every Verdance gadget and widget includes this file first,
-- before it caches Spring.Echo. va_echo=1 keeps the old console echo (debugging in the field).
if active and tostring(opts.va_echo) ~= "1" and Spring.Echo and Spring.Log and LOG and LOG.DEPRECATED
    and not Spring.__vaQuietEcho then
  local echo, log, level = Spring.Echo, Spring.Log, LOG.DEPRECATED
  Spring.Echo = function(a, ...)
    if select("#", ...) == 0 and type(a) == "string" and a:sub(1, 3) == "VA_" then
      return log("Verdance", level, a)
    end
    return echo(a, ...)
  end
  Spring.__vaQuietEcho = true
end

return active
