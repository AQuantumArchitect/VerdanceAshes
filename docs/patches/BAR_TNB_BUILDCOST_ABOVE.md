# BAR build-card Tnb `above` cost line

Verdance widget `gui_verdance_tnb_buildcost.lua` calls:

```lua
WG["gridmenu"].setCostOverride(unitDefID, { above = { value = tnb, color = "\255\200\160\255" } })
WG["buildmenu"].setCostOverride(unitDefID, { above = { value = tnb, color = "\255\200\160\255" } })
```

Only when `tnb > 0`. Zero-cost units are left alone (stock metal + energy).

## BAR.sdd patches required

1. `luaui/Widgets/gui_gridmenu.lua` — CostData.above + draw at priceFontSize * 2.35
2. `luaui/Widgets/gui_buildmenu.lua` — same
3. `luaui/Widgets/gui_info.lua` — read WG.verdance_tnb.costOf and print above metal

Without the patches, overrides with only `above` still leave metal/energy intact (top/bottom unset), but Tnb will not appear.
