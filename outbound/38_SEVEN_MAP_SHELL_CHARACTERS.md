# Outbound 38 — Seven-map living shell characters (execution freeze)

**Date:** 2026-07-27  
**Status:** Phase A freeze + Phase B rate execution (see outbound 39)  
**Concept sources:** seven_maps.json, outbound 06/09/36/37, map_calibration_recommendations, zone maps, first_arc/campaign arcs  
**Does not invent lore** — only executes pre-authored map roles on the living-shell substrate.  
**Grow rates:** `data/base_templates/grow_profiles.json` + per-start `growProfile` on each recipe (SimpleAI sprawl vs BARb easy/medium/hard).

---

## North star

One shell system, seven characters. Wrath ephemeral. Scars persist (Phase C). Capture later as node claim (Phase D).

| Faction | Shell role |
|---------|------------|
| Armada | Default lattice |
| Null Mercs | Flank foothold (non-PVE); ally if rep >= 40 |
| Cortex | Contractor / high-tech pockets only |
| Ashwalkers | Player |
| Raptors | Hazard (Jungle center, ATS center) — not strip-shell cities |

---

## Character matrix

| Map | Descriptor | Shell at t=0 | Bake | Wrath | Arc kinds | Capture later |
|-----|------------|--------------|------|-------|-----------|---------------|
| **greenest_fields** | Synthesized Utopia | Energy islands + LLTs (0 metal) | 8 ARM / 15m | gunslinger 120s | eco_raid, eco_expand | deny only |
| **eye_of_horus** | MIRV Glassed Core | Cortex core + Armada rim | COR core + ARM rim | cortex_qrf 100s | strike_relay | cut node |
| **koom_valley** | Fluid Scar | Lane + ridge pockets | 4-5 ARM + 1 NMC | gunslinger 120/150 | seize_lane, eco_raid | lane node |
| **tabula** | Tiered Plateau | Terrace forts | 5-6 ARM + 1 NMC | gunslinger 120s | hold_plateau, eco_expand | step hold |
| **ancient_bastion** | Taelith-Armada Citadel | Outer works + citadel teeth | outer + citadel D-heavy | bastion_heavy 90s | siege | outer rings |
| **the_rock_jungle** | Limestone Spire Labyrinth | Thin Null scrap + wilds | 1-2 NMC sparse | wild_thin / wild clock | survive_wilds | corridor |
| **all_that_simmers** | High-Conflict Swamp | ARM/COR corners + lane + raptor center | multi-faction | faction-colored | seize_lane, multipressure | flip node |

---

## Per-map (short)

### Greenest Fields
Energy sprawl, converter utopia. Raid pockets, extract before contact wrath. Placeholder + recipe shipped (37).

### Eye of Horus
Surgical strike on SE Cortex dealer pocket; debris lanes are Armada rim teeth; glass center stays open. Null flank foothold (not a city).

### Koom Valley
Moving front: ferrocrete on fluid scar + ridge pockets. seize_lane stands the scar; eco_raid continue promotes a ridge on the same shell.

### Tabula
Staircase of decisions: denser D on gates/rims, eco on plateaus. hold_plateau owns a step; eco_expand plants on held ground.

### Ancient Bastion
Siege benchmark. Outer approach belts + eastern citadel spine (D8). Bite outer rings; do not full-wipe the fortress.

### The Rock Jungle
PVE outlier. Sparse Null scrap only; center is raptor wilds (not baked buildings). Do not use for global eco tuning.

### All That Simmers
Calibration anchor. NE Armada ridge, SW Armada lagoon, SE Cortex basin, swamp lane teeth, center raptor hazard. Multipressure picks which shell to bleed.

---

## Artifacts

```
data/base_templates/<mapId>/bake_recipe.json
data/base_templates/<mapId>/*_placeholder_v1.json
data/base_templates/wrath/*.json
scripts/generate_placeholder_shell.ps1
scripts/bake_living_shell.ps1
```

## Phases

| Phase | Work |
|-------|------|
| **A** | Recipes + placeholders + wrath packs + compiler kinds (this drop) |
| **B** | BARb/SimpleAI rate mixes + real headless bakes + shell character membrane (outbound 39) |
| **C** | Scar ledger + abstract regrow |
| **D** | Capture = clear node + hold (not empty grass) |
| **E** | Voice/polish / lane membrane on shell geometry |

---

*End outbound 38.*
