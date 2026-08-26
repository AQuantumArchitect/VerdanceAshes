# Ash Console — Shared UI Feel

**One product, two skins:** BAR in-theater HUD + HTML war-room hub.

Version: **0.8.3** (theater map + home jungle). Protocol credit laws stay in `docs/CAMPAIGN_BAR_PROTOCOL.md` and `tools/match_credit_v1.py`. Theater/home rules: `docs/THEATER_MAP_AND_HOME.md`.

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
| Deploy / landing | `good` / `edge` |
| Objective | `warn` |
| Extract | `steam` |

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

## Surfaces

| Surface | File | Role |
|---|---|---|
| Hub | `app/showoff/index.html` | Company, Drop board, homecoming card, Abandon |
| BAR command deck | `gui_verdance_objectives.lua` | Briefing, phase strip, barks, debrief + 1/2/3 |
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
- **Phase chip:** APPROACH / FIGHT / EXTRACT / TIMEOUT
- **Verdict colors:** victory=`good`, partial=`warn`, defeat=`bad`, abandon=`muted`, incomplete=`steam`

---

## Presentability checklist

Operator live smoke after SETUP:

- [ ] Briefing dismissible (Space), reopenable (`/vabrief`)
- [ ] Phase + clock readable under BAR resource bar
- [ ] Partial debrief ≠ green victory (HINGE / Hinge. Not a win.)
- [ ] Hub homecoming shows same verdict word as BAR
- [ ] Abandon / incomplete obvious on hub
- [ ] SETUP still syncs mod widgets (incl. `va_ash_tokens.lua`)

---

## Non-goals

RML / BAR-UI-2.0 port · gadget credit law changes · new art pipeline · Chili main HUD
