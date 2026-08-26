# Outbound 39 — Seven-map grow rates + shell character membrane

**Date:** 2026-07-27  
**Status:** Phase B in progress — recipes + rate-tuned placeholders + membrane shipped; real headless bakes validated (launch path)  
**Sources:** seven_maps.json, map_calibration_recommendations, outbound 36/37/38, playable_testing_loop BARb profiles  
**Does not invent lore** — executes documented map characters with SimpleAI / BARbarIAn rate mixes.

---

## North star

One shell system, **seven characters**, grown at **different AI rates**:

| Rate profile | AI | BAR profile | Texture after strip |
|--------------|-----|-------------|---------------------|
| `sprawl` | SimpleAI | — | Eco-heavy islands |
| `hold` | SimpleAI | — | Balanced rim/ridge |
| `fortify_easy` | BARb | easy | Light teeth |
| `fortify` | BARb | medium | Lane/gate fortification |
| `fortify_hard` | BARb | hard | Citadel / dealer cores |
| `aggressive_core` | BARb | hard_aggressive | Military core (optional) |
| `scrap` / `thin` | SimpleAI | — | Sparse foothold / glass edge |

Canonical catalog: `data/base_templates/grow_profiles.json`

All grow teams **co-ally** (`peacefulCoGrow`) so they expand without wiping each other.

---

## Character matrix (rate mix)

| Map | Grow mix | Placeholder units (v2 rates) | Wrath | Raid hint (membrane) |
|-----|----------|------------------------------|-------|----------------------|
| **greenest_fields** | 7× sprawl + 1× fortify_easy | **351** | gunslinger 120s | raid_eco_extract |
| **eye_of_horus** | fortify_hard COR core + thin glass + hold rims | **208** | cortex_qrf 100s | strike_core_extract |
| **koom_valley** | fortify scar + hold ridges + scrap Null + thin mouth | **149** | gunslinger 120/150 | seize_or_raid_lane |
| **tabula** | fortify_hard plateau + fortify gates + hold rims + thin bowl | **349** | gunslinger 120s | bite_outer_rings |
| **ancient_bastion** | fortify_hard citadel + fortify gate + thin killfield + hold flanks | **416** | bastion_heavy 90s | bite_outer_rings |
| **the_rock_jungle** | 2× scrap Null only | **13** | wild_thin 150s | survive_pathing |
| **all_that_simmers** | hold/sprawl ARM + fortify_hard COR + fortify lane | **175** | gunslinger 110s | multipressure bleed |

Spread check: Jungle **13** ≪ Greenest **351** ≪ Bastion **416** — characters read without opening the map.

---

## Umwelt membrane (campaign-compatible)

Module: `tools/quantum_bar_ai/shell_character_membrane.py`

- **Axes:** eco_surface, defense_teeth, fortress, lane_mass, wild_hazard, multi_faction, tech_spike, siege_depth  
- **Fair rule:** proxy never reads raw diag; leak only `fair_tags` + `raid_hint` + solution geometry  
- **Pack:** `outbox/shell_character_membrane.latest.json`  
- **Hooks:** `shell_solution_geometry()` → MissionSolutionSpace-compatible vectors/predicates (EXTRACT always viable)  
- **Tests:** `python -m unittest quantum_bar_ai.test_shell_character -v` (use umwelt venv)

Grow-profile tilts bake into the membrane so craft/brain sees “BARb hard citadel” vs “SimpleAI sprawl” without inventing new lore.

---

## Compiler wire

`build_next_mission_v1.ps1` loads living shells for shell-capable kinds when a template exists:

`eco_raid`, `eco_expand`, `economy_disrupt`, `seize_lane`, `strike_relay`, `hold_plateau`, `siege`, `multipressure`, `gate_control`, `survive_wilds`

Wrath pack + responseSeconds come from each map’s `bake_recipe.wrathDefault`.

---

## Real bake (Phase B)

**Preferred locus: cloud** — see [40_CLOUD_BAR_COMPUTE.md](40_CLOUD_BAR_COMPUTE.md). Local headless often stalls at IconsAtlas; cloud Windows VM runs the same recipes/BARb rates.

```powershell
# Cloud (all seven after cloud_config.json is filled)
powershell -File scripts/cloud/New-CloudBakeBundle.ps1
powershell -File scripts/cloud/Invoke-CloudShellBake.ps1 -RefreshMembrane

# Local fallback — correct headless launch (required):
#   --write-dir <barDataRoot> --isolation --only-local <startscript>
#   cwd = barDataRoot
powershell -File scripts/bake_living_shell.ps1 -MapId the_rock_jungle
powershell -File scripts/bake_all_living_shells.ps1   # shortest map first
```

**Learnings baked this pass:**

1. Plain `spring-headless.exe script.txt` can load a **stale My Games startscript** — always use `--write-dir` + `--only-local`.  
2. During bake, **disable living-shell occupation spawn** (`va_shell_bake=1` → `VA_SHELL_SKIP`) so campaign `va_current.lua` does not dump Greenest onto Jungle.  
3. Headless can hang at **f≈30 on IconsAtlas** for many minutes; bake gadget now sets `UnitIconsAsUI=0`, re-asserts `setmaxspeed 20`, and logs `VA_SHELL_BAKE_TICK`. Bake script temporarily patches `springsettings.cfg` for the same.  
4. BARb rates (easy/medium/hard/hard_aggressive) are the documented playable profiles — reuse them for grow texture, not invent new AI names.  
5. Rate-tuned **placeholders are campaign-playable now**; real strip dumps queue when headless clears the atlas stall (overnight `bake_all_living_shells.ps1`).

Until a map’s `living_shell_v1.json` / `armada_t15_v1.json` exists, compiler uses rate-tuned placeholders.

---

## Commands

```powershell
# Regenerate all placeholders with rate character
powershell -File scripts/bake_all_living_shells.ps1 -PlaceholderOnly

# Real bakes when machine free (overnight-friendly)
powershell -File scripts/bake_all_living_shells.ps1

# Membrane pack for craft / umweltd
$env:PYTHONPATH = "$ws\tools;C:\Users\Luke Spooner\ws-win\umwelt\src"
& "C:\Users\Luke Spooner\ws-win\umwelt\.venv\Scripts\python.exe" -m quantum_bar_ai.shell_character_membrane $ws
```

---

## Still open

| Item | Notes |
|------|--------|
| Full 7-map real strip dumps | **Cloud:** `Invoke-CloudShellBake.ps1` (outbound 40); local overnight fallback |
| Phase C scars | mapScars + abstract regrow |
| Phase D capture | clear node + hold on shell pockets |
| Phase E | lane membrane strips on Koom/ATS shell geometry |
| ATS raid_hint | multipressure tag strong; fortify_hard COR can pull toward siege — monitor after real bake |

---

*End outbound 39.*
