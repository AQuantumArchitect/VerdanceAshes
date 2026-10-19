# Theater Map + Ashwalker Home (v0.8.3+)

Sortie selection lives on the **theater map** in the hub main view. Infil/exfil
are **legal landing pads**, not “rim or bust.” Home ground is **The Rock Jungle**.
Cortex starts friendly; crater destruction ends that.

Ash Console tokens/copy stay in [`UI_ASH_CONSOLE.md`](UI_ASH_CONSOLE.md). Protocol credit laws stay in [`CAMPAIGN_BAR_PROTOCOL.md`](CAMPAIGN_BAR_PROTOCOL.md).

---

## Legal landing pads

A zone is legal for **infil** or **exfil** when either:

1. **Quiet rim** — `edgeScore ≤ 0.28` and not enemy-held / contested / fortress, **or**
2. **Ashwalker base** — `controllingFaction == ashwalkers` **and** Ashwalkers hold a
   majority of the zone’s **defensive-value** stack (`factionPresence` = DV only).
   Claimed / established pads with no fresh stack still count. Parked armies do
   not buy the pad; teeth do (Warder rings, turrets, fortify).

Fresh campaigns own **no** Ashwalker ground, so the opening raid enters from the
**standard shell-free north desert** (`GF_NE_PLATEAU`), hits the SE decoy
plateau, and extracts back to that open pad. `GF_NW_MUSTER` is the alternate
quiet rim (also kept clear of living-shell eco). A clean extract with a holding
stack seeds the pad as an Ashwalker sortie origin for later raids. Rezzing
debris / claiming inland ground unlocks midfield pads the same way.

Greenest living-shell bake **never** seeds Armada eco on those two pads
(`playerClear` / omitted pockets in `data/base_templates/greenest_fields/`).

**Optional center vaults:** `GF_C_GATE` and `GF_C_INNER_GATE` each hold a
fusion reactor ringed by beamers (`gf_c_gate_fus` / `gf_c_inner_fus`). High
value, heavily defended, **bonus** secondary marks — never required for the
raid win. Clearing one pays Null Merc standing.

## Unit behavior assist (v1)

Synced gadget `game_verdance_unit_behavior.lua` — player-assist micro on human
sorties (off under `va_autoplay`). Toggle with modoption `va_unit_behavior`.

| Role | Chassis | Behavior |
|---|---|---|
| Rez | `legrezbot` (+canResurrect) | Idle → repair wounded; if energy deficit → reclaim **trees only** (never rocks/geo) |
| Phobos | `legcen` | Skittish kite out of beamer / laser envelopes |
| Skirmish | `legjav` + light ranged | Standoff from commanders **and decoys** (Dgun bubble ~260) |

Rez assist is idle-queue only (your clicks win). Threat kiting may interrupt.

## Constructor craft XP (φ ladder)

Synced gadget `game_verdance_craft_xp.lua`. Toggle: `va_craft_xp`.

Golden-ratio weights (`φ ≈ 1.618`), **repair = 1**:

| Action | Weight | Notes |
|---|---|---|
| Reclaim | **0** | Never pays craft XP |
| Repair | **φ⁰ = 1** | Medium base (bumped up) |
| Build / assist | **φ¹ ≈ 1.62** | Large continuous |
| Resurrect | **φ² ≈ 2.62** | Strong, but under capture |
| Capture / node claim | **φ³ ≈ 4.24** | Highest |

Rewards (percentage of each constructor’s baseline):

- Build power `× (1 + 0.35 · craftXp)` capped at **1.80**
- Build range `× (1 + 0.12 · craftXp)` capped at **1.25**

Rules params: `va_craft_xp`, `va_craft_bp_mult`, `va_craft_range_mult`.

Craft XP does **not** bleed into Spring combat experience (combat curve is separate).

## Combat veterancy (quantum φ phase)

Synced gadget `game_verdance_veterancy.lua`. Toggle: `va_veterancy` (default on).

Engine XP (damage / kills) stays the source of truth. We own the **reward shape** for **all player non-factory units** (weapons → HP/reload/range; mobile → speed):

| Symbol | Value | Role |
|---|---|---|
| φ | ≈ 1.618 | Soft phase scale |
| φ_hp | 1/φ ≈ 0.618 | HP saturates **early** |
| φ_spd | 1 | Move speed mid-early |
| φ_rng | √φ ≈ 1.27 | Weapon range mid |
| φ_as | φ ≈ 1.618 | Attack speed saturates **late** |
| B | 0.55 | Shared budget (tune after Drop) |

```
θ          = xp / (xp + φ)
hpMult     = 1 + B·φ    · xp/(xp + φ_hp)   -- cap 1.90
speedMult  = 1 + B·0.70 · xp/(xp + φ_spd)  -- cap 1.22
rangeMult  = 1 + B·0.85 · xp/(xp + φ_rng)  -- cap 1.28
reloadMult = 1 / (1 + B · xp/(xp + φ_as))  -- floor 0.55 (~1.8× RoF max)
```

**Feel:** early farm → chunky HP; mid → faster legs + longer reach; late → snappier guns.

Ranks on θ: `green` → `blooded` (≥1/φ²) → `hardened` (≥1/φ) → `cracked` (≥1−1/φ²).

Rules params: `va_vet_xp`, `va_vet_theta`, `va_vet_hp_mult`, `va_vet_speed_mult`, `va_vet_range_mult`, `va_vet_reload_mult`, `va_vet_rank`.

Hero campaign `heroHpMult` stamps first; veterancy rebases on that max HP (second layer). Infolog: `VA_VET_ARMED`, `VA_VET_RANK`, `VA_VET_APPLY`.

Speed via `MoveCtrl.Set*MoveTypeData` (+ `selfMoveSpeedChange` hint). Range via `SetUnitWeaponState` + `SetUnitMaxRange`. Absolute baselines each XP tick (mutator-safe; no full `modrules` replace).

## Playfeel pack (easy wins)

| Piece | Where | What |
|---|---|---|
| Rank-up juice | `game_verdance_veterancy` → `gui_verdance_playfeel` | Screen flash + marker on `blooded/hardened/cracked` |
| Power chip | `gui_verdance_playfeel` | Selected unit: Hero · Vet · Craft stack |
| Hurt retreat | `game_verdance_unit_behavior` | Soft fallback to extract/deploy/friend below ~34% HP |
| Constructor idle | same | Capture > rez wreck > repair heroes > repair (trees only for rezbots in deficit) |
| Hold trust HUD | `gui_verdance_objectives` | % + fill bar + world zone outline (`va_hold_*`) |
| Hero scar | campaign already no-wipe | Critical lost → scar bark, sortie continues |
| Bring them home | objectives + playfeel | Barks / periodic nudge / extract marker |
| Optional vaults | objectives markers | Fusion/beamer secondaries tagged `OPTIONAL VAULT` |
| Drop-1 eco softener | campaign `applyFirstDropEcoSoftener` | +450m / +1800e on chapter 1 |
| Debrief card | terminal rules params | Primary / sec / scars / extract summary |
| Hub sticky peaks | `app/showoff` hero cards | Career rank badge (**Green**/Blooded/…) — not a movement perk |
| Procedural tags | `va_hero_tags.lua` | Named boosts/nerfs (`runner`, `shieldline`, `deadbolt`…) on spawn |
| Retreat corridor | `gui_verdance_playfeel` | Deploy→extract guide; hurt/skittish rays → repair BP |
| Pad storage | campaign `VA_CREW_spawnPadStorage` | Always plant metal + energy storage on drop |
| Eco / control heroes | crew roster + packs | **Hearth** (fusion), **Solarium** (eco lab), **Warder** (beamer) |

### Injury retreat priority

1. Densest friendly **build-power** nest (nanos / rez / cons)  
2. Nearest healthy friend  
3. Deploy pad  
4. Extract (last resort)

### Eco / control hero packs

| Hero | Chassis | Kit | Hire |
|---|---|---|---|
| **Hearth** | `armfus` | Hero fusion reactor | **free** |
| **Solarium** | `armnanotc` | Adv solar ×2 + converter + construction butler ×2 | 1 Tnb |
| **Warder** | `armbeamer` | Area-control Beamer + radar eye | free |

**Note:** career rank default is **Green** (legacy saves may still say `Runner`). The **`runner` tag** is the speed perk.

### Build-card Tnb cost

Widget `gui_verdance_tnb_buildcost` paints Tenebrium stake **above** metal/energy on grid/build cards (purple). Cost `0` is omitted — only M/E show. Formula mirrors `va_tenebrium_handlers.costOf` (constructors ≈ 1 Tnb). Requires BAR `CostData.above` support — see `docs/patches/BAR_TNB_BUILDCOST_ABOVE.md`.

Toggle assists: `va_unit_behavior`, `va_veterancy` (default on).

| Mark | Color | Rule |
|---|---|---|
| Infil | good / edge | quiet rim **or** Ashwalker-majority base |
| Target | warn | capturable / open wound |
| Exfil | steam | same as infil (open pad you can stack on) |
| Route | steam → warn → steam | arrows |

Stamp rejects illegal pads (`LZ_DEPLOY` / `LZ_EXTRACT` → `valid: false`). Midfield
unowned ground is illegal; midfield Ashwalker bases are fine.

---

## Theater loop

1. Open hub → main column shows the **zone board** for the focused theater.
2. Known intel paints control, open targets, claimed scars.
3. Click a **target** (objective — not a landing). Mode defaults to target.
4. **Infil** / **exfil** accept quiet rim **or** Ashwalker bases.
5. SVG **route arrows**: infil → target → exfil.
6. **Drop into battle** from the bar under the board (same deploy stamp path).

---

## Ashwalker home — Rock Jungle

| Field | Value |
|---|---|
| `sessionHomeMap` (new game) | `the_rock_jungle` |
| Raids | Greenest Fields, Eye of Horus, etc. — harvest **Tenebrium** |
| Home build | Hub choice `home_build` — spend 1 Tnb + 1×1km$ metal → `homeCamp.level` |
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
| Legal LZ helper | `tools/landing_zones_v1.py` |
| Stamp LZ | `tools/stamp_deploy_plan_v1.py` |
| Home + rep + opening | `tools/verdance_story_engine_v1.py` |
| Boards | `tools/build_zone_boards_v1.py` / `boards.embed.js` |
