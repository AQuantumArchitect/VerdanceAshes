# Outbound 37 — Living shell templates (world at t=0)

**Date:** 2026-07-27  
**Status:** Design locked + scaffold shipped (placeholder shell + bake pipeline + wrath gadget)  
**Supersedes (direction):** hand-scattered eco camps as the *only* occupation path  
**Extends:** [36_OCCUPIED_MAP_RAID.md](36_OCCUPIED_MAP_RAID.md)

---

## 1. Fantasy

1. The map is **already full** of Armada (or Cortex / Null) **static eco + light teeth**.
2. Those shapes were **grown by SimpleAI**, then **frozen** — not hand-placed toy farms.
3. Player **raids** marked works (eco + LLTs), then **gets out**.
4. **First contact** starts a response timer. When it fires, **ephemeral gunslinger airdrops** punish loitering.
5. Campaign state stores **scars on the shell only** — never the wrath army.

Capture missions are **deferred** until shells exist; then capture = claim a living node, not stand on empty grass.

---

## 2. Pipeline (offline vs match)

```
OFFLINE BAKE (rare, headless)
  N SimpleAI grow ~15 min
  → dump every unit (VA_SHELL_UNIT)
  → apply strip_filter (keep static eco + defenses)
  → data/base_templates/<mapId>/<templateId>.json

MATCH t=0
  Load template − scars
  Spawn static shell (no coms / cons / facs / mobiles)
  Mark primary pocket as objective_target
  Contact clock armed on first damage/LOS fire
  Response pack = ephemeral (not scarred, not saved)

EXTRACT / CONTINUE
  Scar ledger updates destroyed shell units / zone fractions
  Promote next pocket on same shell
  Wrath roster discarded
```

**Do not** re-grow 15 minutes every sortie. Bake is authoring; scars + abstract regrow are campaign time.

---

## 3. Strip filter (canonical)

**Remove (strip):**

| Class | Examples (Armada) | Rule |
|-------|-------------------|------|
| Commander | `armcom`, `armcomcon`, … | any `*com*` commander family |
| Constructor | `armck`, `armack`, `armch`, … | builders / rezzers that build |
| Factory / nano | `armlab`, `armvp`, `armap`, `armnanotc`, … | production |
| Mobile combat | `armpw`, `armwar`, `armham`, vehicles, air, ships | any non-static combat |
| Mobile support | juno trucks, mobile radar if mobile, etc. | anything with speed that fights or rebuilds |

**Keep (shell):**

| Class | Examples | Role |
|-------|----------|------|
| Energy | `armsolar`, `armadvsol`, `armwin`, `armfus`, `armgeo` | raid surface |
| Conversion / storage | `armmakr`, `armestor`, `armmstor` | converter utopia (Greenest) |
| Metal (where map has it) | `armmex`, `armmoho` | Arc 2 density |
| Static defense | `armllt`, `armbeamer`, `armhlt`, `armrl`, `armpb`, `armguard` | teeth |
| Walls / fort | `armdrag`, `armfort` | clutter / cover |
| Static intel | `armrad`, `armarad`, `armjamt` | optional keep |

Authoritative file: `data/base_templates/strip_filter.json`  
Cortex / Legion mirrors listed there.

---

## 4. Greenest Fields bake spec (v1)

| Knob | Value |
|------|--------|
| Map | `Greenest Fields 1.3` / `greenest_fields` |
| Grow teams | **8 × SimpleAI**, side **Armada** |
| Grow time | **15 minutes** = **27000 frames** @ 30fps |
| Metal | 0 native → energy → converters (correct utopia texture) |
| AI | SimpleAI only (no BARb — we want sprawl, not deathball) |
| Start layout | `data/base_templates/greenest_fields/bake_recipe.json` |
| Strip | `strip_filter.json` after dump |
| Output | `data/base_templates/greenest_fields/armada_t15_v1.json` |
| Until bake runs | `armada_placeholder_v1.json` (compiler-usable density stand-in) |

### Eight start slots (normalized 0–1)

| # | Slot id | Approx (x,z) | Zone / intent |
|---|---------|--------------|---------------|
| 0 | `gf_se_works` | 0.80, 0.80 | `GF_SE_ENERGY_WORKS` primary |
| 1 | `gf_n_desert` | 0.80, 0.17 | `GF_NORTH_DESERT_EDGE` |
| 2 | `gf_s_desert` | 0.20, 0.81 | `GF_SOUTH_DESERT_EDGE` |
| 3 | `gf_nw_green` | 0.15, 0.15 | `GF_NW_GREEN_START` |
| 4 | `gf_central_n` | 0.40, 0.30 | central grassland north |
| 5 | `gf_central_s` | 0.35, 0.50 | central grassland south |
| 6 | `gf_east_mid` | 0.72, 0.45 | east mid energy bleed |
| 7 | `gf_west_mid` | 0.25, 0.45 | west mid |

**Clearance:** do not seed shell units inside player staging `GF_SE_STAGING` (approx 0.46–0.68 × 0.48–0.70). Bake recipe marks that rect as `player_clear`.

### Play fantasy on Greenest

1. Drop strike team (Phobos / rez / Wheelies; Vane Karkinos).  
2. Field is full of solar/wind/converter islands + LLTs.  
3. Wreck ~60% of **marked** pocket eco.  
4. Extract before contact timer → gunslingers.  
5. Debrief: next pocket on same shell **or** leave field.

---

## 5. Contact wrath (session-only)

| Field | Arc A default |
|-------|----------------|
| `startOn` | first damage to enemy shell **or** first weapon fire that hits enemy |
| `responseSeconds` | **120** (3600 frames) |
| `pack` | `wrath/armada_gunslinger_response_v1.json` |
| `spawn` | near player centroid / last contact (air drop scatter) |
| `ephemeral` | **true** — `va_ephemeral=1`, excluded from scar ledger |
| `telegraph` | HUD/bark: “Contact. Response inbound.” |

Wrath is **not** the soft clock. Soft clock / raid budget can still exist; wrath is the “you got noticed” hammer.

**State never saves** unit defs from ephemeral packs.

---

## 6. Living world across the seven-map pool

**Frozen execution cards:** [38_SEVEN_MAP_SHELL_CHARACTERS.md](38_SEVEN_MAP_SHELL_CHARACTERS.md)  
**Recipes + placeholders:** `data/base_templates/<mapId>/`

| Map | Shell at t=0 | Bake flavor | Arc 1 use | Capture later |
|-----|--------------|-------------|-----------|---------------|
| **Greenest Fields** | Many energy islands + LLTs | 8 AI / 15m Armada | Multi-pocket eco raid | Deny works only |
| **Eye of Horus** | Cortex core + Armada rim | Cortex center + Armada ring | Strike relay node | Cut glass-graph node |
| **Koom Valley** | Lane + ridge pockets | 4–6 AI on shelves | Raid a lane works | Hold cleared lane node |
| **Tabula** | Terrace forts | AI per terrace | Gate / rim raids | Hold a step |
| **Ancient Bastion** | Outer works + citadel teeth | Long grow / curated heavy | Bite outer rings | Outer claim only |
| **Rock Jungle** | Thin scrap + wilds | Sparse + raptors | Survive / pass | Corridor, not city |
| **All That Simmers** | ARM / NMC / COR shells | Multi-faction grow | Multipressure bleed | Flip faction node |

Standing paint (unchanged lore):

- **Armada** = default lattice  
- **Null Mercs** = flank foothold (ally if rep ≥ 40)  
- **Cortex** = contractor / high-tech pockets  
- **Ashwalkers** = player; no grown city in Arc 1  

Abstract churn between visits (no BAR):

- time since last raid → partial **regrow %** of scarred eco  
- graph scalars → which pockets fatten  
- Null rep → foothold denser / friendlier  

---

## 7. Schema

### Template (`verdance-living-shell/1.0`)

```json
{
  "schemaVersion": "verdance-living-shell/1.0",
  "mapId": "greenest_fields",
  "templateId": "armada_t15_v1",
  "source": "bake|placeholder",
  "faction": "armada",
  "bake": { "growMinutes": 15, "teams": 8, "seed": 11 },
  "units": [
    {
      "unitDefName": "armsolar",
      "x": 0.81,
      "z": 0.79,
      "facing": 0,
      "zoneId": "GF_SE_ENERGY_WORKS",
      "pocketId": "gf_se_works",
      "keepClass": "energy"
    }
  ],
  "pockets": [
    {
      "pocketId": "gf_se_works",
      "zoneId": "GF_SE_ENERGY_WORKS",
      "label": "Southeast Armada Energy Works",
      "kind": "mixed",
      "center": [0.80, 0.80],
      "unitCount": 42
    }
  ]
}
```

Coords are **normalized 0–1** (same as zone maps). Gadget converts via map size.

### Mission seed fields

```lua
livingShell = {
  enabled = true,
  templateId = "armada_placeholder_v1",
  templatePath = "…",  -- optional audit
  teamID = <enemy team>,
  primaryZoneId = "GF_SE_ENERGY_WORKS",
  primaryPocketId = "gf_se_works",
  units = { … },       -- may be inlined from template − scars
  pockets = { … },
},
wrath = {
  enabled = true,
  startOn = "first_contact",
  responseSeconds = 120,
  packId = "armada_gunslinger_response_v1",
  pack = { units = { { unitDefName = "armpw", count = 8 }, … } },
  ephemeral = true,
  telegraph = true,
},
continueRules = {
  promoteOccupationOnContinue = true,
  clearEnemyOnContinue = false,
  -- scars applied at compile; wrath never carried
}
```

### Scar ledger (campaign — later wire)

```text
mapScars[mapId][] = {
  templateId, unitKey|zoneId|pocketId,
  damage01, destroyed, lastTouchedMission
}
```

---

## 8. Arc harmony

| Arc | Shell | Player | Capture |
|-----|-------|--------|---------|
| **1 First Scar** | Full static shells | No base; raid + extract before wrath | **No** — scars only |
| **2 Expand & Tempo** | Same shells + mex/lab on **claimed** nodes | Limited build on friendly ground | Soft: hold cleared node under pressure |
| **3 Siege & Climax** | Bastion / Simmers dense; Jungle wild | Siege / multipressure | Hard flips only where lore allows |

---

## 9. Tooling (this drop)

| Path | Role |
|------|------|
| `outbound/37_LIVING_SHELL_TEMPLATES.md` | This design lock |
| `data/base_templates/strip_filter.json` | Keep / strip classes |
| `data/base_templates/greenest_fields/bake_recipe.json` | 8 starts + grow knobs |
| `data/base_templates/greenest_fields/armada_placeholder_v1.json` | Dense stand-in until real bake |
| `data/base_templates/wrath/armada_gunslinger_response_v1.json` | Ephemeral response pack |
| `scripts/generate_placeholder_shell.ps1` | Rebuild placeholder from recipe |
| `scripts/apply_shell_strip.ps1` | Raw dump → stripped template |
| `scripts/bake_living_shell.ps1` | Headless grow + dump orchestrator |
| `mod/.../game_verdance_shell_bake.lua` | Headless unit dump at freeze frame |
| `mod/.../game_verdance_living_shell.lua` | Spawn shell + contact wrath in match |
| `build_next_mission_v1.ps1` | Prefer living shell for `eco_raid` when template exists; emit `wrath` |

---

## 10. Operator checklist

1. **Now (no headed demo):** rebuild mission; Greenest `eco_raid` should load **placeholder** shell + wrath config.  
2. **When machine free:**  
   `powershell -File scripts/bake_living_shell.ps1 -MapId greenest_fields`  
   → writes `armada_t15_v1.json` from real SimpleAI grow.  
3. Rebuild mission; primary pocket should be dense grown geometry.  
4. Play when wargen calms: contact → timer bark → gunslingers if you linger.  
5. Later: scar ledger + abstract regrow; then rework capture onto nodes.

---

## 11. Explicit non-goals (this sprint)

- Capture / seize_lane redesign (waits for shells)  
- Cloud bake farm (optional later)  
- Re-baking every mission  
- Saving wrath units into campaign state  

---

*End outbound 37.*
