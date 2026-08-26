# 35 — Craft roll-in + dev launch telemetry

**Status:** shipped  
**Date:** 2026-07-26

## What landed

### 1. Overnight champion craft is now the live campaign

| Artifact | Role |
|----------|------|
| `app/brain/craft_recipe.json` | Champion knobs (score 0.960) |
| `app/brain/craft_width_override.json` | Width curve pin (mission 0..14) |
| `app/brain/campaign_craft.json` | Live stamp for BAR compiler + fair sim |
| `state/campaign_state.json` | `progression.difficultyDial` synced to craft difficulty |

**Fair sim:** `build_full_campaign(use_craft=True)` (default when recipe exists) stamps:

- solution_space widths / decoys / win predicates  
- per-arc enemy teeth (`arc1/2/3_scale` × `enemy_aggro`)  
- arc3 fortify + player tax + clock bite  
- lane geometry bias  

**BAR seeds:** `scripts/build_next_mission_v1.ps1` multiplies `enemyScale` by craft aggro × arc scale, and embeds `craft` + `devTelemetry` on the seed.

**Launchers:**

```
app\bin\ROLL_CRAFT.bat          # pin + stamp + verify
app\bin\RUN_CAMPAIGN.bat        # fair 15-mission at craft difficulty
```

### 2. Dev launch — learn fast from *you*

```
app\bin\DEV_LAUNCH.bat          # roll craft + arm dense telemetry + rebuild seed
app\bin\DEV_HARVEST.bat         # after play: infolog → bar_brain (human gold)
```

Or:

```powershell
python -m quantum_bar_ai.dev_launch
python -m quantum_bar_ai.dev_launch --launch   # also start play_session
# …play in BAR…
python -m quantum_bar_ai.dev_launch --harvest
```

**What “dense” means (Lua gadget):**

- `VA_DEV_SAMPLE_JSON` every ~5s (150 frames @ 30fps, configurable)  
- Player command histogram (move / fight / build / reclaim / …)  
- Resource snapshot + army centroid  
- Armed via `app/brain/dev_mode.json` → `generated/dev_telemetry_flag.lua`  

**Learning weight:** human samples train at ~**2.4×** (win) / **1.4×** (loss) vs proxy sim tapes.

Modules:

- `quantum_bar_ai.craft_apply` — knobs, stamp, roll-in  
- `quantum_bar_ai.dev_launch` — arm / disarm / harvest  
- `quantum_bar_ai.player_telemetry` — parse infolog → action tape → bar_brain  

## Champion knobs (rolled in)

```json
{
  "difficulty": 1.31,
  "width_early": 0.18,
  "width_late": 0.74,
  "width_ease": 0.66,
  "decoy_pressure": 2.2,
  "enemy_aggro": 1.35,
  "lane_bias": 1.02,
  "path_purity_target": 0.37,
  "arc1_scale": 0.94,
  "arc2_scale": 0.95,
  "arc3_scale": 1.67
}
```

Intent: arc1 clear (~90%), arc2 tense (~60%), arc3 bites but beatable (~80%), overall ~77%.

## Operator morning path

1. `app\bin\ROLL_CRAFT.bat` (idempotent)  
2. `app\bin\DEV_LAUNCH.bat`  
3. Play the mission in BAR  
4. `app\bin\DEV_HARVEST.bat`  
5. Repeat — brain converges on *your* habits faster than proxy-only gym  

Disarm dense telemetry: `python -m quantum_bar_ai.dev_launch --disarm`

## Not customer

Dev mode stays in the design forge. `EXPORT_CUSTOMER` does not advertise it; disarm before friend demos if you want quiet infologs.
