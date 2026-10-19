-- BROKEN (attic). Do not restore as-is.
--
-- This partial override set corpse = "armcom_dead" (real commander 1250-metal
-- wreck). BAR's unit loader REPLACES by unit name with no deep merge, so a
-- partial table also wiped the rest of armdecom.
--
-- Live override (full unitdef, T2-builder boom, metalcost-scaled wreck):
--   mod/VerdanceAshes.sdd/units/armdecom_tenebrium.lua

return {
  armdecom = {
    corpse = "armcom_dead",
    customParams = {
      verdanceTenebriumDecoy = "1",
      tenebriumWreckAmount = "1",
    },
  },
}
