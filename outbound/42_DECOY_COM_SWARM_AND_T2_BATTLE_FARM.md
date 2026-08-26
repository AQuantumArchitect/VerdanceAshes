# Outbound 42 — Decoy commander swarm + Koom T2 battle farm

**Date:** 2026-07-28  
**Status:** Design locked + scaffolding shipped (placeholders / strip / recipes). Real dumps still need cloud/local headless.  
**Extends:** [37](37_LIVING_SHELL_TEMPLATES.md), [39](39_SEVEN_MAP_GROW_RATES.md), [40](40_CLOUD_BAR_COMPUTE.md)

---

## 1. The idea

### A. Armada decoy-commander eco swarm

Initial occupation used to read as “AI left a dead factory base.” Better fiction:

> **Armada deploys a swarm of autonomous decoy commanders** across the landscape, each farming solars and converters. They *look* like command nodes. They are not real commanders.

| Layer | Commander | Why |
|-------|-----------|-----|
| **Sim / bake** | **Normal** `armcom` / `corcom` / `legcom` | BARb/SimpleAI grow correctly; easy |
| **Strip** | **Remove** real coms (always) | No com soup, no D-gun economy |
| **Occupation shell** | **Plant** `armdecom` / `cordecom` / `legdecom` | Thematic swarm; ~770 metal; weak death; light build set only |

Gameplay effects we want:

- Less dangerous than a real com left on the map  
- Less rewarding for military metal counting  
- Still a visible “node” on each eco island  
- Raid objectives stay **eco structures**, not the decoy (decoys hold fire / hold position)

### B. Koom Valley T2 mid battle farm

Separate bake path (not peaceful multi-pocket co-grow):

1. **1v1** BARb **hard_aggressive** vs BARb **hard_aggressive** on Koom Valley  
2. Let them fight ~**22 min** (~T2)  
3. Dump → **T2 strip filter** (keep moho/fus/advanced statics; still strip facs/cons/mobiles/real coms)  
4. Plant decoy nodes  
5. Treat **central Fluid Scar** pocket as a **T2 starting position** (claim pad)

Goal: mid density that *feels* like a 3v3 mid without full 3v3 cost first. If mid is thin, next step is `bake_recipe_t2_battle_3v3.json`.

---

## 2. BAR unit facts

| Def | Role |
|-----|------|
| `armdecom` | Decoy for `armcom` — builder light eco, ~770 m, `isdecoycommander` |
| `cordecom` | Cortex mirror |
| `legdecom` | Legion mirror |

Real coms remain **sim-only**.

---

## 3. Files

| Path | Role |
|------|------|
| `data/base_templates/strip_filter.json` | Keep decoy defs; decoy plant policy |
| `data/base_templates/strip_filter_t2_battle.json` | Richer T2 keep set for battle mids |
| `data/base_templates/grow_profiles.json` | Documents sim=normal / occupation=decoy |
| `data/base_templates/koom_valley/bake_recipe.json` | Peaceful shell + occupation.decoyCommanders |
| `data/base_templates/koom_valley/bake_recipe_t2_battle_1v1.json` | Battle farm recipe |
| `scripts/apply_shell_strip.ps1` | Plants decoys after strip; `-FilterPath` |
| `scripts/generate_placeholder_shell.ps1` | Placeholder decoy per pocket |
| `scripts/package_battle_farm.ps1` | Packages battle startscript + queue |
| `scripts/cloud/_cloud_common.ps1` | `RecipePath`; skips `aiStart:false` pockets |
| `game_verdance_campaign.lua` | Decoys ≠ commanders (sweep / loss) |
| `game_verdance_living_shell.lua` | Spawn tags + hold orders for decoy nodes |

---

## 4. Commands

```powershell
$ws = "C:\Users\Luke Spooner\Documents\BAR_Verdance_Workspace"
cd $ws

# Refresh all placeholders (includes decoy nodes)
powershell -File scripts/bake_all_living_shells.ps1 -PlaceholderOnly

# Package Koom 1v1 T2 battle farm (offline)
powershell -File scripts/package_battle_farm.ps1

# After a real dump lands:
powershell -File scripts/apply_shell_strip.ps1 `
  -RawDumpPath headless_runs\...\raw_units.json `
  -MapId koom_valley `
  -TemplateId living_t2_mid_v1 `
  -RecipePath data\base_templates\koom_valley\bake_recipe_t2_battle_1v1.json `
  -FilterPath data\base_templates\strip_filter_t2_battle.json
```

Cloud path once AWS is up: package battle farm → sync → remote worker → harvest with T2 filter.

---

## 5. Capture / T2 start (next phase)

`claim.mode = mid_base_t2_start` on the battle recipe is the contract:

- Player does **not** get factories from the shell  
- Player **does** get the mid static pad (T2 eco + teeth + decoy node geometry)  
- Campaign capture / continue can spawn the player force at mid with T2-ish metal/energy reserves (compiler work — Phase D)

---

## 6. Success criteria

1. Placeholders include ≥1 `armdecom`/`cordecom`/`legdecom` per non-thin pocket  
2. Strip never keeps `armcom` / `corcom` / `legcom`  
3. Campaign does not treat decoys as real commanders  
4. Battle package emits 2× BARb hard_aggressive, `peacefulCoGrow=false`, ~39600 frames  
5. After cloud bake: `living_t2_mid_v1.json` has a dense mid pocket usable as T2 start fiction  

---

## 7. Explicit non-goals (this drop)

- Running the multi-hour battle sim locally (IconsAtlas / AWS still the locus)  
- Full 3v3 battle farm (design ready; recipe not authored until 1v1 results)  
- Letting decoys rebuild the map mid-raid (spawn holds fire / stop)  
