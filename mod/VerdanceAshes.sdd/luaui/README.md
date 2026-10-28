# The HUD (LuaUI)

The in-game half of the campaign loop. The gadgets (`luarules/`) decide everything. The HUD shows it
and sends the player's few decisions back.

## The loop, as the HUD sees it
1. **Infil card** (`gui_verdance_infil`): the game waits paused. Verb `begin`.
2. **The rail** (`gui_verdance_sidebar`), top to bottom:
   - the phase and the clock;
   - the job's gauge (gate, kings, capture clear → hold, zone hold, fortify, targets), plus the
     side gauges (presence, purge);
   - the marks;
   - the company;
   - the pad.
   Verb `extract` asks the exfil gadget for the manifest.
3. **Manifest** (`gui_verdance_exfil`): opens when `va_manifest_seq` rises. Verbs `confirm`, `back`,
   `destination(i)`. Confirm sends `VA_CMD:extract:<dest>`.
4. **Closing card**: once `va_terminal` = 1. The result goes home to the hub.

The rest of the HUD:
- the minimap board (owns `WG.vaBoard`, writes `live.json` for the hub);
- the voice (`WG.vaVoice.say`; the beats);
- the hero tags;
- the Tenebrium bar and build costs;
- the hot drop;
- the queen's nest.

## How a widget is put together
- `Include/va_hud.lua` is the common ground: `local Hud = VFS.Include("luaui/Include/va_hud.lua")`.
  It provides:
  - the libraries (`Hud.Ash`, `Hud.J`, `Hud.Board`);
  - fact readers (`Hud.num`, `Hud.str`, `Hud.on`, `Hud.json`, `Hud.seed`);
  - sortie state (`Hud.begun`, `Hud.over`, `Hud.modal`, `Hud.paused`);
  - the shared board (`Hud.board`);
  - verbs (`Hud.verb`, `Hud.press`);
  - words (`Hud.clock`, `Hud.dist`, `Hud.plural`, `Hud.wrap`);
  - chrome (`Hud.column`, `Hud.boardBox`).
- **Facts come from rules params.** Widgets never rescan units. The exfil gadget's `hudScan`
  publishes the company (`va_hud_heroes_json`, `va_pad_*`).
- **Verbs.** A key, a click, a text command and the rig's player all call the same named verb
  (`WG.vaVerbs`). Each press is echoed as `VA_UI_VERB`.
- **The sidebar has three layers:** facts (S, H) → the rail (R, published as `WG.vaRail`, with a
  one-line `sentence`) → paint. The rail is built when the facts are polled, so a headless run
  (which never draws) still says what a player would read. Once a game minute it logs
  `VA_UI_RAIL <sentence>`.

## Checking it
- `python3 tools/hud_wire.py` checks that every signal between the gadgets and the HUD has both
  ends: rules params, the events and the kinds inside them, `VA_CMD` commands and `WG` fields.
  `tests/test_hud_wire.py` runs it. Use `--orphans` to list params a gadget writes that nothing
  reads.
- `tools/hud_harness/harness.py` drives every widget under a stubbed Spring. `render.py` draws the
  four screens to PNG.
- **The headless rig.** With modoption `va_autopilot=1`, `gui_verdance_rig_player` plays the HUD by
  pressing its verbs:
  - begin, then `extract` when the autopilot publishes `va_autopilot_leave`, then `confirm`;
  - a sortie that ends `VA_RIG over status=extracted` went through the whole HUD loop;
  - `VA_AUTOPILOT_HUD_SILENT` means the HUD did not finish the job within 20 s, and the autopilot
    extracted by itself.
- `Widgets/include/*.lua` are stubs on purpose. Copying the mod over an old install replaces the
  libraries that used to live there, and BAR would error on them.
