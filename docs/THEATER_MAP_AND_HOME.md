# Theater Map + Ashwalker Home (v0.8.3)

Sortie selection lives on the **theater map** in the hub main view. Infil/exfil stay on the **rim**. Home ground is **The Rock Jungle**. Cortex starts friendly; crater destruction ends that.

Ash Console tokens/copy stay in [`UI_ASH_CONSOLE.md`](UI_ASH_CONSOLE.md). Protocol credit laws stay in [`CAMPAIGN_BAR_PROTOCOL.md`](CAMPAIGN_BAR_PROTOCOL.md).

---

## Theater loop

1. Open hub → main column shows the **zone board** for the focused theater.
2. Known intel paints control, open targets, claimed scars.
3. Click a **target** (objective — not a landing). Mode defaults to target.
4. **Infil** and **exfil** only accept **rim** zones (`edgeScore ≤ 0.28`).
5. SVG **route arrows**: infil → target → exfil.
6. **Drop into battle** from the bar under the board (same deploy stamp path).

| Mark | Color | Rule |
|---|---|---|
| Infil | good / edge | rim only |
| Target | warn | capturable / open wound |
| Exfil | steam | rim only |
| Route | steam → warn → steam | arrows |

Stamp rejects midfield infil/exfil (`RIM_DEPLOY` / `RIM_EXTRACT` errors → `valid: false`).

---

## Ashwalker home — Rock Jungle

| Field | Value |
|---|---|
| `sessionHomeMap` (new game) | `the_rock_jungle` |
| Raids | Greenest Fields, Eye of Horus, etc. — harvest **Tenebrium** |
| Home build | Hub choice `home_build` — spend Tnb/scrap → `homeCamp.level` |
| Scale truth | Units that build cost ≥1 Tnb; without Tnb you cannot scale BP at home |
| Win slice | **Home Clear** — claim central wilds (+ key shelves) when Tnb/camp scale is enough |

Flags:

- `homeClearReady` — player has enough scale to attempt the clear
- `homeCleared` — win slice achieved (hub badge + homecoming)

Not this pass: full design-doc Path A/B/C, Jump Spires.

---

## Reputation (new game / RESET)

| Faction | Start | Note |
|---|---|---|
| Armada | **18** | Cold line garrison |
| Cortex | **70** | Dealers want customers |
| Nullmercs | 48 | Unchanged |
| sev | 50 | Unchanged |

**Cortex crater grudge:** sorties on `eye_of_horus` (or Cortex-tagged destruction) with destroyed objectives / key structures:

| Verdict | Cortex Δ (approx) |
|---|---|
| victory | −15 … −20 |
| partial | −8 … −12 |
| defeat with damage | −4 |

Plan `repDelta` always applies. Live saves are not rewritten; RESET picks new defaults.

---

## Files

| Surface | Path |
|---|---|
| Hub theater | `app/showoff/index.html` |
| Hub intel | `tools/build_hub_state_v1.py` → `theater` |
| Stamp rim | `tools/stamp_deploy_plan_v1.py` |
| Home + rep | `tools/verdance_story_engine_v1.py` |
| Boards | `tools/build_zone_boards_v1.py` / `boards.embed.js` |
