-- Is Verdance running? Only in a match the hub launched (va_campaign=1) or a shell bake
-- (va_shell_bake=1). Anything else, such as picking this game in BAR's own skirmish menu,
-- is plain Beyond All Reason: every Verdance gadget, widget and unit override stands down.
local opts = (Spring.GetModOptions and Spring.GetModOptions()) or {}
return tostring(opts.va_campaign) == "1" or tostring(opts.va_shell_bake) == "1"
