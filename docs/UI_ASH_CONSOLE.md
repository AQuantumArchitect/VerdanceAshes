# Ash Console — Shared UI Feel

**One product, two skins:** BAR in-theater HUD + HTML war-room hub.

Version: **0.9** · **pass seven 2026-10-20**: three surfaces (minimap board · sidebar · infil/exfil cards), one encoding, no pings. Protocol credit laws stay in `docs/CAMPAIGN_BAR_PROTOCOL.md` and `tools/match_credit_v1.py`. Theater/home rules: `docs/archive/THEATER_MAP_AND_HOME.md`.

---

## Feel

Ash dark · parchment gold · living green edge · steam for systems · violet Tnb · honest verdict colors · quiet hierarchy · Ketha in a framed voice block · uppercase kickers · short headlines.

Not a second brand. Not a debug strip. Not “partial looks like victory.”

---

## Token table (`verdance-ash` v1)

| Token | Hex | RGB (0–1) | Use |
|---|---|---|---|
| `bg` | `#040907` | 0.016, 0.035, 0.027 | Page / deepest fill |
| `panel` | `#08100c` @ 0.90 | 0.031, 0.063, 0.047, 0.90 | Cards |
| `ink` | `#eef6ee` | 0.933, 0.965, 0.933 | Body text |
| `muted` | `#7d9584` | 0.490, 0.584, 0.518 | Secondary |
| `ash` | `#9a8b72` | 0.604, 0.545, 0.447 | Kickers / brand micro |
| `edge` | `#3d8f55` | 0.239, 0.561, 0.333 | Borders, live phase |
| `gold` | `#d4c49a` | 0.831, 0.769, 0.604 | Titles, focus |
| `ketha` | `#a6d1a6` | 0.651, 0.820, 0.651 | Voice line (near edge) |
| `steam` | `#7ec8ff` | 0.494, 0.784, 1.000 | Systems / extract / wire |
| `good` | `#7dff8a` | 0.490, 1.000, 0.541 | Victory / claimed |
| `warn` | `#e0a060` | 0.878, 0.627, 0.376 | Partial / hold / clock |
| `bad` | `#ff7d7d` | 1.000, 0.490, 0.490 | Defeat / hero down |
| `tnb` | `#c9a0ff` | 0.788, 0.627, 1.000 | Tenebrium |

**Map markers (shared semantics)**

| Role | Color |
|---|---|
| Pad (land and lift, one point) | `steam` ring r=560, △ glyph |
| Objective / wound | `warn` |
| Belief fill | ours `edge`/`good` · held-by-faction = that faction's colour · held-unseen `warn` · empty border only · nobody looked = hatch + `?` · alpha = confidence · stale = dotted `ash` ring |
| Exposure | `bad` diagonal hatch (α = how much of us they see) + ◉ at the zone they believe we are in |
| History | ✗ `warn` / ○ `muted` where the briefing was contradicted · ⚑ people left · ■ `gold` holdings |

**Implementations**

- Lua: `mod/VerdanceAshes.sdd/luaui/Widgets/include/va_ash_tokens.lua`
- HTML: `app/showoff/index.html` `:root` CSS variables (keep names locked)

---

## Copy table (keep in sync with `match_credit_v1`)

| Verdict | Banner | Headline |
|---|---|---|
| victory | SECURED | Secured. |
| partial | HINGE | Hinge. Not a win. |
| defeat | FIELD COSTS | Field costs. |
| abandon | LEFT THE FIELD | Left the field. |
| incomplete | RESULT NOT HOME | Result not home — Retry extract or Abandon. |

Secondary: `reasonHint` from credit table; never invent a third dialect.

---

## Surfaces (pass seven)

| Surface | File | Role |
|---|---|---|
| Hub | `app/showoff/index.html` | Company, Drop board, homecoming card, Abandon |
| Belief board (model + painter) | `luaui/Include/va_board.lua` | ONE encoding for every in-game map surface: faction fill = who we believe holds it, alpha = confidence, LOS fades belief, bad hatch = how much of us they see, △ pad, ◆ objective, ◆/◇/✓/✗ marks, ◉ loudest exposure, ✗/○ contradictions, ●○✚⚑ people. Zone outlines, never cell grids. |
| Minimap | `gui_verdance_minimap.lua` | The minimap IS the board (owns `WG.vaBoard`, `WG.vaContradicted`); pad ring on the ground; Yeva on contradictions |
| Sidebar | `gui_verdance_sidebar.lua` | Phase chip + clock meter · mission + progress meter + mark squares · the company (a card per hero: strip, hp bar, state glyph; click selects, double-click focuses) · the pad (dots, exposure, EXTRACT, "left if you lift"). Paints the route stage on the battlefield with MarkerAddLine — no marker text, no ground arrows, no pings. |
| Infil card | `gui_verdance_infil.lua` | Paused landing card: who you brought · the board with pad + job · the job, marks, clock, Yeva's read. Enter begins. `/vabrief` reopens. |
| Exfil manifest | `gui_verdance_exfil.lua` | EXTRACT → pause → going / left-if-you-lift / the board with ●○■ / briefed→seen swatches → confirm. Closing card = the board frozen. |
| Voice | `gui_verdance_voice.lua` | One stack: Ketha, Yeva, rank-ups, inbound. `WG.vaVoice.say`. `/valog`. |
| Tnb bar | `gui_verdance_tnb_bar.lua` | Top-centre: bank · looted · field, pips, rise/fall flash |
| Hero tags | `gui_verdance_hero_tags.lua` | Name only over heroes and wrecks |
| Proxy story | `gui_verdance_proxy_story.lua` | Optional archive (`/vastoryshow`) |

Retired in pass seven (history keeps them): `gui_verdance_objectives.lua` (2,793 lines: rail, narrative cam, F9 overlay, marker spam), `gui_verdance_zone_minimap.lua`, `gui_verdance_belief_overlay.lua`, `gui_verdance_playfeel.lua` (centre-screen nags, debug chip, retreat rays).

**Gadget truth for the HUD** (`game_verdance_exfil.lua` hudScan, every 30 frames): `va_hud_heroes_json` [{id,name,unit,hp,x,z,onPad,zone,crit,level,rank,vet,state,dist} + down wrecks], `va_pad_people/units/off_units/off_structures/enemy_live`. Widgets never rescan units.

**Harness**: `tools/hud_harness/harness.py` runs the widgets under a stubbed Spring in liblua (Linux); `render.py` draws the recorded gl calls to PNG so a screen can be looked at before BAR runs it.

---|---|---|
| Hub | `app/showoff/index.html` | Company, Drop board, homecoming card, Abandon |
| BAR command deck | `gui_verdance_objectives.lua` | Briefing, phase chip, pad ring + headcount, EXTRACT states + "left if you lift", SEEN row, barks (one voice queue with Yeva) |
| Exfil manifest | `gui_verdance_exfil.lua` | EXTRACT → pause → going / staying / learned → confirm |
| Belief overlay | `gui_verdance_belief_overlay.lua` | Minimap belief fill, exposure hatch, contradiction glyphs, Yeva |
| Tnb bar | `gui_verdance_tnb_bar.lua` | Top-centre: bank · looted · field, pips, rise/fall flash |
| Hero tags | `gui_verdance_hero_tags.lua` | World labels |
| Zone minimap | `gui_verdance_zone_minimap.lua` | Enfil / obj / extract |
| Proxy story | `gui_verdance_proxy_story.lua` | Optional archive (`/vastoryshow`) |
| Overmind Chili | `campaign_overmind_widget.lua` | Experiment — not play path; disabled by default |

---

## Chrome rules

- **Kicker:** uppercase, wide tracking, `ash`
- **Title:** `gold`
- **Voice:** left edge bar `edge` + speaker kicker + italic-ish line
- **Panel:** dark fill + thin `edge` border + left accent strip
- **Phase chip:** ▸ APPROACH `edge` · ✦ FIGHT `warn` · ◆ MARKS `gold` · ⌂ EXTRACT `steam` (board resolved — your call) · ∞ OVERTIME `ash` (the map is awake). The clock never ends a sortie and is never red.
- **Verdict colors:** victory=`good`, partial=`warn`, defeat=`bad`, abandon=`muted`, incomplete=`steam`

---

## Presentability checklist

Operator live smoke after SETUP:

- [ ] Infil card: Enter begins; `/vabrief` reopens (paused)
- [ ] Phase + clock readable under BAR resource bar
- [ ] Debrief contracts selectable by click, number key, arrows + Enter
- [ ] Partial debrief ≠ green victory (HINGE / Hinge. Not a win.)
- [ ] Hub homecoming shows same verdict word as BAR
- [ ] Abandon / incomplete obvious on hub
- [ ] SETUP still syncs mod widgets (incl. `va_ash_tokens.lua`)

---

## Non-goals

RML / BAR-UI-2.0 port · gadget credit law changes · new art pipeline · Chili main HUD
