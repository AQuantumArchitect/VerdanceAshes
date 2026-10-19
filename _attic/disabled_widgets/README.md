# Disabled / quarantined widgets

Moved out of `mod/VerdanceAshes.sdd/luaui/Widgets/` so BAR never loads them.

| File | Why |
|---|---|
| `gui_verdance_crew_select.lua` | Muster lives on the HTML hub; BAR receives a sealed `crewBand` packet. Gadget still accepts `vacrewconfirm` for console tests. |
| `campaign_overmind_widget.lua` | Chili experiment — not the play path (Ash Console = objectives HUD). |

Do not re-enable without replacing hub muster / Chili boot guarantees.
