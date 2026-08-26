# Outbound 26 — Gameplay: difficulty clarity + cracked XP farm

**Date:** 2026-07-25  
**Mode:** `progression.mode = cracked_farm` (default)

---

## What I think we can do better (gameplay)

| Pain | Why it hurts | What we changed |
|---|---|---|
| **XP wiped on death** | Character sheet set `xp = 0` on wreck death — farmed power vanished | **Fixed.** Campaign XP + peak BAR XP never decrease on death. Status/scars still apply. |
| **Heroes barely scale** | BAR experience sat near 0.05–0.3; commander cap L5 | **Cracked ladder:** heroes L1–12, commander L1–8, HP + BAR exp floors by level. Late campaign heroes feel broken. |
| **Difficulty fog** | `q6/q7` + zone memory could spike enemyScale to ~2.9 with little readout | **Dial first.** Softer graph coeffs, soft-capped zone scale, plain-English mission card line: band + scale + dial. |
| **Scarcity starvation** | `q7 ≈ 0.98` pushed resource floor to 0.8 | Floor raised to **0.90** so early sorties stay readable. |
| **No XP grind loop** | Only spine missions paid | **Farm patrol** debrief candidate: lighter camp, **~1.85× hero XP**, death still keeps XP. |
| **Power invisible mid-fight** | Name tags only | Tags show **`Vane  L5 Captain`**. |

### Still worth tuning later (not this pass)

1. **Presence HUD** — capture % still under-communicated on seize_lane.
2. **Extract distance** — some maps still feel like “win at spawn.”
3. **Dead heroes stay dead** — FE rule kept; XP is banked if you ever restore them via story.
4. **Live BAR seat / ant overnight** — optional, not required for friend demo.

---

## Progression model (cracked_farm)

```
state.progression = {
  mode: "cracked_farm" | "standard",
  difficultyDial: 0.70–1.35,   // LOUD knob (default 1.0)
  xpMultiplier: 0.5–3.0,       // farm rate without touching enemy scale
  farmSortiesEnabled: true,
  xpPersistOnDeath: true       // always honored
}
```

| Source | Commander XP | Hero campaign XP |
|---|---|---|
| Clean win | ~64 | ~82 (+ farm ×1.85) |
| Messy win | ~52 | ~70 |
| Defeat | ~14 | ~28 (partial if dead) |

- **Hero levels:** 100 campaign XP / level, max 12 → rank Runner → … → **Cracked**
- **BAR unit XP floor:** `0.15 + (level-1)*0.55` (L12 ≈ 6.2 — endgame monsters)
- **HP mult:** grows with level (wounded still ×0.82)

Switch to modest rates anytime:

```json
"progression": { "mode": "standard", "difficultyDial": 1.0 }
```

Ease early campaign without hiding the dial:

```json
"difficultyDial": 0.85
```

---

## Difficulty clarity rules

1. **Mission card** prints: `Expected opposition: standard (scale 1.05) · dial 1.00`
2. **Farm sorties** append `FARM SORTIE (bonus XP, lighter camp)` and scale ×0.72
3. Zone-memory scale soft-capped (3500–11000) so one bloated map cannot invent “heavy”
4. Contested graph nudge reduced (`*0.14` was `*0.25`); **dial multiplies on top**

Tune by editing `state/campaign_state.json` → `progression.difficultyDial`, then rebuild next mission.

---

## BAR version check (important)

| Local install | Status |
|---|---|
| Engine | `recoil_2025.06.24` |
| Game packages / BAR.sdd | **Last rapid pull ~2026-06-18** |
| Upstream | **July Balance Patch live (2026-07-23)** + Widget Hub, etc. |

**You are ~1 month behind on BAR content/balance/graphics.**  
Open the **Beyond All Reason launcher → Update / Play** once so packages refresh past June 18. Verdance depends on `Beyond All Reason $VERSION`; staying current keeps unit defs and GL4 effects honest.

---

## How to play the farm version

1. Confirm `state/campaign_state.json` has `"mode": "cracked_farm"`.
2. Rebuild / play session as usual (`PLAY_SESSION_V1` or your console flow).
3. On debrief, pick **“Farm patrol - bank hero XP”** when you want levels without spine pressure.
4. Watch floating tags climb: `L3 Blooded` → `L7 Marshal` → `L11 Cracked`.
5. Die mid-sortie? **XP stays.** Status may go wounded/dead; the ladder does not reset.

---

## Files touched

- `tools/verdance_story_engine_v1.py` — progression, XP persist, economy/difficulty presentation
- `scripts/build_next_mission_v1.ps1` — dial, farm scale, mission card, hero manifest
- `mod/.../game_verdance_campaign.lua` — peak XP sticky on death/rez
- `mod/.../gui_verdance_hero_tags.lua` — level/rank tags
- `mod/.../gui_verdance_objectives.lua` — clear difficulty label
- `tests/test_verdance_story_engine_v1.py` — XP persist + cracked farm coverage
- `state/campaign_state.json` — progression block enabled

---

## Friend pitch (one line)

> Fair campaign, **XP that never resets on death**, and a farm lane so by the end Vane and Ketha are **cracked** — and the mission card always tells you how hard the fight is.
